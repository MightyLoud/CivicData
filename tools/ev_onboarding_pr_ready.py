#!/usr/bin/env python3
"""Validate a reviewed onboarding draft PR before marking it ready for review.

EV-IMP-013 is a narrow GitHub review-state gate. It consumes the exact
EV-IMP-012 reviewed bundle binding plus live PR/workflow evidence. It may
produce a READY_TO_MARK_READY decision only when the draft PR identity, head
SHA, changed-file allowlist, merge state, and required CI workflows all match.
It never merges, enables auto-merge, publishes, or writes canonical CivicData.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUEST_TOOL = ROOT / "tools" / "ev_onboarding_pr_request.py"
_spec = importlib.util.spec_from_file_location("ev_onboarding_pr_request_for_ready", REQUEST_TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load EV-IMP-012 request tool")
request_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(request_tool)

REQUIRED_WORKFLOWS = {
    "Empowered.Vote Essentials consumer",
    "Civic GPS live smoke",
    "EV onboarding live batch",
}


class ReadyGateError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _validate_commit_sha(value: str) -> str:
    value = str(value).lower()
    if len(value) != 40:
        raise ReadyGateError("expected head SHA must be a 40-character commit SHA")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ReadyGateError("expected head SHA must be hexadecimal") from exc
    return value


def _allowed_path(rel: str) -> bool:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return False
    if rel == "consumers/empowered_vote/package_catalog.v0.1.json":
        return True
    if rel == "civic_gps_extensions/registry_bundles.v0.1.json":
        return True
    return len(path.parts) == 3 and path.parts[:2] == ("onboarding", "ev") and path.name.endswith(".v0.1.json")


def _successful_workflows(rows: list[dict[str, Any]], expected_head_sha: str) -> set[str]:
    success: set[str] = set()
    seen_required: dict[str, list[dict[str, Any]]] = {name: [] for name in REQUIRED_WORKFLOWS}
    for row in rows:
        if not isinstance(row, dict):
            raise ReadyGateError("invalid workflow-run evidence row")
        name = str(row.get("name") or "")
        if name in REQUIRED_WORKFLOWS:
            seen_required[name].append(row)
    for name, matches in seen_required.items():
        exact = [
            row for row in matches
            if str(row.get("head_sha") or "").lower() == expected_head_sha
        ]
        if not exact:
            raise ReadyGateError(f"required workflow missing for exact head: {name}")
        if any(str(row.get("status") or "").lower() != "completed" for row in exact):
            raise ReadyGateError(f"required workflow not completed: {name}")
        if not any(str(row.get("conclusion") or "").lower() == "success" for row in exact):
            raise ReadyGateError(f"required workflow not successful: {name}")
        if any(str(row.get("conclusion") or "").lower() not in {"success", "skipped", "neutral"} for row in exact):
            raise ReadyGateError(f"required workflow has failing exact-head run: {name}")
        success.add(name)
    return success


def evaluate(
    repo_root: Path,
    package_jurisdiction_id: str,
    reviewed_bundle_sha256: str,
    expected_head_sha: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    head = _validate_commit_sha(expected_head_sha)
    request = request_tool.build_request(repo_root, package_jurisdiction_id, reviewed_bundle_sha256)
    if request.get("status") == "NOOP":
        return {
            "gate": "EV-IMP-013",
            "status": "NOOP",
            "package_jurisdiction_id": package_jurisdiction_id,
            "reviewed_bundle_sha256": reviewed_bundle_sha256.lower(),
            "ready_transition_required": False,
            "merge_authorized": False,
            "auto_merge_authorized": False,
            "publication_authorized": False,
            "canonical_writes": 0,
        }
    if request.get("status") != "READY_FOR_DRAFT_PR":
        raise ReadyGateError(f"unexpected EV-IMP-012 request status: {request.get('status')}")

    pr = evidence.get("pull_request")
    runs = evidence.get("workflow_runs")
    if not isinstance(pr, dict) or not isinstance(runs, list):
        raise ReadyGateError("pull_request/workflow_runs evidence missing")
    if str(pr.get("state") or "").upper() != "OPEN":
        raise ReadyGateError("pull request must be OPEN")
    if pr.get("is_draft") is not True:
        raise ReadyGateError("pull request must still be draft")
    if str(pr.get("base_branch") or "") != "main":
        raise ReadyGateError("pull request base must be main")
    if str(pr.get("head_branch") or "") != str(request["branch"]):
        raise ReadyGateError("pull request head branch does not match reviewed request")
    if str(pr.get("head_sha") or "").lower() != head:
        raise ReadyGateError("pull request head SHA changed from reviewed readiness request")
    if str(pr.get("title") or "") != str(request["pull_request"]["title"]):
        raise ReadyGateError("pull request title drift")
    body = str(pr.get("body") or "")
    reviewed = request_tool.validate_sha256(reviewed_bundle_sha256)
    if reviewed not in body:
        raise ReadyGateError("reviewed bundle SHA-256 missing from pull request body")
    if str(pr.get("merge_state_status") or "").upper() != "CLEAN":
        raise ReadyGateError(f"pull request merge state is not CLEAN: {pr.get('merge_state_status')}")

    files = pr.get("changed_files")
    if not isinstance(files, list) or not files:
        raise ReadyGateError("pull request changed-file evidence missing")
    normalized_files = sorted({str(path) for path in files})
    forbidden = [path for path in normalized_files if not _allowed_path(path)]
    if forbidden:
        raise ReadyGateError("pull request contains forbidden paths: " + ",".join(forbidden))

    successful = _successful_workflows(runs, head)
    report = {
        "gate": "EV-IMP-013",
        "status": "READY_TO_MARK_READY",
        "package_jurisdiction_id": package_jurisdiction_id,
        "reviewed_bundle_sha256": reviewed,
        "pull_request_number": int(pr["number"]),
        "head_branch": request["branch"],
        "head_sha": head,
        "changed_files": normalized_files,
        "required_workflows": sorted(REQUIRED_WORKFLOWS),
        "successful_workflows": sorted(successful),
        "ready_transition_required": True,
        "merge_authorized": False,
        "auto_merge_authorized": False,
        "publication_authorized": False,
        "canonical_writes": 0,
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--package-jurisdiction-id", required=True)
    ap.add_argument("--reviewed-bundle-sha256", required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise SystemExit("evidence must be a JSON object")
    report = evaluate(
        args.repo_root.resolve(),
        args.package_jurisdiction_id,
        args.reviewed_bundle_sha256,
        args.expected_head_sha,
        evidence,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ready-decision.json").write_text(canonical(report), encoding="utf-8")
    print(canonical(report).strip())


if __name__ == "__main__":
    main()
