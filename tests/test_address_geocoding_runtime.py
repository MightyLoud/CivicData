from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.geocoding_boundary import (
    GeocodePolicy,
    GeocodingBoundary,
    GeocodingBoundaryError,
    select_candidate,
)
from consumers.empowered_vote.address_runtime import build_representation_for_address


class FakeProvider:
    provider_id = "FAKE"

    def __init__(self, candidates):
        self._candidates = candidates

    def find_candidates(self, address, *, max_locations):
        return list(self._candidates)[:max_locations]


def candidate(address, score, x, y, addr_type="PointAddress"):
    return {
        "address": address,
        "score": score,
        "location": {"x": x, "y": y},
        "attributes": {
            "Match_addr": address,
            "Addr_type": addr_type,
        },
    }


class AddressGeocodingRuntimeTests(unittest.TestCase):
    def test_high_confidence_point_address_passes(self):
        row = select_candidate([
            candidate(
                "500 Cottonwood Dr, Alamosa, Colorado, 81101",
                100,
                -105.870897502578,
                37.479843286555,
            )
        ])
        self.assertEqual(row["score"], 100)
        self.assertEqual(row["addr_type"], "PointAddress")
        self.assertEqual(row["candidate_count"], 1)

    def test_low_score_fails_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "GEOCODER_SCORE_BELOW_POLICY",
        ):
            select_candidate([
                candidate("weak", 80, -105, 39)
            ])

    def test_close_competing_geographies_are_ambiguous(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "AMBIGUOUS_ADDRESS",
        ):
            select_candidate([
                candidate("A", 100, -105, 39),
                candidate("B", 98, -105.1, 39.1),
            ])

    def test_duplicate_provider_labels_for_same_point_do_not_create_false_ambiguity(self):
        row = select_candidate([
            candidate("A", 100, -105, 39),
            candidate("A alternate label", 99, -105, 39),
        ])
        self.assertEqual(row["candidate_count"], 1)

    def test_unsupported_address_type_fails_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "GEOCODER_ADDRESS_TYPE_NOT_ALLOWED",
        ):
            select_candidate([
                candidate("postal", 100, -105, 39, "Postal")
            ])

    def test_empty_results_fail_closed(self):
        with self.assertRaisesRegex(
            GeocodingBoundaryError,
            "ADDRESS_NOT_MATCHED",
        ):
            select_candidate([])

    def test_policy_is_explicit_and_configurable(self):
        policy = GeocodePolicy(
            min_score=90,
            min_margin=2,
            allowed_addr_types=("PointAddress",),
            max_candidates=3,
        )
        result = GeocodingBoundary(
            FakeProvider([candidate("A", 94, -105, 39)]),
            policy=policy,
        ).resolve("A")
        self.assertEqual(result["policy"]["min_score"], 90)
        self.assertEqual(result["provider"], "FAKE")
        self.assertEqual(result["canonical_writes"], 0)

    def test_end_to_end_address_to_representatives_uses_governed_polygon(self):
        provider = FakeProvider([
            candidate(
                "500 Cottonwood Dr, Alamosa, Colorado, 81101",
                100,
                -105.870897502578,
                37.479843286555,
            )
        ])
        model = build_representation_for_address(
            "500 Cottonwood Dr, Alamosa, CO 81101",
            geocoder=provider,
            generated_at="2026-10-11T14:45:00Z",
            root=ROOT,
        )
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(
            model["resolved_division_ocdid"],
            "ocd-division/country:us/state:co/place:alamosa/ward:1",
        )
        offices = {
            row["office_id"] for row in model["applicable_offices"]
        }
        self.assertEqual(
            offices,
            {
                "office-co-alamosa-mayor",
                "office-co-alamosa-council-at-large",
                "office-co-alamosa-council-ward-1",
            },
        )
        self.assertEqual(
            model["address_resolution_source"],
            "GOVERNED_ADDRESS_GEOCODE_PIP",
        )
        self.assertEqual(
            model["governed_geography"]["resolution_source"],
            "GOVERNED_GEOMETRY_PIP",
        )
        self.assertEqual(model["canonical_writes"], 0)

    def test_geocoder_ambiguity_stops_before_geography(self):
        provider = FakeProvider([
            candidate("A", 100, -105, 39),
            candidate("B", 99, -105.2, 39.2),
        ])
        model = build_representation_for_address(
            "ambiguous",
            geocoder=provider,
            generated_at="2026-10-11T14:45:00Z",
            root=ROOT,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "AMBIGUOUS_ADDRESS")
        self.assertEqual(model["canonical_writes"], 0)

    def test_high_confidence_point_outside_governed_geometry_fails_closed(self):
        provider = FakeProvider([
            candidate("outside", 100, -100, 40)
        ])
        model = build_representation_for_address(
            "outside",
            geocoder=provider,
            generated_at="2026-10-11T14:45:00Z",
            root=ROOT,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(
            model["error"],
            "POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
