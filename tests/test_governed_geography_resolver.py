from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.governed_geography_resolver import (
    GovernedCoordinateResolver,
    GovernedGeographyError,
    SOURCE,
)

ALAMOSA = ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json"
ARVADA = ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json"


class GovernedCoordinateResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = GovernedCoordinateResolver(root=ROOT)

    def test_all_eight_real_control_coordinates_resolve_without_expected_division_input(self):
        checked = 0
        for path in (ALAMOSA, ARVADA):
            package = json.loads(path.read_text(encoding="utf-8"))
            native_to_ocdid = {
                row["division_id"]: row["ocd_division_id"]
                for row in package["records"]["divisions"]
            }
            for control in package["qa"]["address_tests"]:
                if control.get("coordinate_role") != "DERIVED_TEST_POINT_ONLY":
                    continue
                checked += 1
                result = self.resolver.resolve(
                    jurisdiction_id=package["jurisdiction"]["jurisdiction_id"],
                    longitude=control["longitude"],
                    latitude=control["latitude"],
                )
                with self.subTest(test_id=control["test_id"]):
                    self.assertEqual(
                        result["division_ocdid"],
                        native_to_ocdid[control["expected_division_id"]],
                    )
                    self.assertEqual(result["resolution_source"], SOURCE)
                    self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(checked, 8)

    def test_can_resolve_by_jurisdiction_ocdid(self):
        result = self.resolver.resolve(
            jurisdiction_ocdid="ocd-jurisdiction/country:us/state:co/place:arvada/government",
            longitude=-105.18539000544,
            latitude=39.816501932133,
        )
        self.assertEqual(
            result["division_ocdid"],
            "ocd-division/country:us/state:co/place:arvada/council_district:4",
        )

    def test_civic_gps_payload_uses_runtime_resolved_division_as_binding(self):
        gps, binding = self.resolver.civic_gps_payload(
            address="500 Cottonwood Dr, Alamosa, CO 81101",
            matched_address="500 Cottonwood Dr, Alamosa, Colorado, 81101",
            longitude=-105.870897502578,
            latitude=37.479843286555,
            jurisdiction_id="jurisdiction-co-alamosa",
        )
        assignment = gps["payload"]["district_assignments"][0]
        self.assertEqual(
            assignment["district_key"],
            "ocd-division/country:us/state:co/place:alamosa/ward:1",
        )
        self.assertEqual(
            binding["district_division_map"][assignment["district_key"]],
            assignment["district_key"],
        )

    def test_unknown_jurisdiction_fails_closed(self):
        with self.assertRaisesRegex(
            GovernedGeographyError,
            "GOVERNED_GEOMETRY_JURISDICTION_UNKNOWN",
        ):
            self.resolver.resolve(
                jurisdiction_id="jurisdiction-co-missing",
                longitude=-105.0,
                latitude=39.0,
            )

    def test_outside_point_fails_closed(self):
        with self.assertRaisesRegex(
            GovernedGeographyError,
            "POINT_OUTSIDE_GOVERNED_GEOMETRY",
        ):
            self.resolver.resolve(
                jurisdiction_id="jurisdiction-co-alamosa",
                longitude=-100,
                latitude=40,
            )

    def test_selector_must_be_exactly_one_identity(self):
        with self.assertRaisesRegex(
            GovernedGeographyError,
            "JURISDICTION_SELECTOR_INVALID",
        ):
            self.resolver.resolve(
                longitude=-105,
                latitude=39,
            )
        with self.assertRaisesRegex(
            GovernedGeographyError,
            "JURISDICTION_SELECTOR_INVALID",
        ):
            self.resolver.resolve(
                jurisdiction_id="jurisdiction-co-alamosa",
                jurisdiction_ocdid="ocd-jurisdiction/country:us/state:co/place:alamosa/government",
                longitude=-105,
                latitude=39,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
