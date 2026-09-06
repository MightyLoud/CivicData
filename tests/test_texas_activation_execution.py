"""Post-activation verification for the bounded Texas catalog + registry route."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile
from tools.jurisdiction_package import canonical_json

ENTRY_SHA = "1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189"
GROUP_SHA = "826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a"
PACKAGE_SHA = "a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530"
ACTIVATION_SHA = "8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166"
GROUP_ID = "GEO-TX-LEGISLATIVE-TWO-DISTRICTS"


def sha_json(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TexasActivationExecutionTests(unittest.TestCase):
    def test_exact_certified_catalog_and_registry_objects_are_active(self):
        contract = read_json(ROOT / "services/texas_bounded_api/service_contract.v0.1.json")
        catalog = package_catalog.load_catalog()
        matches = [
            row for row in catalog["entries"]
            if row.get("profile") == "state_legislative_representation"
            and (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
        ]
        self.assertEqual(len(matches), 1)
        entry = matches[0]
        self.assertEqual(entry, contract["catalog_entry"])
        self.assertEqual(sha_json(entry), ENTRY_SHA)

        package = package_catalog.reconstruct_package(entry, ROOT)
        self.assertEqual(sha_json(package), PACKAGE_SHA)
        identities = {
            str(row.get("identity_resolution_status") or row.get("person_status") or "").upper()
            for row in package["records"]["people"]
        }
        self.assertEqual(identities, {"AUTHORITATIVE"})

        divisions = {row["division_kind"]: row["division_id"] for row in package["records"]["divisions"]}
        groups, bindings = build_texas_production_configuration(
            package,
            house_division_id=divisions["SLDL"],
            senate_division_id=divisions["SLDU"],
        )
        self.assertEqual({row["binding_id"] for row in bindings}, {"tx-house", "tx-senate"})
        expected_group = groups[0]
        self.assertEqual(sha_json(expected_group), GROUP_SHA)

        registry = read_json(ROOT / "civic_gps_extensions/registry_bundles.v0.1.json")
        active_groups = [row for row in registry.get("legislative_boundary_overlays", []) if row.get("group_id") == GROUP_ID]
        self.assertEqual(len(active_groups), 1)
        self.assertEqual(active_groups[0], expected_group)
        self.assertEqual(active_groups[0]["scope"], "PRODUCTION_BOUNDED")
        self.assertFalse(active_groups[0]["publication_eligible"])

    def test_activation_receipt_binds_authorized_repository_mutations_only(self):
        receipt = read_json(ROOT / "data/packages/tx/legislative/activation-v0.1.json")
        recorded = receipt["deterministic_sha256"]
        core = dict(receipt)
        core.pop("deterministic_sha256")
        self.assertEqual(sha_json(core), recorded)
        self.assertEqual(recorded, ACTIVATION_SHA)
        self.assertEqual(receipt["status"], "ACTIVATED_BOUNDED")
        self.assertTrue(receipt["activation_authorized"])
        self.assertEqual(receipt["repository_activation"], "ACTIVATED_BOUNDED")
        self.assertTrue(receipt["activation"]["default_catalog_mutation"])
        self.assertTrue(receipt["activation"]["default_registry_mutation"])
        self.assertFalse(receipt["boundaries"]["merge_authorized"])
        self.assertFalse(receipt["boundaries"]["release_authorized"])
        self.assertFalse(receipt["boundaries"]["publication_workflow_authorized"])
        self.assertFalse(receipt["boundaries"]["railway_redeploy_authorized"])
        self.assertEqual(receipt["boundaries"]["canonical_writes"], 0)
        self.assertEqual(receipt["inputs"]["catalog_entry_sha256"], ENTRY_SHA)
        self.assertEqual(receipt["inputs"]["legislative_group_sha256"], GROUP_SHA)
        self.assertEqual(receipt["inputs"]["package_sha256"], PACKAGE_SHA)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TexasActivationExecutionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(json.dumps({
        "status": "PASS",
        "repository_activation": "ACTIVATED_BOUNDED",
        "catalog_entry_sha256": ENTRY_SHA,
        "legislative_group_sha256": GROUP_SHA,
        "activation_receipt_sha256": ACTIVATION_SHA,
        "merge": "NOT_AUTHORIZED",
        "release": "NOT_AUTHORIZED",
        "canonical_writes": 0,
    }, sort_keys=True))
