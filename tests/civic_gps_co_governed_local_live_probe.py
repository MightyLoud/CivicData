#!/usr/bin/env python3
"""Live Civic GPS geocode -> governed local polygons -> EV Contract v1 proof."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.contract_v1 import (
    build_representation_from_civic_gps_result,
)
from consumers.empowered_vote.live_civic_gps import (
    load_governed_civic_gps_resolver,
    normalize_civic_gps_result,
)

EXTENSION = ROOT / "civic_gps_extensions" / "registry_bundles.v0.1.json"
PACKAGES = {
    "Alamosa": ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
    "Arvada": ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
}
GENERATED_AT = "2026-09-26T20:30:00Z"


def split_ids(value):
    return sorted(
        part.strip()
        for part in str(value or "").split(";")
        if part.strip()
    )


def overlay_for(extension, jurisdiction_id):
    matches = [
        row
        for row in extension["governed_local_district_overlays"]
        if row["jurisdiction_id"] == jurisdiction_id
    ]
    assert len(matches) == 1, matches
    return matches[0]


def binding_for(package, overlay):
    return {
        "contract_jurisdiction_ocdid": (
            package["jurisdiction"]["ocd_jurisdiction_id"]
        ),
        "civic_gps_jurisdiction_id": overlay["jurisdiction_id"],
        "district_adapter_id": overlay["overlay_id"],
        "district_division_map": {
            str(key): meta["division_ocdid"]
            for key, meta in overlay["districts"].items()
        },
    }


def expected_key(package, control, overlay):
    divisions = {
        row["division_id"]: row["ocd_division_id"]
        for row in package["records"]["divisions"]
    }
    expected_ocdid = divisions[control["expected_division_id"]]
    reverse = {
        meta["division_ocdid"]: str(key)
        for key, meta in overlay["districts"].items()
    }
    return reverse[expected_ocdid]


def run() -> None:
    extension = json.loads(EXTENSION.read_text(encoding="utf-8"))
    resolver = load_governed_civic_gps_resolver(
        ROOT,
        timeout_seconds=30.0,
    )
    results = []
    live_success_by_city = {city: 0 for city in PACKAGES}

    for city, package_path in PACKAGES.items():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        civic_jurisdiction_id = (
            "jur-us-co-alamosa"
            if city == "Alamosa"
            else "jur-us-co-arvada"
        )
        overlay = overlay_for(extension, civic_jurisdiction_id)
        contract = export_factory_package(
            package,
            generated_at=GENERATED_AT,
            governed_package=True,
        )
        binding = binding_for(package, overlay)
        controls = [
            row
            for row in package["qa"]["address_tests"]
            if row.get("coordinate_role") == "DERIVED_TEST_POINT_ONLY"
        ]
        assert len(controls) == 4, (city, len(controls))

        for control in controls:
            canonical_address = control["address_input"]
            longitude = float(control["longitude"])
            latitude = float(control["latitude"])

            coordinate_gps = resolver.resolve_governed_local_coordinate(
                civic_jurisdiction_id,
                longitude=longitude,
                latitude=latitude,
                observed_on=None,
            )
            if "error" in coordinate_gps:
                raise AssertionError(
                    (city, canonical_address, coordinate_gps["error"])
                )
            coordinate_normalized = normalize_civic_gps_result(
                canonical_address,
                coordinate_gps,
            )
            assert coordinate_normalized["status"] == "PASS", (
                coordinate_normalized
            )
            got_key = coordinate_normalized[
                "district_assignments"
            ].get(overlay["overlay_id"])
            want_key = expected_key(package, control, overlay)
            assert got_key == want_key, (
                city,
                canonical_address,
                want_key,
                got_key,
                coordinate_normalized["district_assignments"],
            )

            coordinate_model = build_representation_from_civic_gps_result(
                contract,
                canonical_address,
                coordinate_gps,
                binding=binding,
                resolution_source=(
                    "CIVIC_GPS_GOVERNED_LOCAL_COORDINATE"
                ),
            )
            assert coordinate_model["status"] == "PASS", coordinate_model
            actual_offices = sorted(
                row["office_id"]
                for row in coordinate_model["applicable_offices"]
            )
            expected_offices = split_ids(
                control["expected_office_ids"]
            )
            assert actual_offices == expected_offices, (
                city,
                canonical_address,
                expected_offices,
                actual_offices,
            )
            assert coordinate_model["resolved_division_ocdid"] == binding[
                "district_division_map"
            ][want_key]
            assert coordinate_model["canonical_writes"] == 0

            live_geocode_status = control.get(
                "civic_gps_live_geocode_status",
                "EXPECTED",
            )
            live_address_result = None
            if live_geocode_status == "EXPECTED":
                live_address = (
                    control.get("civic_gps_probe_address")
                    or canonical_address
                )
                live_gps = resolver.resolve(
                    live_address,
                    observed_on=None,
                )
                if "error" in live_gps:
                    error = live_gps["error"]
                    code = str(error.get("code") or "")
                    if code not in {
                        "ADDRESS_NOT_MATCHED",
                        "UPSTREAM_REQUEST_FAILED",
                    }:
                        raise AssertionError(
                            (city, live_address, error)
                        )
                    live_address_result = {
                        "status": "GEOCODER_PROVIDER_GAP",
                        "address": live_address,
                        "error_code": code,
                        "detail": error,
                    }
                else:
                    live_normalized = normalize_civic_gps_result(
                        live_address,
                        live_gps,
                    )
                    assert live_normalized["status"] == "PASS", live_normalized
                    assert civic_jurisdiction_id in live_normalized[
                        "jurisdiction_ids"
                    ]
                    live_key = live_normalized[
                        "district_assignments"
                    ].get(overlay["overlay_id"])
                    assert live_key == want_key, (
                        city,
                        live_address,
                        want_key,
                        live_key,
                    )

                    payload = live_gps["payload"]
                    jurisdiction_offices = [
                        row
                        for row in payload.get("offices", [])
                        if row.get("jurisdiction_id")
                        == civic_jurisdiction_id
                    ]
                    jurisdiction_applicable = [
                        row
                        for row in payload.get("applicable_offices", [])
                        if row.get("jurisdiction_id")
                        == civic_jurisdiction_id
                    ]
                    jurisdiction_actions = [
                        row
                        for row in payload.get("action_links", [])
                        if row.get("jurisdiction_id")
                        == civic_jurisdiction_id
                    ]
                    assert jurisdiction_offices == []
                    assert jurisdiction_applicable == []
                    assert jurisdiction_actions == []
                    live_success_by_city[city] += 1
                    live_address_result = {
                        "status": "PASS",
                        "address": live_address,
                        "district_key": live_key,
                        "matched_address": (
                            live_normalized.get("matched_address")
                        ),
                    }
            else:
                assert live_geocode_status == (
                    "UNRESOLVED_CENSUS_GEOCODER"
                )
                live_address_result = {
                    "status": live_geocode_status,
                    "address": canonical_address,
                    "detail": control.get(
                        "civic_gps_live_geocode_note"
                    ),
                }

            results.append({
                "city": city,
                "canonical_control_address": canonical_address,
                "adapter_id": overlay["overlay_id"],
                "district_key": got_key,
                "longitude": longitude,
                "latitude": latitude,
                "resolved_division_ocdid": (
                    coordinate_model["resolved_division_ocdid"]
                ),
                "office_ids": actual_offices,
                "current_holder_count": (
                    coordinate_model["current_holder_count"]
                ),
                "coordinate_resolution_source": (
                    coordinate_model["address_resolution_source"]
                ),
                "live_address": live_address_result,
            })

    assert len(results) == 8
    for city, success_count in live_success_by_city.items():
        assert success_count >= 1, (
            city,
            "At least one live Census-geocoder route per city is required.",
            results,
        )

    print(json.dumps({
        "status": "PASS",
        "gate": "EV-RC1-GOVERNED-LOCAL-GEOMETRY-LIVE",
        "controls": results,
        "dynamic_polygon_assignments": 8,
        "factory_expected_divisions_used_as_routing_input": 0,
        "live_address_geocodes_passed": sum(
            1
            for row in results
            if row["live_address"]["status"] == "PASS"
        ),
        "live_address_geocoder_gaps": sum(
            1
            for row in results
            if row["live_address"]["status"]
            in {
                "UNRESOLVED_CENSUS_GEOCODER",
                "GEOCODER_PROVIDER_GAP",
            }
        ),
        "live_success_by_city": live_success_by_city,
        "civic_gps_local_civic_fact_rows": 0,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
