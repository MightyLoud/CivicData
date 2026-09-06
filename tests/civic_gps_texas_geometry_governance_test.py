"""Offline controls for the bounded Texas geometry-version governance contract."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.texas_geometry_governance import (
    ACCEPTANCE,
    GeometryGovernanceFailure,
    PINS,
    POLICY_ID,
    verify_texas_geometry_governance,
)


def metadata(chamber):
    pin = PINS[chamber]
    schema = 1742232985031 if chamber == "house" else 1742233136000
    data = 1742232985031 if chamber == "house" else 1770228332000
    return {
        "serviceItemId": pin["service_item_id"],
        "name": pin["layer_name"],
        "editingInfo": {"schemaLastEditDate": schema, "dataLastEditDate": data},
        "fields": [{"name": pin["district_field"], "type": "esriFieldTypeInteger"}],
    }


class Response:
    def __init__(self, body):
        self.body = copy.deepcopy(body)

    def raise_for_status(self):
        pass

    def json(self):
        return copy.deepcopy(self.body)


class Session:
    def __init__(self):
        self.bodies = {chamber: metadata(chamber) for chamber in PINS}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, copy.deepcopy(params), timeout))
        chamber = "house" if "House" in url else "senate" if "Senate" in url else None
        if chamber is None:
            raise AssertionError("unexpected URL: " + url)
        return Response(self.bodies[chamber])


class TexasGeometryGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.session = Session()

    def test_pass_receipt_is_deterministic_and_bound_to_acceptance(self):
        first = verify_texas_geometry_governance(session=self.session)
        second = verify_texas_geometry_governance(session=Session())
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(first["policy_id"], POLICY_ID)
        self.assertEqual(first["acceptance"], ACCEPTANCE)
        self.assertEqual(len(first["receipt_sha256"]), 64)
        self.assertEqual(len(self.session.calls), 2)
        self.assertTrue(all(call[1] == {"f": "json"} for call in self.session.calls))

    def test_service_item_drift_fails_closed(self):
        self.session.bodies["house"]["serviceItemId"] = "changed"
        with self.assertRaisesRegex(GeometryGovernanceFailure, "service_item_id"):
            verify_texas_geometry_governance(session=self.session)

    def test_layer_name_drift_fails_closed(self):
        self.session.bodies["senate"]["name"] = "changed"
        with self.assertRaisesRegex(GeometryGovernanceFailure, "layer_name"):
            verify_texas_geometry_governance(session=self.session)

    def test_data_edit_drift_fails_closed(self):
        self.session.bodies["senate"]["editingInfo"]["dataLastEditDate"] += 1000
        with self.assertRaisesRegex(GeometryGovernanceFailure, "data_last_edit_utc"):
            verify_texas_geometry_governance(session=self.session)

    def test_schema_edit_drift_fails_closed(self):
        self.session.bodies["house"]["editingInfo"]["schemaLastEditDate"] += 1000
        with self.assertRaisesRegex(GeometryGovernanceFailure, "schema_last_edit_utc"):
            verify_texas_geometry_governance(session=self.session)

    def test_district_field_type_drift_fails_closed(self):
        self.session.bodies["house"]["fields"][0]["type"] = "esriFieldTypeString"
        with self.assertRaisesRegex(GeometryGovernanceFailure, "district_field_type"):
            verify_texas_geometry_governance(session=self.session)

    def test_missing_metadata_fails_closed(self):
        self.session.bodies["house"].pop("editingInfo")
        with self.assertRaises(GeometryGovernanceFailure):
            verify_texas_geometry_governance(session=self.session)


if __name__ == "__main__":
    unittest.main()
