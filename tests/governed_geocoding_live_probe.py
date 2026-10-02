#!/usr/bin/env python3
"""Live ArcGIS geocoder -> governed PIP -> EV representation probe."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote.address_runtime import (
    RESOLUTION_SOURCE,
    build_representation_for_address,
)
from tools.geocoding_boundary import (
    ARCGIS_PROVIDER,
    ArcGISWorldGeocoder,
    GeocodePolicy,
)

PACKAGES = (
    ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
    ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
)
STAMP = "2026-10-01T18:55:00-06:00"


def main() -> int:
    geocoder = ArcGISWorldGeocoder(timeout_seconds=30.0)
    policy = GeocodePolicy()
    results = []

    for package_path in PACKAGES:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        native_to_ocdid = {
            row["division_id"]: row["ocd_division_id"]
            for row in package["records"]["divisions"]
        }
        for control in package["qa"]["address_tests"]:
            if control.get("coordinate_role") != "DERIVED_TEST_POINT_ONLY":
                continue

            model = build_representation_for_address(
                control["address_input"],
                geocoder=geocoder,
                generated_at=STAMP,
                root=ROOT,
                policy=policy,
            )
            if model.get("status") != "PASS":
                raise AssertionError(
                    f"{control['test_id']}: live pipeline failed: {model}"
                )

            expected_division = native_to_ocdid[control["expected_division_id"]]
            if model.get("resolved_division_ocdid") != expected_division:
                raise AssertionError(
                    f"{control['test_id']}: expected {expected_division}, "
                    f"got {model.get('resolved_division_ocdid')}"
                )

            actual_offices = sorted(
                row["office_id"] for row in model["applicable_offices"]
            )
            expected_offices = sorted(
                part.strip()
                for part in control["expected_office_ids"].split(";")
                if part.strip()
            )
            if actual_offices != expected_offices:
                raise AssertionError(
                    f"{control['test_id']}: office mismatch "
                    f"expected={expected_offices} actual={actual_offices}"
                )

            geocoding = model["geocoding"]
            if geocoding["provider"] != ARCGIS_PROVIDER:
                raise AssertionError(
                    f"{control['test_id']}: wrong provider {geocoding['provider']}"
                )
            if geocoding["score"] < policy.min_score:
                raise AssertionError(
                    f"{control['test_id']}: score below policy"
                )
            if geocoding["addr_type"] not in policy.allowed_addr_types:
                raise AssertionError(
                    f"{control['test_id']}: type outside policy"
                )
            if model["address_resolution_source"] != RESOLUTION_SOURCE:
                raise AssertionError(
                    f"{control['test_id']}: wrong resolution source"
                )
            if model["canonical_writes"] != 0:
                raise AssertionError(
                    f"{control['test_id']}: canonical writes must remain zero"
                )

            results.append(
                {
                    "test_id": control["test_id"],
                    "address": control["address_input"],
                    "matched_address": geocoding["matched_address"],
                    "score": geocoding["score"],
                    "addr_type": geocoding["addr_type"],
                    "candidate_count": geocoding["candidate_count"],
                    "score_margin": geocoding["score_margin"],
                    "division_ocdid": model["resolved_division_ocdid"],
                    "office_count": len(actual_offices),
                    "status": "PASS",
                }
            )

    if len(results) != 8:
        raise AssertionError(f"expected 8 live district controls, got {len(results)}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "GOVERNED-GEOCODING-LIVE-001",
                "provider": ARCGIS_PROVIDER,
                "policy": {
                    "min_score": policy.min_score,
                    "min_margin": policy.min_margin,
                    "allowed_addr_types": list(policy.allowed_addr_types),
                },
                "controls": results,
                "canonical_writes": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
