#!/usr/bin/env python3
"""Diagnostic-only probe for a Census-geocoder-compatible Arvada District 3 control."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import load_resolver_with_extensions
from tools.geocoding_boundary import ArcGISWorldGeocoder, GeocodingBoundary

CANDIDATES = [
    "12140 W 57th Ave, Arvada, CO 80002",
    "10664 W 58th Ave, Arvada, CO 80002",
    "11200 W 58th Ave, Arvada, CO 80002",
    "5881 Miller St, Arvada, CO 80002",
    "10275 W 55th Ave, Arvada, CO 80002",
]

EXPECTED_JURISDICTION = "jur-us-co-arvada"
EXPECTED_ADAPTER = "DIST-CO-ARVADA-COUNCIL"
EXPECTED_KEY = "3"


def main() -> int:
    resolver = load_resolver_with_extensions(ROOT, timeout_seconds=30.0)
    arcgis = GeocodingBoundary(ArcGISWorldGeocoder(timeout_seconds=30.0))
    rows = []
    for address in CANDIDATES:
        result = resolver.resolve(address, observed_on=None)
        row = {"address": address}
        if "error" in result:
            row.update({"status": "ERROR", "error": result["error"]})
        else:
            payload = result["payload"]
            jurisdictions = sorted(
                item["jurisdiction_id"]
                for item in payload.get("jurisdictions", [])
                if item.get("jurisdiction_id")
            )
            assignments = {
                item["adapter_id"]: str(item["district_key"])
                for item in payload.get("district_assignments", [])
                if item.get("adapter_id")
            }
            row.update({
                "status": "PASS",
                "jurisdictions": jurisdictions,
                "district_key": assignments.get(EXPECTED_ADAPTER),
                "district3_eligible": (
                    EXPECTED_JURISDICTION in jurisdictions
                    and assignments.get(EXPECTED_ADAPTER) == EXPECTED_KEY
                ),
            })
        try:
            row["arcgis"] = arcgis.resolve(address)
        except Exception as exc:
            row["arcgis_error"] = str(exc)
        rows.append(row)

    print(json.dumps({"probe": "ARVADA_DISTRICT3_ADDRESS", "results": rows}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
