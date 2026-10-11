#!/usr/bin/env python3
"""Live ArcGIS geocoder → governed polygon → EV representation smoke."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.geocoding_boundary import ArcGISWorldGeocoder
from consumers.empowered_vote.address_runtime import build_representation_for_address

STAMP = "2026-10-11T14:45:00Z"

CASES = [
    (
        "500 Cottonwood Dr, Alamosa, CO 81101",
        "ocd-division/country:us/state:co/place:alamosa/ward:1",
        "office-co-alamosa-council-ward-1",
    ),
    (
        "860 Craft Dr, Alamosa, CO 81101",
        "ocd-division/country:us/state:co/place:alamosa/ward:2",
        "office-co-alamosa-council-ward-2",
    ),
    (
        "1555 W Sixth St, Alamosa, CO 81101",
        "ocd-division/country:us/state:co/place:alamosa/ward:3",
        "office-co-alamosa-council-ward-3",
    ),
    (
        "1000 Twentieth St, Alamosa, CO 81101",
        "ocd-division/country:us/state:co/place:alamosa/ward:4",
        "office-co-alamosa-council-ward-4",
    ),
    (
        "8600 Wadsworth Boulevard, Arvada, CO 80003",
        "ocd-division/country:us/state:co/place:arvada/council_district:1",
        "office-co-arvada-council-district-1",
    ),
    (
        "7770 Pierce St, Arvada, CO 80003",
        "ocd-division/country:us/state:co/place:arvada/council_district:2",
        "office-co-arvada-council-district-2",
    ),
    (
        "12140 W 57th Ave, Arvada, CO 80002",
        "ocd-division/country:us/state:co/place:arvada/council_district:3",
        "office-co-arvada-council-district-3",
    ),
    (
        "6655 Quaker Street, Arvada, CO 80007",
        "ocd-division/country:us/state:co/place:arvada/council_district:4",
        "office-co-arvada-council-district-4",
    ),
]


def main() -> int:
    geocoder = ArcGISWorldGeocoder(timeout_seconds=30)
    for address, expected_division, expected_local_office in CASES:
        model = build_representation_for_address(
            address,
            geocoder=geocoder,
            generated_at=STAMP,
            root=ROOT,
        )
        assert model["status"] == "PASS", model
        assert model["resolved_division_ocdid"] == expected_division, model
        assert model["geocoding"]["score"] >= 95, model
        assert expected_local_office in {
            row["office_id"] for row in model["applicable_offices"]
        }, model
        assert model["canonical_writes"] == 0, model
        print(
            "PASS",
            address,
            model["geocoding"]["score"],
            model["geocoding"]["addr_type"],
            model["resolved_division_ocdid"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
