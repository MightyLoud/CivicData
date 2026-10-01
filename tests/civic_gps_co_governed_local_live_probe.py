#!/usr/bin/env python3
"""Live Civic GPS geocode -> governed local polygons -> EV Contract v1 proof."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.factory.export_representation import export_factory_package
from civic_gps_extensions.loader import load_resolver_with_extensions
from consumers.empowered_vote.contract_v1 import (
    build_representation_from_civic_gps_result,
)
from consumers.empowered_vote.live_civic_gps import normalize_civic_gps_result

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
    resolver = load_resolver_with_extensions(
        ROOT,
        timeout_seconds=30.0,
    )
    results = []

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
            address = control["address_input"]
            gps = resolver.resolve(address, observed_on=None)
            if "error" in gps:
                raise AssertionError((city, address, gps["error"]))
            normalized = normalize_civic_gps_result(address, gps)
            assert normalized["status"] == "PASS", normalized
            assert civic_jurisdiction_id in normalized["jurisdiction_ids"]
            got_key = normalized["district_assignments"].get(
                overlay["overlay_id"]
            )
            want_key = expected_key(package, control, overlay)
            assert got_key == want_key, (
                city,
                address,
                want_key,
                got_key,
                normalized["district_assignments"],
            )

            payload = gps["payload"]
            jurisdiction_offices = [
                row
                for row in payload.get("offices", [])
                if row.get("jurisdiction_id") == civic_jurisdiction_id
            ]
            jurisdiction_applicable = [
                row
                for row in payload.get("applicable_offices", [])
                if row.get("jurisdiction_id") == civic_jurisdiction_id
            ]
            jurisdiction_actions = [
                row
                for row in payload.get("action_links", [])
                if row.get("jurisdiction_id") == civic_jurisdiction_id
            ]
            assert jurisdiction_offices == []
            assert jurisdiction_applicable == []
            assert jurisdiction_actions == []

            model = build_representation_from_civic_gps_result(
                contract,
                address,
                gps,
                binding=binding,
                resolution_source=(
                    "CIVIC_GPS_GOVERNED_LOCAL_GEOMETRY"
                ),
            )
            assert model["status"] == "PASS", model
            actual_offices = sorted(
                row["office_id"]
                for row in model["applicable_offices"]
            )
            expected_offices = split_ids(
                control["expected_office_ids"]
            )
            assert actual_offices == expected_offices, (
                city,
                address,
                expected_offices,
                actual_offices,
            )
            assert model["resolved_division_ocdid"] == binding[
                "district_division_map"
            ][want_key]
            assert model["address_resolution_source"] == (
                "CIVIC_GPS_GOVERNED_LOCAL_GEOMETRY"
            )
            assert model["canonical_writes"] == 0

            results.append({
                "city": city,
                "address": address,
                "adapter_id": overlay["overlay_id"],
                "district_key": got_key,
                "resolved_division_ocdid": (
                    model["resolved_division_ocdid"]
                ),
                "office_ids": actual_offices,
                "current_holder_count": (
                    model["current_holder_count"]
                ),
                "matched_address": model.get("matched_address"),
            })

    assert len(results) == 8
    print(json.dumps({
        "status": "PASS",
        "gate": "EV-RC1-GOVERNED-LOCAL-GEOMETRY-LIVE",
        "controls": results,
        "dynamic_polygon_assignments": 8,
        "factory_controls_used_as_routing_input": 0,
        "civic_gps_local_civic_fact_rows": 0,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
