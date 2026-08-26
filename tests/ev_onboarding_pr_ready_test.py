#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_pr_ready.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_pr_ready", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load EV-IMP-013 tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    original = mod.request_tool.build_request
    try:
        reviewed = "a" * 64
        mod.request_tool.build_request = lambda repo_root, package_jurisdiction_id, reviewed_bundle_sha256: {
            "status": "READY_FOR_DRAFT_PR",
            "branch": "onboarding/wa-example-aaaaaaaaaaaa",
            "pull_request": {"title": "Onboard jurisdiction-wa-example (aaaaaaaaaaaa)"},
        }
        head = "b" * 40
        evidence = {
            "pull_request": {
                "number": 88,
                "state": "OPEN",
                "is_draft": True,
                "base_branch": "main",
                "head_branch": "onboarding/wa-example-aaaaaaaaaaaa",
                "head_sha": head,
                "title": "Onboard jurisdiction-wa-example (aaaaaaaaaaaa)",
                "body": f"reviewed bundle {reviewed}",
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
        }
        decision = mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, evidence)
        assert decision["status"] == "READY_TO_MARK_READY"
        assert decision["ready_transition_required"] is True
        assert decision["merge_authorized"] is False
        assert decision["auto_merge_authorized"] is False
        assert decision["canonical_writes"] == 0

        bad_path = json.loads(json.dumps(evidence))
        bad_path["pull_request"]["changed_files"].append("README.md")
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, bad_path)
        except mod.ReadyGateError as exc:
            assert "forbidden paths" in str(exc)
        else:
            raise AssertionError("forbidden path must fail closed")

        failed_ci = json.loads(json.dumps(evidence))
        failed_ci["workflow_runs"][0]["conclusion"] = "failure"
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, failed_ci)
        except mod.ReadyGateError as exc:
            assert "not successful" in str(exc) or "failing exact-head" in str(exc)
        else:
            raise AssertionError("failed required CI must fail closed")

        head_drift = json.loads(json.dumps(evidence))
        head_drift["pull_request"]["head_sha"] = "c" * 40
        try:
            mod.evaluate(ROOT, "jurisdiction-wa-example", reviewed, head, head_drift)
        except mod.ReadyGateError as exc:
            assert "head SHA changed" in str(exc)
        else:
            raise AssertionError("head drift must fail closed")

        mod.request_tool.build_request = lambda repo_root, package_jurisdiction_id, reviewed_bundle_sha256: {"status": "NOOP"}
        noop = mod.evaluate(ROOT, "jurisdiction-co-akron", reviewed, head, {})
        assert noop["status"] == "NOOP"
        assert noop["ready_transition_required"] is False
        assert noop["merge_authorized"] is False
    finally:
        mod.request_tool.build_request = original

    print(json.dumps({
        "gate": "EV-IMP-013",
        "status": "PASS",
        "clean_exact_head": "READY_TO_MARK_READY",
        "forbidden_path": "FAIL-CLOSED",
        "failed_required_ci": "FAIL-CLOSED",
        "head_drift": "FAIL-CLOSED",
        "merge_authorized": False,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
