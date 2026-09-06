"""Synthetic release-readiness controls for the activated bounded Texas runtime."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.jurisdiction_package import canonical_json
from tools.texas_release_readiness import EXPECTED_CHECKS, ReleaseReadinessError, build_release_readiness, sha_json

HEAD = "e" * 40
ENTRY_SHA = "1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189"
GROUP_SHA = "826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a"
ACTIVATION_SHA = "8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166"


def evidence(head=HEAD):
    value = {
        "schema_version": "texas-post-activation-hosted-evidence/0.1",
        "environment": "production",
        "head_sha": head,
        "status": "PASS",
        "profile_id": "tx_legislative_two_office_v0.1",
        "repository_activation": "ACTIVATED_BOUNDED",
        "checks": [{"check_id": check_id, "status": "PASS"} for check_id in sorted(EXPECTED_CHECKS)],
        "service_contract_sha256": "f" * 64,
        "catalog_entry_sha256": ENTRY_SHA,
        "legislative_group_sha256": GROUP_SHA,
        "activation_receipt_deterministic_sha256": ACTIVATION_SHA,
        "release_authorized": False,
        "publication_workflow_authorized": False,
        "canonical_writes": 0,
    }
    value["deterministic_sha256"] = sha_json(value)
    return value


class TexasReleaseReadinessTests(unittest.TestCase):
    def test_validated_candidate_is_ready_for_runtime_merge_not_release(self):
        receipt = build_release_readiness(
            repo_root=ROOT,
            hosted_evidence=evidence(),
            expected_head_sha=HEAD,
            runtime_merged=False,
        )
        self.assertEqual(receipt["status"], "READY_FOR_RUNTIME_MERGE")
        self.assertFalse(receipt["runtime_merged"])
        self.assertEqual(receipt["gates"]["runtime_merge"], "REQUIRED")
        self.assertFalse(receipt["release_authorized"])
        self.assertFalse(receipt["publication_workflow_authorized"])
        self.assertEqual(receipt["canonical_writes"], 0)
        self.assertEqual(len(receipt["deterministic_sha256"]), 64)

    def test_same_contract_after_merge_is_ready_for_release_authorization_only(self):
        receipt = build_release_readiness(
            repo_root=ROOT,
            hosted_evidence=evidence(),
            expected_head_sha=HEAD,
            runtime_merged=True,
        )
        self.assertEqual(receipt["status"], "READY_FOR_RELEASE_AUTHORIZATION")
        self.assertTrue(receipt["runtime_merged"])
        self.assertEqual(receipt["gates"]["runtime_merge"], "PASS")
        self.assertFalse(receipt["release_authorized"])
        self.assertFalse(receipt["publication_workflow_authorized"])

    def test_head_drift_fails_closed(self):
        with self.assertRaises(ReleaseReadinessError) as error:
            build_release_readiness(
                repo_root=ROOT,
                hosted_evidence=evidence(head="a" * 40),
                expected_head_sha=HEAD,
                runtime_merged=False,
            )
        self.assertEqual(error.exception.code, "RELEASE_READINESS_HOSTED_HEAD_DRIFT")

    def test_missing_hosted_check_fails_closed(self):
        bad = evidence()
        bad["checks"] = bad["checks"][:-1]
        bad.pop("deterministic_sha256")
        bad["deterministic_sha256"] = sha_json(bad)
        with self.assertRaises(ReleaseReadinessError) as error:
            build_release_readiness(
                repo_root=ROOT,
                hosted_evidence=bad,
                expected_head_sha=HEAD,
                runtime_merged=False,
            )
        self.assertEqual(error.exception.code, "RELEASE_READINESS_HOSTED_CHECK_COVERAGE_INVALID")


if __name__ == "__main__":
    unittest.main(verbosity=2)
