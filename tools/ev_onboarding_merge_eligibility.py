#!/usr/bin/env python3
"""Evaluate final merge eligibility for a reviewed onboarding pull request.

EV-IMP-014 is the final decision gate before a separately authorized merge. It
binds the exact EV-IMP-012 reviewed bundle to the live, non-draft pull request,
its exact head commit, allowlisted files, clean merge state, successful exact-
head CI, and an explicit final human review acknowledgement. It never performs
or authorizes the merge itself.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUEST_TOOL = ROOT / "tools" / "ev_onboarding_pr_request.py"
_spec = importlib.util.spec_from_file_location("ev_onboarding_pr_request_for_merge", REQUEST_TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load EV-IMP-012 request tool")
request_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(request_tool)

REQUIRED_WORKFLOWS = {
    "Empowered.Vote Essentials consumer",
    "Civic GPS live smoke",
    "EV onboarding live batch",
}


class MergeEligibilityError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _validate_commit_sha(value: str) -> str:
    value = str(value).lower()
    if len(value) != 40:
        raise MergeEligibilityError("expected head SHA must be a 40-character commit SHA")
    try:
        int(value, 16)
    except ValueError as exc:
        raise MergeEligibilityError("expected head SHA must be hexadecimal") from exc
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


def _require_successful_workflows(rows: list[dict[str, Any]], head: str) -> list[str]:
    successful: list[str] = []
    for name in sorted(REQUIRED_WORKFLOWS):
        exact = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("name") or "") == name
            and str(row.get("head_sha") or "").lower() == head
        ]
        if not exact:
            raise MergeEligibilityError(f"required workflow missing for exact head: {name}")
        if any(str(row.get("status") or "").lower() != "completed" for row in exact):
            raise MergeEligibilityError(f"required workflow not completed: {name}")
        if not any(str(row.get("conclusion") or "").lower() == "success" for row in exact):
            raise MergeEligibilityError(f"required workflow not successful: {name}")
        if any(str(row.get("conclusion") or "").lower() not in {"success", "neutral", "skipped"} for row in exact):
            raise MergeEligibilityError(f"required workflow has failing exact-head run: {name}")
        successful.append(name)
    return successful


def _review_state_by_actor(reviews: list[dict[str, Any]]) -> dict[str, str]:
    latest: dict[str, tuple[str, str]] = {}
    for row in reviews:
        if not isinstance(row, dict):
            raise MergeEligibilityError("invalid review evidence row")
        actor = str(row.get("actor") or row.get("user") or "").strip()
        state = str(row.get("state") or "").upper().strip()
        submitted = str(row.get("submitted_at") or "")
        if not actor or state not in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}:
            continue
        current = latest.get(actor)
        if current is None or submitted >= current[0]:
            latest[actor] = (submitted, state)
    return {actor: state for actor, (_, state) in sorted(latest.items())}


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
            "gate": "EV-IMP-014",
            "status": "NOOP",
            "package_jurisdiction_id": package_jurisdiction_id,
            "reviewed_bundle_sha256": reviewed_bundle_sha256.lower(),
            "merge_action_required": False,
            "merge_authorized": False,
            "auto_merge_authorized": False,
            "publication_authorized": False,
            "canonical_writes": 0,
        }
    if request.get("status") != "READY_FOR_DRAFT_PR":
        raise MergeEligibilityError(f"unexpected EV-IMP-012 request status: {request.get('status')}")

    pr = evidence.get("pull_request")
    runs = evidence.get("workflow_runs")
    reviews = evidence.get("reviews", [])
    if not isinstance(pr, dict) or not isinstance(runs, list) or not isinstance(reviews, list):
        raise MergeEligibilityError("pull_request/workflow_runs/reviews evidence missing")
    if evidence.get("merge_review_acknowledged") is not True:
        raise MergeEligibilityError("explicit final merge review acknowledgement is required")

    if str(pr.get("state") or "").upper() != "OPEN":
        raise MergeEligibilityError("pull request must be OPEN")
    if pr.get("is_draft") is not False:
        raise MergeEligibilityError("pull request must already be ready for review")
    if str(pr.get("base_branch") or "") != "main":
        raise MergeEligibilityError("pull request base must be main")
    if str(pr.get("head_branch") or "") != str(request["branch"]):
        raise MergeEligibilityError("pull request head branch does not match reviewed request")
    if str(pr.get("head_sha") or "").lower() != head:
        raise MergeEligibilityError("pull request head SHA changed from merge-eligibility request")
    if str(pr.get("title") or "") != str(request["pull_request"]["title"]):
        raise MergeEligibilityError("pull request title drift")

    reviewed = request_tool.validate_sha256(reviewed_bundle_sha256)
    if reviewed not in str(pr.get("body") or ""):
        raise MergeEligibilityError("reviewed bundle SHA-256 missing from pull request body")
    if pr.get("mergeable") is not True:
        raise MergeEligibilityError("pull request is not mergeable")
    merge_state = str(pr.get("merge_state_status") or "").upper()
    if merge_state != "CLEAN":
        raise MergeEligibilityError(f"pull request merge state is not CLEAN: {merge_state}")

    files = pr.get("changed_files")
    if not isinstance(files, list) or not files:
        raise MergeEligibilityError("pull request changed-file evidence missing")
    normalized_files = sorted({str(path) for path in files})
    forbidden = [path for path in normalized_files if not _allowed_path(path)]
    if forbidden:
        raise MergeEligibilityError("pull request contains forbidden paths: " + ",".join(forbidden))

    successful = _require_successful_workflows(runs, head)
    latest_reviews = _review_state_by_actor(reviews)
    blocking = sorted(actor for actor, state in latest_reviews.items() if state == "CHANGES_REQUESTED")
    if blocking:
        raise MergeEligibilityError("changes requested by: " + ",".join(blocking))

    return {
        "gate": "EV-IMP-014",
        "status": "MERGE_ELIGIBLE",
        "package_jurisdiction_id": package_jurisdiction_id,
        "reviewed_bundle_sha256": reviewed,
        "pull_request_number": int(pr["number"]),
        "head_branch": request["branch"],
        "head_sha": head,
        "changed_files": normalized_files,
        "required_workflows": sorted(REQUIRED_WORKFLOWS),
        "successful_workflows": successful,
        "latest_review_states": latest_reviews,
        "merge_review_acknowledged": True,
        "merge_action_required": True,
        "merge_authorized": False,
        "auto_merge_authorized": False,
        "publication_authorized": False,
        "canonical_writes": 0,
    }


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
    (args.output / "merge-eligibility.json").write_text(canonical(report), encoding="utf-8")
    print(canonical(report).strip())


if __name__ == "__main__":
    main()
