from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import contract_v1_catalog

MARKET = "747 Market Street, Tacoma, WA 98402"
SHERIDAN = "6500 South Sheridan Avenue, Tacoma, WA 98408"


def gps(address: str, district: str | None) -> dict:
    assignments = [
        {"adapter_id": "DIST-WA-PIERCE-COUNCIL", "district_key": "4"},
    ]
    if district is not None:
        assignments.append(
            {"adapter_id": "DIST-WA-TACOMA-COUNCIL", "district_key": district}
        )
    return {
        "payload": {
            "input": {"matched_address": address.upper()},
            "jurisdictions": [
                {"jurisdiction_id": "jur-us-wa-pierce"},
                {"jurisdiction_id": "jur-us-wa-tacoma"},
            ],
            "district_assignments": assignments,
            "applicable_offices": [{"office_id": "poison"}],
            "officeholders": [{"person_id": "poison"}],
            "action_links": [{"label": "poison"}],
        }
    }


class EmpoweredVoteContractV1TacomaTests(unittest.TestCase):
    def build(self, address: str, district: str) -> dict:
        return contract_v1_catalog.build_representation_from_catalog(
            address,
            gps(address, district),
            repo_root=ROOT,
            profile="municipal_essentials",
        )

    def test_district_two_shadow_matches_legacy_representation(self):
        comparison = contract_v1_catalog.compare_shadow_to_legacy(
            MARKET,
            gps(MARKET, "2"),
            repo_root=ROOT,
            profile="municipal_essentials",
        )
        self.assertEqual(comparison["status"], "PASS", comparison)
        self.assertTrue(comparison["parity_ok"], comparison)
        self.assertEqual(comparison["office_differences"], [])
        self.assertEqual(comparison["canonical_writes"], 0)

    def test_district_five_shadow_matches_legacy_representation(self):
        comparison = contract_v1_catalog.compare_shadow_to_legacy(
            SHERIDAN,
            gps(SHERIDAN, "5"),
            repo_root=ROOT,
            profile="municipal_essentials",
        )
        self.assertEqual(comparison["status"], "PASS", comparison)
        self.assertTrue(comparison["parity_ok"], comparison)
        self.assertEqual(comparison["office_differences"], [])
        self.assertEqual(comparison["canonical_writes"], 0)

    def test_district_two_contains_citywide_plus_one_district_office(self):
        model = self.build(MARKET, "2")
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["package_catalog_entry_id"], "wa-tacoma-municipal-essentials-v0.2")
        self.assertEqual(model["legacy_package_schema_version"], "0.2")
        self.assertEqual(model["certification"]["status"], "certified")
        self.assertEqual(model["district_assignments"]["DIST-WA-TACOMA-COUNCIL"], "2")
        self.assertEqual(len(model["applicable_offices"]), 6)
        self.assertTrue(
            any(
                row["division_ocdid"].endswith("/council_district:2")
                or row["division_ocdid"].endswith("/council_district:02")
                for row in model["applicable_offices"]
            ),
            model["applicable_offices"],
        )
        self.assertEqual(model["canonical_writes"], 0)

    def test_switching_district_changes_only_district_scoped_office(self):
        district_two = self.build(MARKET, "2")
        district_five = self.build(SHERIDAN, "5")
        self.assertEqual(district_two["status"], "PASS", district_two)
        self.assertEqual(district_five["status"], "PASS", district_five)

        by_division_two = {
            row["office_id"]: row["division_ocdid"]
            for row in district_two["applicable_offices"]
        }
        by_division_five = {
            row["office_id"]: row["division_ocdid"]
            for row in district_five["applicable_offices"]
        }
        common = set(by_division_two) & set(by_division_five)
        same = {office_id for office_id in common if by_division_two[office_id] == by_division_five[office_id]}
        changed = {office_id for office_id in common if by_division_two[office_id] != by_division_five[office_id]}

        # Five citywide offices remain stable. One district-scoped council seat differs.
        self.assertEqual(len(same), 5)
        self.assertEqual(len(changed), 0)
        district_two_only = set(by_division_two) - set(by_division_five)
        district_five_only = set(by_division_five) - set(by_division_two)
        self.assertEqual(len(district_two_only), 1)
        self.assertEqual(len(district_five_only), 1)

    def test_missing_tacoma_district_fails_closed(self):
        model = contract_v1_catalog.build_representation_from_catalog(
            MARKET,
            gps(MARKET, None),
            repo_root=ROOT,
            profile="municipal_essentials",
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CIVIC_GPS_REQUIRED_DISTRICT_MISSING")
        self.assertEqual(model["canonical_writes"], 0)

    def test_unknown_tacoma_district_fails_closed(self):
        model = self.build(MARKET, "99")
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertIn(
            model["error"],
            {"CONTRACT_V1_DIVISION_CROSSWALK_MISSING", "CIVIC_GPS_DISTRICT_NOT_IN_CONTRACT"},
        )
        self.assertEqual(model["canonical_writes"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
