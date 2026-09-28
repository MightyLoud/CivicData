from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.electoral_geometry import FIXTURE, load_json, point_in_geometry, validate


class GovernedElectoralGeometryTests(unittest.TestCase):
    def test_governed_geometry_contract_is_green(self):
        self.assertEqual(validate(), [])

    def test_exactly_four_local_divisions_per_city(self):
        fixture = load_json(FIXTURE)
        for city, source in fixture["sources"].items():
            with self.subTest(city=city):
                self.assertEqual(source["feature_count"], 4)
                self.assertEqual(len(source["division_ids"]), 4)

    def test_all_eight_controls_reproduce_expected_division_offline(self):
        fixture = load_json(FIXTURE)
        geometries = {
            city: load_json(ROOT / source["artifact_path"])
            for city, source in fixture["sources"].items()
        }
        self.assertEqual(len(fixture["pip_controls"]), 8)
        for row in fixture["pip_controls"]:
            with self.subTest(test_id=row["test_id"]):
                matches = [
                    feature["properties"]["division_id"]
                    for feature in geometries[row["city"]]["features"]
                    if point_in_geometry(
                        row["longitude"],
                        row["latitude"],
                        feature["geometry"],
                    )
                ]
                self.assertEqual(matches, [row["expected_division_id"]])
                self.assertEqual(row["geocode_score"], 100)

    def test_machine_readable_geometry_warnings_are_resolved(self):
        for city in ("alamosa", "arvada"):
            package = json.loads(
                (
                    ROOT
                    / "data"
                    / "normalized"
                    / "co"
                    / f"jurisdiction-co-{city}"
                    / "jurisdiction.json"
                ).read_text(encoding="utf-8")
            )
            rows = [
                row
                for row in package["warnings"]
                if row["gap_type"] == "MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED"
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "RESOLVED")
            self.assertFalse(rows[0]["blocking"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
