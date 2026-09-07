#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_throughput_batch.py"
spec = importlib.util.spec_from_file_location("ev_throughput", TOOL)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    original_propose = mod.proposal.propose
    original_materialize = mod.materialize.materialize
    try:
        def fake_propose(root, jurisdiction_id):
            if jurisdiction_id in {"jurisdiction:ready-add", "jurisdiction:ready-noop"}:
                return {
                    "status": "READY",
                    "profile": "municipal_representation",
                    "routing_candidate": {"status": "GOVERNED_MATCH"},
                }
            if jurisdiction_id == "jurisdiction:review":
                return {
                    "status": "REVIEW_REQUIRED",
                    "profile": "municipal_representation",
                    "routing_candidate": {"status": "RESEARCH_REQUIRED"},
                }
            if jurisdiction_id == "jurisdiction:proposal-error":
                raise ValueError("bad package")
            if jurisdiction_id == "jurisdiction:materialize-error":
                return {
                    "status": "READY",
                    "profile": "municipal_essentials",
                    "routing_candidate": {"status": "GOVERNED_MATCH"},
                }
            raise AssertionError(jurisdiction_id)

        def fake_materialize(root, jurisdiction_id, out):
            if jurisdiction_id == "jurisdiction:materialize-error":
                raise RuntimeError("collision")
            if jurisdiction_id == "jurisdiction:ready-add":
                return {
                    "changes": [
                        {"path": "onboarding/ev/ready.v0.1.json", "action": "ADD"},
                        {"path": "consumers/empowered_vote/package_catalog.v0.1.json", "action": "NOOP"},
                    ],
                    "changes_required": 1,
                }
            if jurisdiction_id == "jurisdiction:ready-noop":
                return {
                    "changes": [
                        {"path": "onboarding/ev/existing.v0.1.json", "action": "NOOP"},
                    ],
                    "changes_required": 0,
                }
            raise AssertionError(jurisdiction_id)

        mod.proposal.propose = fake_propose
        mod.materialize.materialize = fake_materialize

        ids = [
            "jurisdiction:ready-add",
            "jurisdiction:ready-noop",
            "jurisdiction:review",
            "jurisdiction:proposal-error",
            "jurisdiction:materialize-error",
        ]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            report = mod.run(ROOT, out, ids)
            persisted = json.loads((out / "throughput-report.json").read_text(encoding="utf-8"))

        assert persisted == report
        assert report["status"] == "PASS" and report["targets"] == 5
        assert report["ready"] == 2 and report["review_required"] == 1 and report["blocked"] == 2
        assert report["repository_mutated"] is False
        assert report["canonical_writes"] == 0

        rows = {row["package_jurisdiction_id"]: row for row in report["jurisdictions"]}
        assert rows["jurisdiction:ready-add"]["materialization_status"] == "ADD"
        assert rows["jurisdiction:ready-add"]["changes_required"] == 1
        assert rows["jurisdiction:ready-add"]["changed_files"] == ["onboarding/ev/ready.v0.1.json"]
        assert rows["jurisdiction:ready-noop"]["materialization_status"] == "NOOP"
        assert rows["jurisdiction:ready-noop"]["changes_required"] == 0
        assert rows["jurisdiction:review"]["disposition"] == "REVIEW_REQUIRED"
        assert rows["jurisdiction:proposal-error"]["disposition"] == "BLOCKED"
        assert rows["jurisdiction:materialize-error"]["disposition"] == "BLOCKED"

        # A drifted/obsolete materialization result must fail closed rather than
        # being silently interpreted as NOOP (the historical PR #44 failure mode).
        def drifted_materialize(root, jurisdiction_id, out):
            return {"status": "ADD", "changed_files": ["obsolete-contract.json"]}

        mod.materialize.materialize = drifted_materialize
        with tempfile.TemporaryDirectory() as td:
            drift = mod.run(ROOT, Path(td), ["jurisdiction:ready-add"])
        drift_row = drift["jurisdictions"][0]
        assert drift_row["disposition"] == "BLOCKED"
        assert drift_row["materialization_status"] == "ERROR"
        assert "changes" in drift_row["error"]
    finally:
        mod.proposal.propose = original_propose
        mod.materialize.materialize = original_materialize

    print(json.dumps({
        "gate": "EV-IMP-017",
        "status": "PASS",
        "add_noop_contract": "PASS",
        "failure_isolation": "PASS",
        "review_isolation": "PASS",
        "manifest_drift_fail_closed": "PASS",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
