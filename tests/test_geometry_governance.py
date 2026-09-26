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
ALAMOSA_GEOMETRY = ROOT / "data/reference/co/geometry/alamosa_wards_2023_v0.1.json"
ARVADA_GEOMETRY = ROOT / "data/reference/co/geometry/arvada_council_districts_2023_v0.1.json"
ALAMOSA_PACKAGE = ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json"
ARVADA_PACKAGE = ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json"


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

    def test_source_registry_resolves_both_governed_geometry_snapshots(self):
        registry = load_source_registry(REGISTRY)
        self.assertEqual(validate_source_registry(registry), [])
        expected = {
            "jurisdiction-co-alamosa": (
                "https://services2.arcgis.com/kQ9CrbL3URg6t3jo/arcgis/rest/services/Wards/FeatureServer/0",
                "data/reference/co/geometry/alamosa_wards_2023_v0.1.json",
            ),
            "jurisdiction-co-arvada": (
                "https://services1.arcgis.com/eQyVgDz2cjhzbzN7/arcgis/rest/services/Council_Districts/FeatureServer/1",
                "data/reference/co/geometry/arvada_council_districts_2023_v0.1.json",
            ),
        }
        for jurisdiction_id, (url, snapshot_path) in expected.items():
            with self.subTest(jurisdiction_id=jurisdiction_id):
                row = assert_registry_snapshot_ready(registry, jurisdiction_id)
                self.assertEqual(
                    row["machine_source_status"],
                    "RESOLVED_MACHINE_READABLE",
                )
                self.assertEqual(row["machine_source_url"], url)
                self.assertEqual(row["governed_snapshot_path"], snapshot_path)
                self.assertIsNone(row["blocker_code"])

    def test_real_alamosa_and_arvada_snapshots_validate(self):
        for path in (ALAMOSA_GEOMETRY, ARVADA_GEOMETRY):
            with self.subTest(path=path.name):
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(validate_geometry_snapshot(snapshot), [])
                self.assertEqual(
                    len(snapshot["feature_collection"]["features"]),
                    4,
                )

    def test_eight_real_district_control_points_resolve_to_expected_polygons(self):
        cases = (
            (ALAMOSA_PACKAGE, ALAMOSA_GEOMETRY),
            (ARVADA_PACKAGE, ARVADA_GEOMETRY),
        )
        checked = 0
        for package_path, geometry_path in cases:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            snapshot = json.loads(geometry_path.read_text(encoding="utf-8"))
            native_to_ocdid = {
                row["division_id"]: row["ocd_division_id"]
                for row in package["records"]["divisions"]
                if row.get("division_id") and row.get("ocd_division_id")
            }
            for control in package["qa"]["address_tests"]:
                if control.get("coordinate_role") != "DERIVED_TEST_POINT_ONLY":
                    continue
                checked += 1
                expected = native_to_ocdid[control["expected_division_id"]]
                actual = resolve_point(
                    snapshot,
                    x=float(control["longitude"]),
                    y=float(control["latitude"]),
                )
                with self.subTest(test_id=control["test_id"]):
                    self.assertEqual(actual, expected)
                    self.assertEqual(
                        control["coordinate_source"],
                        "ESRI_WORLD_GEOCODER",
                    )
                    self.assertEqual(control["coordinate_score"], 100)
        self.assertEqual(checked, 8)

    def test_registry_forbids_claiming_resolved_without_snapshot_and_url(self):
        registry = load_source_registry(REGISTRY)
        row = registry["entries"][0]
        row["machine_source_status"] = "RESOLVED_MACHINE_READABLE"
        row["machine_source_url"] = None
        row["governed_snapshot_path"] = None
        row["blocker_code"] = None
        self.assertIn(
            "RESOLVED_MACHINE_SOURCE_FIELDS_REQUIRED",
            validate_source_registry(registry),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
