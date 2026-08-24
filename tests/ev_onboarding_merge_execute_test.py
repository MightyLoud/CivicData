#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_merge_execute.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_merge_execute", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load EV-IMP-015 tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    original = mod.eligibility.evaluate
    try:
        reviewed = "a" * 64
        head = "b" * 40
        mod.eligibility.evaluate = lambda repo_root, package_id, reviewed_sha, head_sha, evidence: {
            "status": "MERGE_ELIGIBLE",
            "pull_request_number": 88,
            "head_sha": head,
            "reviewed_bundle_sha256": reviewed,
        }
        auth = mod.authorization_text(88, head)
        request = mod.build_request(ROOT, "jurisdiction-wa-example", reviewed, head, auth, {})
        assert request["status"] == "AUTHORIZED_FOR_ONE_SQUASH_MERGE"
        assert request["pull_request_number"] == 88
        assert request["expected_head_sha"] == head
        assert request["merge_method"] == "squash"
        assert request["merge_authorized"] is True
        assert request["auto_merge_authorized"] is False
        assert request["publication_authorized"] is False
        assert request["canonical_writes"] == 0
        assert len(request["request_sha256"]) == 64

        try:
            mod.build_request(ROOT, "jurisdiction-wa-example", reviewed, head, "AUTHORIZE MERGE PR #88", {})
        except mod.MergeExecutionError as exc:
            assert "authorization mismatch" in str(exc)
        else:
            raise AssertionError("partial authorization must fail closed")

        mod.eligibility.evaluate = lambda *args, **kwargs: {"status": "NOOP"}
        noop = mod.build_request(ROOT, "jurisdiction-co-akron", reviewed, head, "irrelevant", {})
        assert noop["status"] == "NOOP"
        assert noop["merge_required"] is False
        assert noop["merge_authorized"] is False

        mod.eligibility.evaluate = lambda *args, **kwargs: {"status": "BLOCKED"}
        try:
            mod.build_request(ROOT, "jurisdiction-wa-example", reviewed, head, auth, {})
        except mod.MergeExecutionError as exc:
            assert "MERGE_ELIGIBLE" in str(exc)
        else:
            raise AssertionError("non-eligible decision must fail closed")
    finally:
        mod.eligibility.evaluate = original

    print(json.dumps({
        "gate": "EV-IMP-015",
        "status": "PASS",
        "exact_authorization": "PASS",
        "partial_authorization": "FAIL-CLOSED",
        "noneligible": "FAIL-CLOSED",
        "merge_method": "squash",
        "auto_merge_authorized": False,
        "publication_authorized": False,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
