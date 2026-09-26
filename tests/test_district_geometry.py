from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_district_geometry import verify

GEOMETRY = ROOT / "data" / "geometry" / "co"


class DistrictGeometryOfflineTests(unittest.TestCase):
    def test_pinned_geometry_is_complete_and_self_consistent(self):
        result = verify(ROOT)
        self.assertTrue(result["passed"], result)
        self.assertEqual(set(result["geometry"]), {"alamosa", "arvada"})
        for city in ("alamosa", "arvada"):
            with self.subTest(city=city):
                row = result["geometry"][city]
                self.assertTrue(row["hash_ok"])
                self.assertTrue(row["district_set_ok"])
                self.assertEqual(row["districts"], ["1", "2", "3", "4"])
                self.assertEqual(row["feature_count"], 4)

    def test_all_eight_pinned_points_recompute_to_expected_district(self):
        result = verify(ROOT)
        self.assertEqual(len(result["points"]), 8)
        for row in result["points"]:
            with self.subTest(test_id=row["test_id"]):
                self.assertTrue(row["result"], row)
                self.assertEqual(
                    row["actual_district"],
                    row["expected_district"],
                )

    def test_machine_readable_sources_are_now_governed_package_evidence(self):
        result = verify(ROOT)
        for city, row in result["packages"].items():
            with self.subTest(city=city):
                self.assertTrue(row["machine_source_present"])
                self.assertTrue(row["machine_source_url_ok"])
                self.assertTrue(row["controls_bound_to_machine_source"])

    def test_geometry_archive_warnings_are_closed(self):
        result = verify(ROOT)
        for city, row in result["packages"].items():
            with self.subTest(city=city):
                self.assertTrue(row["warnings_closed"])
                self.assertTrue(row["warning_count_synced"])

    def test_manifest_records_exact_authoritative_layers_and_hashes(self):
        manifest = json.loads(
            (GEOMETRY / "district_geometry_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["sources"]["alamosa"]["layer_url"],
            "https://services2.arcgis.com/kQ9CrbL3URg6t3jo/ArcGIS/rest/services/Wards/FeatureServer/0",
        )
        self.assertEqual(
            manifest["sources"]["arvada"]["layer_url"],
            "https://services1.arcgis.com/eQyVgDz2cjhzbzN7/arcgis/rest/services/Council_Districts/FeatureServer/1",
        )
        self.assertEqual(
            manifest["sources"]["alamosa"]["geojson_sha256"],
            "1deec2550add4b6129cf2ec5b15e6c154b9d029d70376711ab36d9f12fb1e000",
        )
        self.assertEqual(
            manifest["sources"]["arvada"]["geojson_sha256"],
            "fb00b068f851899ef8446f4fc28e1bb6b74d98839a0038a82a2048df4568a491",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
