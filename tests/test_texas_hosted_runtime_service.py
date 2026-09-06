"""Offline contract controls for the bounded Texas hosted runtime service."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for path in (ROOT, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from civic_gps_texas_activation_runtime_test import GovernanceSession
from consumers.empowered_vote import package_catalog, production_profile
from services.texas_bounded_api.runtime import TexasBoundedRuntime

HEAD = "c" * 40


class TexasHostedRuntimeServiceTests(unittest.TestCase):
    def test_service_contract_pins_successor_artifact_and_stays_inactive(self):
        contract = json.loads((ROOT / "services/texas_bounded_api/service_contract.v0.1.json").read_text(encoding="utf-8"))
        meta = json.loads((ROOT / "data/packages/tx/legislative/successor-package-metadata-v0.1.json").read_text(encoding="utf-8"))
        receipt = json.loads((ROOT / "data/packages/tx/legislative/acceptance-v0.1.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["schema_version"], "texas-hosted-runtime-service/0.1")
        self.assertEqual(contract["profile_id"], production_profile.PROFILE_ID)
        self.assertFalse(contract["activation_authorized"])
        self.assertEqual(contract["repository_activation"], "NOT_ACTIVATED")
        self.assertEqual(contract["canonical_writes"], 0)
        self.assertEqual(contract["expected"]["jurisdiction_json_sha256"], meta["jurisdiction_json_sha256"])
        self.assertEqual(contract["expected"]["archive_sha256"], meta["archive_sha256"])
        self.assertEqual(contract["expected"]["acceptance_receipt_sha256"], meta["acceptance_receipt_sha256"])
        self.assertEqual(contract["expected"]["acceptance_deterministic_sha256"], receipt["deterministic_sha256"])

    def test_default_catalog_remains_without_texas_profile(self):
        entries = package_catalog.load_catalog()["entries"]
        self.assertFalse(any(
            row.get("profile") == "state_legislative_representation"
            or (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
            for row in entries
        ))

    def test_runtime_builds_exact_candidate_with_governed_preflight(self):
        runtime = TexasBoundedRuntime.build(
            ROOT,
            head_sha=HEAD,
            environment="container-ci",
            session=GovernanceSession(),
        )
        try:
            readiness = runtime.readiness()
            self.assertEqual(readiness["status"], "PASS")
            self.assertEqual(set(readiness["checks"].values()), {"PASS"})
            service = readiness["service"]
            self.assertEqual(service["head_sha"], HEAD)
            self.assertEqual(service["environment"], "container-ci")
            self.assertEqual(service["profile_id"], production_profile.PROFILE_ID)
            self.assertEqual(service["repository_activation"], "NOT_ACTIVATED")
            self.assertFalse(service["activation_authorized"])
            self.assertEqual(service["canonical_writes"], 0)
            self.assertEqual(service["jurisdiction_json_sha256"], runtime.meta["jurisdiction_json_sha256"])
            self.assertEqual(service["archive_sha256"], runtime.meta["archive_sha256"])
            self.assertEqual(service["acceptance_deterministic_sha256"], runtime.receipt["deterministic_sha256"])
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
