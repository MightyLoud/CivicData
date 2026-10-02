from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote.address_runtime import (
    RESOLUTION_SOURCE,
    build_representation_for_address,
)
from tools.geocoding_boundary import (
    ARCGIS_PROVIDER,
    GeocodePolicy,
    GeocodingBoundary,
    GeocodingBoundaryError,
    select_candidate,
)

ALAMOSA = ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json"
ARVADA = ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json"
STAMP = "2026-10-01T18:55:00-06:00"


class FixtureGeocoder:
    provider_id = "FIXTURE_GEOCODER"

    def __init__(self, candidates_by_address):
        self.candidates_by_address = candidates_by_address

    def find_candidates(self, address, *, max_locations):
        return self.candidates_by_address.get(address, [])[:max_locations]


def candidate(address, lon, lat, *, score=100, addr_type="PointAddress"):
    return {
        "address": address,
        "location": {"x": lon, "y": lat},
        "score": score,
        "attributes": {"Addr_type": addr_type},
    }


class GeocodingBoundaryTests(unittest.TestCase):
    def test_high_confidence_candidate_passes(self):
        result = select_candidate([
            candidate("100 Main St", -105, 39, score=100),
            candidate("100 Main St Alt", -105.1, 39.1, score=90),
        ])
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["score_margin"], 10)

    def test_weak_candidate_fails_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "GEOCODER_SCORE_BELOW_POLICY",
        ):
            select_candidate([
                candidate("100 Main St", -105, 39, score=94),
            ])

    def test_near_tie_fails_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "AMBIGUOUS_ADDRESS",
        ):
            select_candidate([
                candidate("100 Main St", -105, 39, score=100),
                candidate("100 Main St Other", -104, 39, score=98),
            ])

    def test_unsupported_match_type_fails_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "GEOCODER_ADDRESS_TYPE_NOT_ALLOWED",
        ):
            select_candidate([
                candidate(
                    "Main St, Example",
                    -105,
                    39,
                    score=100,
                    addr_type="StreetName",
                ),
            ])

    def test_invalid_coordinate_fails_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "GEOCODER_COORDINATES_INVALID",
        ):
            select_candidate([
                candidate("100 Main St", 500, 39),
            ])

    def test_exact_duplicate_candidates_do_not_create_false_ambiguity(self):
        row = candidate("100 Main St", -105, 39)
        result = select_candidate([row, dict(row)])
        self.assertEqual(result["candidate_count"], 1)
        self.assertIsNone(result["score_margin"])

    def test_policy_is_configurable(self):
        policy = GeocodePolicy(
            min_score=90,
            min_margin=2,
            allowed_addr_types=("StreetName",),
            max_candidates=3,
        )
        result = select_candidate(
            [candidate("Main St", -105, 39, score=91, addr_type="StreetName")],
            policy=policy,
        )
        self.assertEqual(result["addr_type"], "StreetName")

    def test_boundary_preserves_provider_identity_and_zero_writes(self):
        geocoder = FixtureGeocoder({
            "100 Main St": [candidate("100 Main St", -105, 39)]
        })
        result = GeocodingBoundary(geocoder).resolve("100 Main St")
        self.assertEqual(result["provider"], "FIXTURE_GEOCODER")
        self.assertEqual(result["canonical_writes"], 0)


class EndToEndAddressRepresentationTests(unittest.TestCase):
    def fixtures(self):
        mapping = {}
        expected = {}
        for package_path in (ALAMOSA, ARVADA):
            package = json.loads(package_path.read_text(encoding="utf-8"))
            native_to_ocdid = {
                row["division_id"]: row["ocd_division_id"]
                for row in package["records"]["divisions"]
            }
            for control in package["qa"]["address_tests"]:
                if control.get("coordinate_role") != "DERIVED_TEST_POINT_ONLY":
                    continue
                mapping[control["address_input"]] = [
                    candidate(
                        control["geocoded_address"],
                        control["longitude"],
                        control["latitude"],
                        score=control["coordinate_score"],
                        addr_type=control["geocode_type"],
                    )
                ]
                expected[control["address_input"]] = (
                    native_to_ocdid[control["expected_division_id"]]
                )
        return mapping, expected

    def test_all_eight_district_addresses_run_end_to_end_without_jurisdiction_hint(self):
        mapping, expected = self.fixtures()
        geocoder = FixtureGeocoder(mapping)
        self.assertEqual(len(expected), 8)
        for address, expected_division in expected.items():
            with self.subTest(address=address):
                model = build_representation_for_address(
                    address,
                    geocoder=geocoder,
                    generated_at=STAMP,
                    root=ROOT,
                )
                self.assertEqual(model["status"], "PASS", model)
                self.assertEqual(
                    model["resolved_division_ocdid"],
                    expected_division,
                )
                self.assertEqual(
                    model["address_resolution_source"],
                    RESOLUTION_SOURCE,
                )
                self.assertEqual(
                    model["governed_geography"]["division_ocdid"],
                    expected_division,
                )
                self.assertEqual(model["canonical_writes"], 0)
                self.assertGreaterEqual(len(model["applicable_offices"]), 3)

    def test_unknown_address_fails_before_geography(self):
        model = build_representation_for_address(
            "not a real test address",
            geocoder=FixtureGeocoder({}),
            generated_at=STAMP,
            root=ROOT,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "ADDRESS_NOT_MATCHED")

    def test_coordinate_outside_governed_jurisdictions_fails_closed(self):
        geocoder = FixtureGeocoder({
            "outside": [
                candidate("Outside", -100, 40, score=100)
            ]
        })
        model = build_representation_for_address(
            "outside",
            geocoder=geocoder,
            generated_at=STAMP,
            root=ROOT,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(
            model["error"],
            "POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
