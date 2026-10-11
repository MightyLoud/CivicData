from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.governed_local import (
    GovernedLocalDistrictError,
    apply_governed_local_overlays,
    prepare_governed_local_overlays,
    validate_governed_local_overlay_config,
)

EXT = ROOT / "civic_gps_extensions/registry_bundles.v0.1.json"


class GovernedLocalDistrictOverlayTests(unittest.TestCase):
    def rows(self):
        extension = json.loads(EXT.read_text(encoding="utf-8"))
        return extension["governed_local_district_overlays"]

    def test_config_validates_and_snapshots_prepare(self):
        rows = self.rows()
        self.assertEqual(validate_governed_local_overlay_config(rows), [])
        prepared = prepare_governed_local_overlays(ROOT, rows)
        self.assertEqual(len(prepared), 2)
        self.assertEqual(
            {row["jurisdiction_id"] for row in prepared},
            {"jur-us-co-alamosa", "jur-us-co-arvada"},
        )

    def test_alamosa_point_yields_ward_assignment_without_civic_facts(self):
        prepared = prepare_governed_local_overlays(ROOT, self.rows())
        result = {
            "payload": {
                "jurisdictions": [
                    {"jurisdiction_id": "jur-us-co-alamosa", "name": "Alamosa"}
                ],
                "matched_divisions": [],
                "district_assignments": [],
                "evidence": [],
                "coverage": [],
                "offices": [],
                "officeholders": [],
                "applicable_offices": [],
                "action_links": [],
                "known_gaps": [],
            }
        }
        out = apply_governed_local_overlays(
            result,
            {"longitude": -105.870897502578, "latitude": 37.479843286555},
            prepared,
            observed_on="2026-10-11",
        )
        self.assertEqual(
            out["payload"]["district_assignments"],
            [{"adapter_id": "DIST-CO-ALAMOSA-WARDS-GOVERNED", "district_key": "1"}],
        )
        self.assertTrue(
            any(
                row["division_id"] == "div-us-co-alamosa-ward-1"
                for row in out["payload"]["matched_divisions"]
            )
        )
        self.assertEqual(out["payload"]["offices"], [])
        self.assertEqual(out["payload"]["officeholders"], [])
        self.assertEqual(out["payload"]["action_links"], [])

    def test_arvada_point_yields_district_four(self):
        prepared = prepare_governed_local_overlays(ROOT, self.rows())
        result = {
            "payload": {
                "jurisdictions": [
                    {"jurisdiction_id": "jur-us-co-arvada", "name": "Arvada"}
                ],
                "matched_divisions": [],
                "district_assignments": [],
                "evidence": [],
                "coverage": [],
                "known_gaps": [],
            }
        }
        out = apply_governed_local_overlays(
            result,
            {"longitude": -105.18539000544, "latitude": 39.816501932133},
            prepared,
            observed_on=None,
        )
        self.assertEqual(
            out["payload"]["district_assignments"][0],
            {"adapter_id": "DIST-CO-ARVADA-COUNCIL-GOVERNED", "district_key": "4"},
        )

    def test_outside_active_jurisdiction_polygon_fails_closed(self):
        prepared = prepare_governed_local_overlays(ROOT, self.rows())
        result = {
            "payload": {
                "jurisdictions": [{"jurisdiction_id": "jur-us-co-alamosa"}],
                "matched_divisions": [],
                "district_assignments": [],
            }
        }
        with self.assertRaisesRegex(
            GovernedLocalDistrictError,
            "GOVERNED_LOCAL_DISTRICT_NOT_RESOLVED",
        ):
            apply_governed_local_overlays(
                result,
                {"longitude": -100, "latitude": 40},
                prepared,
                observed_on=None,
            )

    def test_registry_snapshot_binding_cannot_drift(self):
        rows = self.rows()
        rows[0]["snapshot_path"] = "data/reference/co/geometry/not-real.json"
        with self.assertRaisesRegex(
            GovernedLocalDistrictError,
            "GOVERNED_LOCAL_SNAPSHOT_REGISTRY_MISMATCH",
        ):
            prepare_governed_local_overlays(ROOT, rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
