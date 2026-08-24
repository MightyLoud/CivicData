#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_merge_eligibility.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_merge_eligibility", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load EV-IMP-014 tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    original = mod.request_tool.build_request
    try:
        reviewed = "a" * 64
        branch = "onboarding/wa-example-aaaaaaaaaaaa"
        title = "Onboard jurisdiction-wa-example (aaaaaaaaaaaa)"
        mod.request_tool.build_request = lambda repo_root, package_jurisdiction_id, reviewed_bundle_sha256: {
            "status": "READY_FOR_DRAFT_PR",
            "branch": branch,
            "pull_request": {"title": title},
        }
        head = "b" * 40
        evidence = {
            "merge_review_acknowledged": True,
            "pull_request": {
                "number": 91,
                "state": "OPEN",
                "is_draft": False,
                "base_branch": "main",
                "head_branch": branch,
                "head_sha": head,
                "title": title,
                "body": f"reviewed bundle {reviewed}",
                "mergeable": True,
                "merge_state_status": "CLEAN",
                "changed_files": [
                    "onboarding/ev/example.v0.1.json",
                    "consumers/empowered_vote/package_catalog.v0.1.json",
                    "civic_gps_extensions/registry_bundles.v0.1.json",
                ],
            },
            "workflow_runs": [
                {"name": name, "head_sha": head, "status": "completed", "conclusion": "success"}
                for name in sorted(mod.REQUIRED_WORKFLOWS)
            ],
            "reviews": [
                {"actor": "reviewer-a", "state": "APPROVED", "submitted_at": "2026-08-24T00:00:00Z"},
            ],
        }

        decision = mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, evidence)
        assert decision["status"] == "MERGE_ELIGIBLE"
        assert decision["merge_action_required"] is True
        assert decision["merge_review_acknowledged"] is True
        assert decision["merge_authorized"] is False
        assert decision["auto_merge_authorized"] is False
        assert decision["publication_authorized"] is False
        assert decision["canonical_writes"] == 0

        no_ack = json.loads(json.dumps(evidence))
        no_ack["merge_review_acknowledged"] = False
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, no_ack)
        except mod.MergeEligibilityError as exc:
            assert "acknowledgement" in str(exc)
        else:
            raise AssertionError("missing final review acknowledgement must fail closed")

        draft = json.loads(json.dumps(evidence))
        draft["pull_request"]["is_draft"] = True
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, draft)
        except mod.MergeEligibilityError as exc:
            assert "ready for review" in str(exc)
        else:
            raise AssertionError("draft PR must fail closed")

        requested = json.loads(json.dumps(evidence))
        requested["reviews"].append({
            "actor": "reviewer-b",
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-08-24T00:01:00Z",
        })
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, requested)
        except mod.MergeEligibilityError as exc:
            assert "changes requested" in str(exc)
        else:
            raise AssertionError("active changes-requested review must fail closed")

        failed_ci = json.loads(json.dumps(evidence))
        failed_ci["workflow_runs"][0]["conclusion"] = "failure"
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, failed_ci)
        except mod.MergeEligibilityError as exc:
            assert "not successful" in str(exc) or "failing exact-head" in str(exc)
        else:
            raise AssertionError("failed required CI must fail closed")

        dirty = json.loads(json.dumps(evidence))
        dirty["pull_request"]["merge_state_status"] = "BEHIND"
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, dirty)
        except mod.MergeEligibilityError as exc:
            assert "not CLEAN" in str(exc)
        else:
            raise AssertionError("non-clean merge state must fail closed")

        mod.request_tool.build_request = lambda repo_root, package_jurisdiction_id, reviewed_bundle_sha256: {"status": "NOOP"}
        noop = mod.evaluate(ROOT, "jurisdiction-co-akron", reviewed, head, {})
        assert noop["status"] == "NOOP"
        assert noop["merge_action_required"] is False
        assert noop["merge_authorized"] is False
    finally:
        mod.request_tool.build_request = original

    print(json.dumps({
        "gate": "EV-IMP-014",
        "status": "PASS",
        "clean_final_review": "MERGE_ELIGIBLE",
        "missing_acknowledgement": "FAIL-CLOSED",
        "draft_pr": "FAIL-CLOSED",
        "changes_requested": "FAIL-CLOSED",
        "failed_required_ci": "FAIL-CLOSED",
        "dirty_merge_state": "FAIL-CLOSED",
        "merge_authorized": False,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
