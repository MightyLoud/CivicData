from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.geometry_governance import (
    GeometryGovernanceError,
    assert_registry_snapshot_ready,
    geometry_contains,
    load_source_registry,
    resolve_point,
    validate_geometry_snapshot,
    validate_source_registry,
)

REGISTRY = ROOT / "data/reference/co/district_geometry_sources_v0.1.json"
FIXTURE = ROOT / "acceptance/geometry/synthetic_four_districts_v0.1.json"


class GeometryGovernanceTests(unittest.TestCase):
    def fixture(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_synthetic_snapshot_validates_and_covers_all_divisions(self):
        snapshot = self.fixture()
        self.assertEqual(validate_geometry_snapshot(snapshot), [])
        self.assertEqual(
            resolve_point(snapshot, x=0.5, y=1.5),
            "ocd-division/country:us/state:zz/place:synthetic/district:1",
        )
        self.assertEqual(
            resolve_point(snapshot, x=1.5, y=1.5),
            "ocd-division/country:us/state:zz/place:synthetic/district:2",
        )
        self.assertEqual(
            resolve_point(snapshot, x=0.5, y=0.5),
            "ocd-division/country:us/state:zz/place:synthetic/district:3",
        )
        self.assertEqual(
            resolve_point(snapshot, x=1.5, y=0.5),
            "ocd-division/country:us/state:zz/place:synthetic/district:4",
        )

    def test_boundary_points_are_inclusive_but_ambiguous_shared_edges_fail(self):
        snapshot = self.fixture()
        with self.assertRaisesRegex(
            GeometryGovernanceError,
            "POINT_GEOMETRY_AMBIGUOUS",
        ):
            resolve_point(snapshot, x=1.0, y=1.5)

    def test_point_outside_geometry_fails_closed(self):
        with self.assertRaisesRegex(
            GeometryGovernanceError,
            "POINT_OUTSIDE_GOVERNED_GEOMETRY",
        ):
            resolve_point(self.fixture(), x=10, y=10)

    def test_polygon_holes_are_respected(self):
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [[0,0],[4,0],[4,4],[0,4],[0,0]],
                [[1,1],[3,1],[3,3],[1,3],[1,1]],
            ],
        }
        self.assertTrue(geometry_contains(geometry, (0.5, 0.5)))
        self.assertFalse(geometry_contains(geometry, (2, 2)))
        self.assertTrue(geometry_contains(geometry, (1, 2)))

    def test_missing_division_feature_fails_validation(self):
        snapshot = self.fixture()
        snapshot["feature_collection"]["features"].pop()
        self.assertIn(
            "GEOMETRY_DIVISION_COVERAGE_INCOMPLETE",
            validate_geometry_snapshot(snapshot),
        )

    def test_duplicate_division_feature_fails_validation(self):
        snapshot = self.fixture()
        snapshot["feature_collection"]["features"].append(
            deepcopy(snapshot["feature_collection"]["features"][0])
        )
        self.assertIn(
            "GEOMETRY_FEATURE_DIVISION_DUPLICATE",
            validate_geometry_snapshot(snapshot),
        )

    def test_source_registry_is_valid_and_fail_closed_for_both_current_blockers(self):
        registry = load_source_registry(REGISTRY)
        self.assertEqual(validate_source_registry(registry), [])
        by_id = {
            row["jurisdiction_id"]: row
            for row in registry["entries"]
        }
        self.assertEqual(
            by_id["jurisdiction-co-alamosa"]["machine_source_status"],
            "UNRESOLVED_ENDPOINT",
        )
        self.assertEqual(
            by_id["jurisdiction-co-arvada"]["machine_source_status"],
            "UNRESOLVED_ENDPOINT",
        )
        with self.assertRaisesRegex(
            GeometryGovernanceError,
            "ALAMOSA_WARD_MACHINE_SOURCE_UNRESOLVED",
        ):
            assert_registry_snapshot_ready(
                registry,
                "jurisdiction-co-alamosa",
            )
        with self.assertRaisesRegex(
            GeometryGovernanceError,
            "ARVADA_COUNCIL_DISTRICT_MACHINE_SOURCE_UNRESOLVED",
        ):
            assert_registry_snapshot_ready(
                registry,
                "jurisdiction-co-arvada",
            )

    def test_registry_forbids_claiming_resolved_without_snapshot_and_url(self):
        registry = load_source_registry(REGISTRY)
        row = registry["entries"][0]
        row["machine_source_status"] = "RESOLVED_MACHINE_READABLE"
        row["blocker_code"] = ""
        self.assertIn(
            "RESOLVED_MACHINE_SOURCE_FIELDS_REQUIRED",
            validate_source_registry(registry),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
