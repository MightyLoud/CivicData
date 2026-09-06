"""Offline contract controls for the activated bounded Texas hosted runtime v0.2."""
from __future__ import annotations

import hashlib
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
from services.texas_bounded_api.runtime_v0_2 import TexasBoundedRuntimeV02
from tools.jurisdiction_package import canonical_json

HEAD = "d" * 40
ENTRY_SHA = "1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189"
GROUP_SHA = "826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a"
ACTIVATION_SHA = "8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166"


def sha_json(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class TexasPostActivationRuntimeTests(unittest.TestCase):
    def test_v02_contract_requires_activated_defaults_and_keeps_release_closed(self):
        contract = json.loads((ROOT / "services/texas_bounded_api/service_contract.v0.2.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["schema_version"], "texas-hosted-runtime-service/0.2")
        self.assertEqual(contract["profile_id"], production_profile.PROFILE_ID)
        self.assertEqual(contract["repository_activation"], "ACTIVATED_BOUNDED")
        self.assertTrue(contract["activation_authorized"])
        self.assertFalse(contract["release_authorized"])
        self.assertFalse(contract["publication_workflow_authorized"])
        self.assertEqual(contract["canonical_writes"], 0)
        self.assertEqual(contract["expected"]["catalog_entry_sha256"], ENTRY_SHA)
        self.assertEqual(contract["expected"]["legislative_group_sha256"], GROUP_SHA)
        self.assertEqual(contract["expected"]["activation_receipt_deterministic_sha256"], ACTIVATION_SHA)

    def test_default_catalog_contains_exact_certified_entry(self):
        contract = json.loads((ROOT / "services/texas_bounded_api/service_contract.v0.2.json").read_text(encoding="utf-8"))
        entries = package_catalog.load_catalog()["entries"]
        matches = [
            row for row in entries
            if row.get("profile") == "state_legislative_representation"
            and (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], contract["catalog_entry"])
        self.assertEqual(sha_json(matches[0]), ENTRY_SHA)

    def test_runtime_builds_from_activated_default_catalog_and_registry(self):
        runtime = TexasBoundedRuntimeV02.build(
            ROOT,
            head_sha=HEAD,
            environment="container-ci",
            session=GovernanceSession(),
        )
        readiness = runtime.readiness()
        self.assertEqual(readiness["status"], "PASS")
        self.assertEqual(set(readiness["checks"].values()), {"PASS"})
        service = readiness["service"]
        self.assertEqual(service["service_id"], "civicdata-tx-legislative-two-office-v0.2")
        self.assertEqual(service["schema_version"], "texas-hosted-runtime-service/0.2")
        self.assertEqual(service["head_sha"], HEAD)
        self.assertEqual(service["environment"], "container-ci")
        self.assertEqual(service["repository_activation"], "ACTIVATED_BOUNDED")
        self.assertTrue(service["activation_authorized"])
        self.assertFalse(service["release_authorized"])
        self.assertFalse(service["publication_workflow_authorized"])
        self.assertEqual(service["catalog_entry_sha256"], ENTRY_SHA)
        self.assertEqual(service["legislative_group_sha256"], GROUP_SHA)
        self.assertEqual(service["activation_receipt_deterministic_sha256"], ACTIVATION_SHA)
        self.assertEqual(service["canonical_writes"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
