#!/usr/bin/env python3
"""Verify the repository state after an explicitly authorized onboarding merge.

EV-IMP-016 consumes the immutable EV-IMP-015 merge request plus fresh post-
merge evidence. It proves the expected PR was merged at the expected head, the
reported merge commit is present on main, governed onboarding outputs are still
idempotent, required post-merge checks are green, and no publication/canonical
write authority was introduced. It emits closure evidence only; it performs no
repository mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class PostMergeVerificationError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def sha(value: Any) -> str:
    text = str(value or "").lower()
    if len(text) != 40:
        raise PostMergeVerificationError("commit SHA must be 40 characters")
    try:
        int(text, 16)
    except ValueError as exc:
        raise PostMergeVerificationError("commit SHA must be hexadecimal") from exc
    return text


def verify(merge_request: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    if merge_request.get("gate") != "EV-IMP-015" or merge_request.get("status") != "AUTHORIZED_FOR_ONE_SQUASH_MERGE":
        raise PostMergeVerificationError("valid EV-IMP-015 authorized merge request required")
    if merge_request.get("merge_method") != "squash" or merge_request.get("merge_authorized") is not True:
        raise PostMergeVerificationError("merge request does not authorize one squash merge")

    pr = evidence.get("pull_request")
    if not isinstance(pr, dict):
        raise PostMergeVerificationError("post-merge pull_request evidence missing")
    expected_pr = int(merge_request["pull_request_number"])
    expected_head = sha(merge_request["expected_head_sha"])
    if int(pr.get("number", -1)) != expected_pr:
        raise PostMergeVerificationError("merged PR number drift")
    if pr.get("merged") is not True or str(pr.get("state") or "").upper() != "CLOSED":
        raise PostMergeVerificationError("pull request is not closed+merged")
    if sha(pr.get("head_sha")) != expected_head:
        raise PostMergeVerificationError("merged PR head does not match authorized head")

    merge_sha = sha(pr.get("merge_commit_sha"))
    main_head = sha(evidence.get("main_head_sha"))
    main_contains = evidence.get("main_contains_merge_commit")
    if main_contains is not True:
        raise PostMergeVerificationError("merge commit is not proven reachable from main")
    if evidence.get("require_merge_as_current_main_head", False) is True and main_head != merge_sha:
        raise PostMergeVerificationError("current main head is not the expected merge commit")

    checks = evidence.get("post_merge_checks")
    if not isinstance(checks, list) or not checks:
        raise PostMergeVerificationError("post-merge checks missing")
    failed = []
    for row in checks:
        if not isinstance(row, dict) or not row.get("name"):
            raise PostMergeVerificationError("invalid post-merge check evidence")
        if str(row.get("status") or "").upper() != "PASS":
            failed.append(str(row.get("name")))
    if failed:
        raise PostMergeVerificationError("post-merge checks failed: " + ",".join(sorted(failed)))

    if evidence.get("production_materialization_status") != "NOOP":
        raise PostMergeVerificationError("production onboarding materialization is not idempotent NOOP")
    if int(evidence.get("canonical_writes", -1)) != 0:
        raise PostMergeVerificationError("canonical writes must remain zero")
    if evidence.get("publication_performed") is not False:
        raise PostMergeVerificationError("publication must remain false")

    report = {
        "gate": "EV-IMP-016",
        "status": "CLOSED_PASS",
        "pull_request_number": expected_pr,
        "authorized_head_sha": expected_head,
        "merge_commit_sha": merge_sha,
        "main_head_sha_observed": main_head,
        "main_contains_merge_commit": True,
        "post_merge_checks": sorted(str(row["name"]) for row in checks),
        "production_materialization_status": "NOOP",
        "canonical_writes": 0,
        "publication_performed": False,
        "closure_complete": True,
    }
    report["closure_sha256"] = hashlib.sha256(canonical(report).encode()).hexdigest()
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-request", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    request = json.loads(args.merge_request.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = verify(request, evidence)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "closure-evidence.json").write_text(canonical(result), encoding="utf-8")
    print(canonical(result).strip())


if __name__ == "__main__":
    main()
