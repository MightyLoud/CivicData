from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.civicpatch.rendered_open_data import export_rendered_roster
from consumers.empowered_vote import contract_v1, contract_v1_catalog, package_catalog

AKRON_OCDID = "ocd-jurisdiction/country:us/state:co/place:akron/government"
AKRON_DIVISION = "ocd-division/country:us/state:co/place:akron"
ADDRESS = "250 Main Avenue, Akron, CO 80720"
GPS = {
    "payload": {
        "input": {"matched_address": ADDRESS},
        "jurisdictions": [{"jurisdiction_id": "jur-us-co-akron"}],
        "district_assignments": [],
        "applicable_offices": [],
        "officeholders": [],
        "action_links": [],
    }
}
FIXTURE = ROOT / "tests/fixtures/representation/akron_civicpatch_rendered_2025-07-09.json"


class EmpoweredVoteContractV1Tests(unittest.TestCase):
    def test_shadow_catalog_builds_certified_akron_representation(self):
        model = contract_v1_catalog.build_representation_from_catalog(
            ADDRESS,
            GPS,
            repo_root=ROOT,
        )
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["consumer_gate"], "EV-RC1-SHADOW")
        self.assertEqual(
            model["package_catalog_entry_id"],
            "co-akron-municipal-representation-v0.1",
        )
        self.assertEqual(model["contract_source"], "FACTORY_PACKAGE_PROJECTION")
        self.assertEqual(model["legacy_package_schema_version"], "0.1")
        self.assertEqual(model["jurisdiction"]["jurisdiction_ocdid"], AKRON_OCDID)
        self.assertEqual(model["resolved_division_ocdid"], AKRON_DIVISION)
        self.assertEqual(model["certification"]["status"], "certified")
        self.assertEqual(model["current_holder_count"], 7)
        self.assertEqual(len(model["applicable_offices"]), 2)
        self.assertEqual(model["canonical_writes"], 0)

        offices = {row["office_id"]: row for row in model["applicable_offices"]}
        self.assertEqual(set(offices), {"office-co-akron-mayor", "office-co-akron-trustee"})
        self.assertEqual(offices["office-co-akron-mayor"]["seat_capacity"], 1)
        self.assertEqual(offices["office-co-akron-mayor"]["vacancy_count"], 0)
        self.assertEqual(offices["office-co-akron-trustee"]["seat_capacity"], 6)
        self.assertEqual(offices["office-co-akron-trustee"]["vacancy_count"], 0)

        trustees = {row["name"]: row for row in offices["office-co-akron-trustee"]["holders"]}
        self.assertEqual(
            set(trustees),
            {
                "Braden Brent",
                "Crystann Benson",
                "Jared Jefferson",
                "Joe Tarnow",
                "Ron Kraich",
                "Terry Alexander",
            },
        )
        self.assertEqual(trustees["Jared Jefferson"]["leadership_roles"], ["Mayor Pro Tem"])
        self.assertEqual(trustees["Jared Jefferson"]["term_end"], "2028")

    def test_contract_shadow_matches_legacy_voter_facing_akron_semantics(self):
        comparison = contract_v1_catalog.compare_shadow_to_legacy(
            ADDRESS,
            GPS,
            repo_root=ROOT,
        )
        self.assertEqual(comparison["status"], "PASS", comparison)
        self.assertTrue(comparison["parity_ok"], comparison)
        self.assertEqual(comparison["legacy_current_holder_count"], 7)
        self.assertEqual(comparison["contract_v1_current_holder_count"], 7)
        self.assertEqual(comparison["office_differences"], [])
        self.assertEqual(comparison["canonical_writes"], 0)

    def test_uncertified_civicpatch_render_is_not_voter_facing_authority(self):
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rendered = export_rendered_roster(
            source,
            generated_at="2025-07-09T00:16:44+00:00",
        )
        self.assertEqual(rendered["certification"]["status"], "uncertified")

        model = contract_v1.build_representation_from_civic_gps_result(
            rendered,
            ADDRESS,
            GPS,
            binding={
                "contract_jurisdiction_ocdid": AKRON_OCDID,
                "civic_gps_jurisdiction_id": "jur-us-co-akron",
            },
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CONTRACT_NOT_CERTIFIED")
        self.assertIn("CONTRACT_NOT_CERTIFIED", model["detail"])
        self.assertEqual(model["canonical_writes"], 0)

    def test_contract_graph_tampering_fails_closed(self):
        catalog = package_catalog.load_catalog()
        entry = package_catalog.select_entry(
            catalog,
            GPS,
            profile="municipal_representation",
        )
        package = package_catalog.reconstruct_package(entry, ROOT)

        from adapters.factory.export_representation import export_factory_package

        contract = export_factory_package(
            package,
            generated_at="2026-08-19T00:00:00+00:00",
            governed_package=True,
        )
        broken = copy.deepcopy(contract)
        broken["memberships"][0]["post_id"] = "00000000-0000-4000-8000-000000000000"

        model = contract_v1.build_representation_from_civic_gps_result(
            broken,
            ADDRESS,
            GPS,
            binding={
                "contract_jurisdiction_ocdid": AKRON_OCDID,
                "civic_gps_jurisdiction_id": "jur-us-co-akron",
            },
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CONTRACT_INVALID")
        self.assertIn("CONTRACT_MEMBERSHIP_POST_FK", model["detail"])
        self.assertEqual(model["canonical_writes"], 0)

    def test_certification_gate_tampering_fails_closed(self):
        catalog = package_catalog.load_catalog()
        entry = package_catalog.select_entry(
            catalog,
            GPS,
            profile="municipal_representation",
        )
        package = package_catalog.reconstruct_package(entry, ROOT)

        from adapters.factory.export_representation import export_factory_package

        contract = export_factory_package(
            package,
            generated_at="2026-08-19T00:00:00+00:00",
            governed_package=True,
        )
        contract["certification"]["parity_ok"] = False

        model = contract_v1.build_representation_from_civic_gps_result(
            contract,
            ADDRESS,
            GPS,
            binding={
                "contract_jurisdiction_ocdid": AKRON_OCDID,
                "civic_gps_jurisdiction_id": "jur-us-co-akron",
            },
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CONTRACT_INVALID")
        self.assertIn("CONTRACT_CERTIFICATION_GATES_NOT_MET", model["detail"])

    def test_inactive_civic_gps_jurisdiction_fails_closed(self):
        model = contract_v1_catalog.build_representation_from_catalog(
            ADDRESS,
            {
                "payload": {
                    "input": {"matched_address": ADDRESS},
                    "jurisdictions": [],
                    "district_assignments": [],
                }
            },
            repo_root=ROOT,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
