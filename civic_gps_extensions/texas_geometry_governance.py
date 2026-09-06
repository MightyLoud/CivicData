"""Version governance for the bounded Texas legislative geometry preview."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

POLICY_ID = "texas-legislative-geometry-governance/0.1"
ACCEPTANCE = {
    "accepted_on": "2026-09-06",
    "candidate_commit": "a9994e75d9aac62ae1ae494b8984199e7477bd6a",
    "evidence_archive": "Day12_TX_Live_Controls_2026-09-06.zip",
    "evidence_archive_sha256": "f8f7d11bccd35d23496cbb3cb0f4dd82f2604bf5b3ac3d3cc7799e4eccb21a39",
}
PINS = {
    "house": {
        "plan_id": "PLANH2316",
        "authority_url": "https://data.capitol.texas.gov/dataset/planh2316",
        "tlc_resource_id": "a4d3230f-47f2-4253-85f3-51a6c3c9ad0a",
        "tlc_package_id": "71af633c-21bf-42cf-ad48-4fe95593a897",
        "tlc_revision_id": "b41261de-fc86-4290-9276-c1281d3b4139",
        "service_url": "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_State_House_Districts/FeatureServer/0",
        "service_item_id": "0627be7aa6f0440081bd750734761a63",
        "layer_name": "Texas_State_House_Districts_89th_2025_2027",
        "district_field": "DIST_NBR",
        "schema_last_edit_utc": "2025-03-17T17:36:25Z",
        "data_last_edit_utc": "2025-03-17T17:36:25Z",
        "accepted_hausdorff_m": "0.0000678642",
        "vintage_note": "Captured service polygon accepted against TLC PLANH2316 in the TLC NAD83 Lambert CRS.",
    },
    "senate": {
        "plan_id": "PLANS2168",
        "authority_url": "https://data.capitol.texas.gov/dataset/plans2168",
        "tlc_resource_id": "8247dbc6-b942-4a29-813c-1ebc603a7236",
        "tlc_package_id": "70836384-f10c-423d-a36e-748d7e000872",
        "tlc_revision_id": "ff3cee08-8f50-4092-8663-8f3f4bdde189",
        "service_url": "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_State_Senate_Districts/FeatureServer/0",
        "service_item_id": "bef1f9f8758d43378e554c09d5ed6f5c",
        "layer_name": "Texas_State_Senate_89th_Districts_89th_2025_2027",
        "district_field": "DIST_NBR",
        "schema_last_edit_utc": "2025-03-17T17:38:56Z",
        "data_last_edit_utc": "2026-02-04T18:05:32Z",
        "accepted_hausdorff_m": "0.0000676856",
        "vintage_note": (
            "The service description says 88th Legislature while the accepted layer name says 89th; "
            "the captured district-14 polygon was accepted only after comparison to TLC PLANS2168."
        ),
    },
}


class GeometryGovernanceFailure(ValueError):
    """Raised when mutable live geometry no longer matches the accepted version markers."""


def _utc_second(value):
    if type(value) not in (int, float):
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _get_json(session, url, timeout_seconds):
    response = session.get(url, params={"f": "json"}, timeout=timeout_seconds)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise GeometryGovernanceFailure("service metadata is not a JSON object")
    return body


def _service_item_id(session, layer_url, layer_body, timeout_seconds):
    value = layer_body.get("serviceItemId")
    if isinstance(value, str) and value:
        return value
    service_url = layer_url.rstrip("/").rsplit("/", 1)[0]
    return _get_json(session, service_url, timeout_seconds).get("serviceItemId")


def verify_texas_geometry_governance(*, session=None, timeout_seconds=30.0):
    """Verify mutable ArcGIS version markers before live Texas legislative routing."""
    if session is None:
        import requests
        session = requests.Session()

    observed = {}
    for chamber, pin in PINS.items():
        try:
            body = _get_json(session, pin["service_url"], timeout_seconds)
            editing = body.get("editingInfo")
            fields = body.get("fields")
            if not isinstance(editing, dict) or not isinstance(fields, list):
                raise GeometryGovernanceFailure("editingInfo/fields missing")
            field_types = {
                row.get("name"): row.get("type")
                for row in fields
                if isinstance(row, dict) and isinstance(row.get("name"), str)
            }
            actual = {
                "service_item_id": _service_item_id(session, pin["service_url"], body, timeout_seconds),
                "layer_name": body.get("name"),
                "schema_last_edit_utc": _utc_second(editing.get("schemaLastEditDate")),
                "data_last_edit_utc": _utc_second(editing.get("dataLastEditDate")),
                "district_field_type": field_types.get(pin["district_field"]),
            }
        except GeometryGovernanceFailure:
            raise
        except Exception as exc:
            raise GeometryGovernanceFailure(f"{chamber}: service metadata unavailable") from exc

        expected = {
            "service_item_id": pin["service_item_id"],
            "layer_name": pin["layer_name"],
            "schema_last_edit_utc": pin["schema_last_edit_utc"],
            "data_last_edit_utc": pin["data_last_edit_utc"],
            "district_field_type": "esriFieldTypeInteger",
        }
        mismatches = sorted(key for key, value in expected.items() if actual.get(key) != value)
        if mismatches:
            raise GeometryGovernanceFailure(
                f"{chamber}: accepted geometry version markers changed: {','.join(mismatches)}"
            )
        observed[chamber] = actual

    core = {
        "policy_id": POLICY_ID,
        "acceptance": ACCEPTANCE,
        "pins": PINS,
        "observed": observed,
    }
    receipt_sha256 = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {"status": "PASS", **core, "receipt_sha256": receipt_sha256}


def main():
    receipt = verify_texas_geometry_governance()
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
