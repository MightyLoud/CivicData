#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import (
    _load_extension,
    load_registry_with_extensions,
)
from civic_gps_extensions.local_geometry import (
    GovernedLocalDistrictError,
    apply_governed_local_district_overlays,
    prepare_governed_local_district_overlays,
)

EXTENSION = ROOT / "civic_gps_extensions" / "registry_bundles.v0.1.json"


class GovernedLocalDistrictOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extension = _load_extension(EXTENSION)
        cls.overlays = prepare_governed_local_district_overlays(
            ROOT,
            cls.extension["governed_local_district_overlays"],
        )

    def test_merged_registry_contains_sixteen_bundles_without_mutating_packed_runtime(self):
        merged, _ = load_registry_with_extensions(ROOT)
        self.assertEqual(len(merged["bundles"]), 16)
        self.assertEqual(
            {
                row["adapter_id"]
                for row in merged["bundles"]
                if row["adapter_id"] in {
                    "BASE-CO-ALAMOSA",
                    "BASE-CO-ARVADA",
                }
            },
            {"BASE-CO-ALAMOSA", "BASE-CO-ARVADA"},
        )

    def test_all_configured_snapshots_prepare(self):
        self.assertEqual(
            {row["overlay_id"] for row in self.overlays},
            {
                "DIST-CO-ALAMOSA-WARD",
                "DIST-CO-ARVADA-COUNCIL",
            },
        )
        for row in self.overlays:
            self.assertEqual(
                len(row["_snapshot"]["feature_collection"]["features"]),
                4,
            )

    def test_known_alamosa_point_resolves_from_archived_polygon(self):
        result = {
            "payload": {
                "jurisdictions": [
                    {"jurisdiction_id": "jur-us-co-alamosa"}
                ],
                "district_assignments": [],
                "matched_divisions": [],
                "evidence": [],
                "coverage": [],
                "known_gaps": [],
            }
        }
        out = apply_governed_local_district_overlays(
            result,
            {
                "longitude": -105.870897502578,
                "latitude": 37.479843286555,
            },
            self.overlays,
            observed_on="2026-09-26",
        )
        self.assertEqual(
            out["payload"]["district_assignments"],
            [{
                "adapter_id": "DIST-CO-ALAMOSA-WARD",
                "district_key": "1",
            }],
        )
        self.assertEqual(
            out["payload"]["matched_divisions"][0]["division_id"],
            "div-us-co-alamosa-ward-1",
        )

    def test_known_arvada_point_resolves_from_archived_polygon(self):
        result = {
            "payload": {
                "jurisdictions": [
                    {"jurisdiction_id": "jur-us-co-arvada"}
                ],
                "district_assignments": [],
                "matched_divisions": [],
                "evidence": [],
                "coverage": [],
                "known_gaps": [],
            }
        }
        out = apply_governed_local_district_overlays(
            result,
            {
                "longitude": -105.18539000544,
                "latitude": 39.816501932133,
            },
            self.overlays,
            observed_on="2026-09-26",
        )
        self.assertEqual(
            out["payload"]["district_assignments"],
            [{
                "adapter_id": "DIST-CO-ARVADA-COUNCIL",
                "district_key": "4",
            }],
        )

    def test_inactive_jurisdiction_does_not_receive_assignment(self):
        result = {
            "payload": {
                "jurisdictions": [
                    {"jurisdiction_id": "jur-us-co-akron"}
                ],
                "district_assignments": [],
                "matched_divisions": [],
                "evidence": [],
                "coverage": [],
                "known_gaps": [],
            }
        }
        out = apply_governed_local_district_overlays(
            result,
            {"longitude": -105.87, "latitude": 37.48},
            self.overlays,
        )
        self.assertEqual(out["payload"]["district_assignments"], [])

    def test_outside_active_geometry_fails_adapter_closed(self):
        result = {
            "payload": {
                "jurisdictions": [
                    {"jurisdiction_id": "jur-us-co-alamosa"}
                ],
                "district_assignments": [],
                "matched_divisions": [],
                "evidence": [],
                "coverage": [],
                "known_gaps": [],
            }
        }
        out = apply_governed_local_district_overlays(
            result,
            {"longitude": -104.0, "latitude": 39.0},
            self.overlays,
        )
        self.assertEqual(out["payload"]["district_assignments"], [])
        self.assertEqual(
            out["payload"]["known_gaps"][0]["status"],
            "CONFLICT",
        )
        self.assertIn(
            "POINT_OUTSIDE_GOVERNED_GEOMETRY",
            out["payload"]["known_gaps"][0]["summary"],
        )

    def test_coordinate_resolver_returns_geography_only_payload(self):
        from civic_gps_extensions.loader import (
            CivicGPSBoundaryOverlayResolver,
        )

        class FakeEngine:
            pass

        resolver = CivicGPSBoundaryOverlayResolver(
            FakeEngine(),
            [],
            [],
            self.overlays,
        )
        result = resolver.resolve_governed_local_coordinate(
            "jur-us-co-arvada",
            longitude=-105.18539000544,
            latitude=39.816501932133,
            observed_on="2026-09-26",
        )
        self.assertNotIn("error", result)
        self.assertEqual(
            result["payload"]["district_assignments"],
            [{
                "adapter_id": "DIST-CO-ARVADA-COUNCIL",
                "district_key": "4",
            }],
        )
        self.assertEqual(result["payload"]["offices"], [])
        self.assertEqual(result["payload"]["officeholders"], [])
        self.assertEqual(result["payload"]["action_links"], [])

    def test_registry_snapshot_path_drift_fails_before_runtime(self):
        rows = deepcopy(
            self.extension["governed_local_district_overlays"]
        )
        rows[0]["snapshot_path"] = (
            "data/reference/co/geometry/not-the-governed-snapshot.json"
        )
        with self.assertRaisesRegex(
            GovernedLocalDistrictError,
            "LOCAL_DISTRICT_REGISTRY_SNAPSHOT_MISMATCH",
        ):
            prepare_governed_local_district_overlays(ROOT, rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
