"""Offline runtime controls for a proposed bounded Texas production overlay."""
from __future__ import annotations

import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for path in (ROOT, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.texas_geometry_governance import PINS
from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from civic_gps_legislative_overlay_test import Response, Session, package


class GovernanceSession(Session):
    def __init__(self, drift=False):
        super().__init__()
        self.drift = drift
        self.metadata_calls = []

    def get(self, url, params=None, timeout=None):
        if ("Texas_State_House" in url or "Texas_State_Senate" in url) and params == {"f": "json"}:
            self.calls.append((url, copy.deepcopy(params)))
            self.metadata_calls.append((url, copy.deepcopy(params)))
            chamber = "house" if "Texas_State_House" in url else "senate"
            schema = 1742232985031 if chamber == "house" else 1742233136000
            data = 1742232985031 if chamber == "house" else 1770228332000
            body = {
                "serviceItemId": PINS[chamber]["service_item_id"],
                "name": PINS[chamber]["layer_name"],
                "editingInfo": {"schemaLastEditDate": schema, "dataLastEditDate": data},
                "fields": [{"name": "DIST_NBR", "type": "esriFieldTypeInteger"}],
            }
            if self.drift and chamber == "house":
                body["name"] = "changed"
            return Response(body)
        return super().get(url, params=params, timeout=timeout)


class TexasActivationRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.runtime_root = Path(cls.tmp.name)
        data = b"".join(path.read_bytes() for path in sorted((ROOT / "civic_gps_runtime_parts").glob("part.*")))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(cls.runtime_root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def production_groups(self):
        groups, _ = build_texas_production_configuration(
            package(), house_division_id="test-house-49", senate_division_id="test-senate-14")
        return groups

    def test_preflight_runs_before_geocoding_and_scope_is_preserved(self):
        session = GovernanceSession()
        resolver = load_resolver_with_extensions(
            self.runtime_root, legislative_overlays=self.production_groups(), session=session)
        self.assertEqual(len(session.metadata_calls), 2)
        self.assertEqual(len(session.geocoder_calls), 0)

        result = resolver.resolve("SYNTHETIC INPUT", observed_on="2026-09-06")
        assignments = [
            row for row in result["payload"]["district_assignments"]
            if str(row.get("adapter_id", "")).startswith("DIST-TX-")
        ]
        self.assertEqual(len(assignments), 2)
        self.assertTrue(all(row["scope"] == "PRODUCTION_BOUNDED" for row in assignments))
        coverage = [
            row for row in result["payload"]["coverage"]
            if row.get("layer") == "GEO-TX-LEGISLATIVE-TWO-DISTRICTS"
        ]
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0]["scope"], "PRODUCTION_BOUNDED")
        self.assertFalse(coverage[0]["publication_eligible"])
        self.assertFalse(any(
            row.get("gap_id") == "GAP-GEO-TX-LEGISLATIVE-TWO-DISTRICTS-RELEASE"
            for row in result["payload"]["known_gaps"]
        ))

    def test_geometry_marker_drift_blocks_before_geocoding(self):
        session = GovernanceSession(drift=True)
        with self.assertRaisesRegex(ValueError, "GEOMETRY_VERSION_DRIFT"):
            load_resolver_with_extensions(
                self.runtime_root, legislative_overlays=self.production_groups(), session=session)
        self.assertEqual(len(session.geocoder_calls), 0)

    def test_policy_cannot_be_reused_with_different_geometry(self):
        groups = self.production_groups()
        groups[0]["district_adapters"][0]["service_url"] = "https://example.invalid/FeatureServer/0"
        session = GovernanceSession()
        with self.assertRaisesRegex(ValueError, "TEXAS_GEOMETRY_GOVERNANCE_BINDING_DRIFT"):
            load_resolver_with_extensions(self.runtime_root, legislative_overlays=groups, session=session)
        self.assertEqual(len(session.metadata_calls), 0)
        self.assertEqual(len(session.geocoder_calls), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
