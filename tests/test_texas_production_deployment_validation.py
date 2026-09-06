"""Offline disposition controls for exact-head Texas deployment validation."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.texas_production_deployment_validation import CHECK_IDS, _report


class TexasProductionDeploymentValidationTests(unittest.TestCase):
    def inputs(self):
        meta = {
            "jurisdiction_json_sha256": "a" * 64,
            "archive_sha256": "b" * 64,
        }
        receipt = {"deterministic_sha256": "c" * 64}
        return meta, receipt

    def test_six_runtime_checks_plus_missing_host_remains_blocked_not_failed(self):
        statuses = {check_id: "PASS" for check_id in CHECK_IDS[:-1]}
        statuses["hosted-runtime-route"] = "BLOCKED"
        details = {check_id: {} for check_id in CHECK_IDS}
        meta, receipt = self.inputs()
        report = _report("d" * 40, "2026-09-06", statuses, details, meta, receipt)
        self.assertEqual(report["status"], "BLOCKED_HOSTED_RUNTIME_ROUTE")
        self.assertFalse(report["activation_authorized"])
        self.assertEqual(report["repository_activation"], "NOT_ACTIVATED")
        self.assertEqual(report["canonical_writes"], 0)
        self.assertEqual(len(report["deterministic_sha256"]), 64)

    def test_any_non_host_runtime_failure_is_a_validation_failure(self):
        statuses = {check_id: "PASS" for check_id in CHECK_IDS[:-1]}
        statuses["positive-both-bindings"] = "FAIL"
        statuses["hosted-runtime-route"] = "BLOCKED"
        details = {check_id: {} for check_id in CHECK_IDS}
        meta, receipt = self.inputs()
        report = _report("d" * 40, "2026-09-06", statuses, details, meta, receipt)
        self.assertEqual(report["status"], "FAIL")

    def test_missing_checks_do_not_accidentally_pass(self):
        meta, receipt = self.inputs()
        report = _report("d" * 40, "2026-09-06", {}, {}, meta, receipt)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(row["status"] == "NOT_RUN" for row in report["checks"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
