#!/usr/bin/env python3
"""Prepare deterministic Git branch/PR metadata for a reviewed onboarding bundle.

EV-IMP-012 consumes the EV-IMP-011 review binding. It does not merge, publish,
or create civic facts. The companion workflow may use this metadata to create a
review branch and draft pull request only after the exact reviewed bundle hash
has been regenerated and applied successfully.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROMOTE_TOOL = ROOT / "tools" / "ev_onboarding_promote.py"
_spec = importlib.util.spec_from_file_location("ev_onboarding_promote_for_pr", PROMOTE_TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load onboarding promotion tool")
promote_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_tool)


class PRRequestError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not out:
        raise PRRequestError("cannot derive branch slug")
    return out


def validate_sha256(value: str) -> str:
    if len(value) != 64:
        raise PRRequestError("reviewed bundle SHA-256 must be 64 characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise PRRequestError("reviewed bundle SHA-256 must be hexadecimal") from exc
    return value.lower()


def build_request(repo_root: Path, package_jurisdiction_id: str, reviewed_bundle_sha256: str) -> dict[str, Any]:
    reviewed = validate_sha256(reviewed_bundle_sha256)
    plan = promote_tool.generate(repo_root, package_jurisdiction_id, repo_root / ".ev-imp-012-preview")
    if plan["bundle_sha256"] != reviewed:
        raise PRRequestError(
            f"reviewed bundle drift: expected {reviewed}, regenerated {plan['bundle_sha256']}"
        )
    if plan["status"] == "NOOP":
        return {
            "gate": "EV-IMP-012",
            "status": "NOOP",
            "package_jurisdiction_id": package_jurisdiction_id,
            "bundle_sha256": reviewed,
            "branch_creation_required": False,
            "pull_request_creation_required": False,
            "merge_authorized": False,
            "publication_authorized": False,
            "canonical_writes": 0,
        }
    if plan["status"] != "READY_FOR_REVIEW" or plan["changes_required"] <= 0:
        raise PRRequestError(f"unexpected EV-IMP-011 promotion plan status: {plan['status']}")

    short = reviewed[:12]
    slug = _slug(package_jurisdiction_id.removeprefix("jurisdiction-"))
    branch = f"onboarding/{slug}-{short}"
    title = f"Onboard {package_jurisdiction_id} ({short})"
    body = (
        "EV-IMP-012 reviewed onboarding promotion.\n\n"
        f"- Package jurisdiction: `{package_jurisdiction_id}`\n"
        f"- Reviewed bundle SHA-256: `{reviewed}`\n"
        f"- Changes required: `{plan['changes_required']}`\n"
        "- Routing authority was established before this gate.\n"
        "- Canonical CivicData writes: `0`.\n"
        "- This PR is created as a draft. Automatic merge and external publication are not authorized.\n"
    )
    commit_message = f"Onboard {package_jurisdiction_id} via reviewed bundle {short}"
    request = {
        "gate": "EV-IMP-012",
        "status": "READY_FOR_DRAFT_PR",
        "package_jurisdiction_id": package_jurisdiction_id,
        "bundle_sha256": reviewed,
        "branch": branch,
        "base_branch": "main",
        "commit_message": commit_message,
        "pull_request": {
            "title": title,
            "body": body,
            "draft": True,
        },
        "changes_required": plan["changes_required"],
        "branch_creation_required": True,
        "pull_request_creation_required": True,
        "merge_authorized": False,
        "publication_authorized": False,
        "canonical_writes": 0,
    }
    request["request_sha256"] = hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()
    return request


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--package-jurisdiction-id", required=True)
    ap.add_argument("--reviewed-bundle-sha256", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = build_request(args.repo_root.resolve(), args.package_jurisdiction_id, args.reviewed_bundle_sha256)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pr-request.json").write_text(canonical(result), encoding="utf-8")
    print(canonical(result).strip())


if __name__ == "__main__":
    main()
