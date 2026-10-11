#!/usr/bin/env python3
"""Diagnostic-only probe for a Census-geocoder-compatible Alamosa Ward 4 control."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import load_resolver_with_extensions
from tools.geocoding_boundary import ArcGISWorldGeocoder, GeocodingBoundary

CANDIDATES = [
    "1000 Twentieth St, Alamosa, CO 81101",
    "1000 20th St, Alamosa, CO 81101",
    "1000 Twentieth Street, Alamosa, CO 81101",
    "1000 20th Street, Alamosa, CO 81101",
    "1000 20th St, Alamosa, CO",
    "2222 Old Sanford Rd, Alamosa, CO 81101",
    "2242 Old Sanford Rd, Alamosa, CO 81101",
    "2190 State Ave, Alamosa, CO 81101",
]

EXPECTED_JURISDICTION = "jur-us-co-alamosa"
EXPECTED_ADAPTER = "DIST-CO-ALAMOSA-WARD"
EXPECTED_KEY = "4"


def main() -> int:
    resolver = load_resolver_with_extensions(ROOT, timeout_seconds=30.0)
    rows = []
    for address in CANDIDATES:
        result = resolver.resolve(address, observed_on=None)
        if "error" in result:
            rows.append({
                "address": address,
                "status": "ERROR",
                "error": result["error"],
            })
            continue
        payload = result["payload"]
        jurisdictions = sorted(
            row["jurisdiction_id"]
            for row in payload.get("jurisdictions", [])
            if row.get("jurisdiction_id")
        )
        assignments = {
            row["adapter_id"]: str(row["district_key"])
            for row in payload.get("district_assignments", [])
            if row.get("adapter_id")
        }
        rows.append({
            "address": address,
            "status": "PASS",
            "jurisdictions": jurisdictions,
            "district_key": assignments.get(EXPECTED_ADAPTER),
            "ward4_eligible": (
                EXPECTED_JURISDICTION in jurisdictions
                and assignments.get(EXPECTED_ADAPTER) == EXPECTED_KEY
            ),
        })
    arcgis = GeocodingBoundary(ArcGISWorldGeocoder(timeout_seconds=30.0))
    arcgis_result = arcgis.resolve("2190 State Ave, Alamosa, CO 81101")
    print(json.dumps({
        "probe": "ALAMOSA_WARD4_ADDRESS",
        "results": rows,
        "arcgis_selected_control": arcgis_result,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
