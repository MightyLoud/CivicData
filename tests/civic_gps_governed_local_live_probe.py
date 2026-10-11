#!/usr/bin/env python3
"""Live Civic GPS governed-local polygons -> Contract v1 proof for issue #104."""
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

STAMP = "2026-10-11T18:00:00Z"

CASES = (
    {
        "package": ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
        "gps_jurisdiction_id": "jur-us-co-alamosa",
        "adapter_id": "DIST-CO-ALAMOSA-WARDS-GOVERNED",
        "district_map": {
            "1": "ocd-division/country:us/state:co/place:alamosa/ward:1",
            "2": "ocd-division/country:us/state:co/place:alamosa/ward:2",
            "3": "ocd-division/country:us/state:co/place:alamosa/ward:3",
            "4": "ocd-division/country:us/state:co/place:alamosa/ward:4",
        },
    },
    {
        "package": ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
        "gps_jurisdiction_id": "jur-us-co-arvada",
        "adapter_id": "DIST-CO-ARVADA-COUNCIL-GOVERNED",
        "district_map": {
            "1": "ocd-division/country:us/state:co/place:arvada/council_district:1",
            "2": "ocd-division/country:us/state:co/place:arvada/council_district:2",
            "3": "ocd-division/country:us/state:co/place:arvada/council_district:3",
            "4": "ocd-division/country:us/state:co/place:arvada/council_district:4",
        },
    },
)


def expected_key_for_control(control: dict, mapping: dict[str, str]) -> str:
    expected_native = str(control["expected_division_id"])
    suffix = expected_native.rsplit("-", 1)[-1]
    if suffix not in mapping:
        raise AssertionError(
            f"{control['test_id']}: no district key for {expected_native}"
        )
    return suffix


def civic_fact_rows_for_jurisdiction(payload: dict, jurisdiction_id: str) -> dict:
    offices = [
        row
        for row in payload.get("offices", [])
        if row.get("jurisdiction_id") == jurisdiction_id
    ]
    applicable = [
        row
        for row in payload.get("applicable_offices", [])
        if row.get("jurisdiction_id") == jurisdiction_id
    ]
    office_ids = {row.get("office_id") for row in offices}
    holders = [
        row
        for row in payload.get("officeholders", [])
        if row.get("office_id") in office_ids
    ]
    actions = [
        row
        for row in payload.get("action_links", [])
        if row.get("jurisdiction_id") == jurisdiction_id
    ]
    return {
        "offices": offices,
        "applicable": applicable,
        "holders": holders,
        "actions": actions,
    }


def main() -> int:
    resolver = load_resolver_with_extensions(ROOT, timeout_seconds=30.0)
    summaries = []

    for case in CASES:
        package = json.loads(case["package"].read_text(encoding="utf-8"))
        contract = export_factory_package(
            package,
            generated_at=STAMP,
            governed_package=True,
        )
        jurisdiction_ocdid = package["jurisdiction"]["ocd_jurisdiction_id"]

        for control in package["qa"]["address_tests"]:
            if control.get("coordinate_role") != "DERIVED_TEST_POINT_ONLY":
                continue

            address = control["address_input"]
            routing_address = (
                control.get("civic_gps_live_routing_address")
                or address
            )
            gps = resolver.resolve(routing_address, observed_on=None)
            if "error" in gps:
                raise AssertionError(
                    f"{control['test_id']}: Civic GPS error for "
                    f"{routing_address!r}: {gps['error']}"
                )
            payload = gps["payload"]
            jurisdiction_ids = {
                str(row["jurisdiction_id"])
                for row in payload.get("jurisdictions", [])
                if row.get("jurisdiction_id")
            }
            if case["gps_jurisdiction_id"] not in jurisdiction_ids:
                raise AssertionError(
                    f"{control['test_id']}: missing {case['gps_jurisdiction_id']}; "
                    f"got {sorted(jurisdiction_ids)}"
                )

            assignments = {
                str(row["adapter_id"]): str(row["district_key"])
                for row in payload.get("district_assignments", [])
                if row.get("adapter_id") is not None
            }
            expected_key = expected_key_for_control(
                control,
                case["district_map"],
            )
            got_key = assignments.get(case["adapter_id"])
            if got_key != expected_key:
                raise AssertionError(
                    f"{control['test_id']}: expected district key {expected_key}, "
                    f"got {got_key!r}"
                )

            local_facts = civic_fact_rows_for_jurisdiction(
                payload,
                case["gps_jurisdiction_id"],
            )
            if any(local_facts.values()):
                raise AssertionError(
                    f"{control['test_id']}: routing extension emitted civic facts: "
                    f"{local_facts}"
                )

            binding = {
                "contract_jurisdiction_ocdid": jurisdiction_ocdid,
                "civic_gps_jurisdiction_id": case["gps_jurisdiction_id"],
                "district_adapter_id": case["adapter_id"],
                "district_division_map": case["district_map"],
            }
            model = build_representation_from_civic_gps_result(
                contract,
                address,
                gps,
                binding=binding,
                resolution_source="CIVIC_GPS_LIVE_GOVERNED_LOCAL",
            )
            if model.get("status") != "PASS":
                raise AssertionError(
                    f"{control['test_id']}: Contract v1 failed: {model}"
                )

            expected_offices = sorted(
                part.strip()
                for part in control["expected_office_ids"].split(";")
                if part.strip()
            )
            actual_offices = sorted(
                row["office_id"]
                for row in model["applicable_offices"]
            )
            if actual_offices != expected_offices:
                raise AssertionError(
                    f"{control['test_id']}: expected offices "
                    f"{expected_offices}, got {actual_offices}"
                )
            if model["resolved_division_ocdid"] != case["district_map"][expected_key]:
                raise AssertionError(
                    f"{control['test_id']}: wrong Contract division "
                    f"{model['resolved_division_ocdid']}"
                )
            if model["canonical_writes"] != 0:
                raise AssertionError(
                    f"{control['test_id']}: canonical writes must remain zero"
                )

            resolution_mode = gps.get("meta", {}).get("resolution_mode")
            fallback_provider = gps.get("meta", {}).get("fallback_provider")
            if control["test_id"] == "addrtest-co-alamosa-ward-4-lee-fields":
                if resolution_mode != "GOVERNED_LOCAL_GEOCODER_FALLBACK":
                    raise AssertionError(
                        f"{control['test_id']}: expected governed fallback, "
                        f"got {resolution_mode!r}"
                    )
                if fallback_provider != "ARCGIS_WORLD_GEOCODER":
                    raise AssertionError(
                        f"{control['test_id']}: expected ArcGIS fallback, "
                        f"got {fallback_provider!r}"
                    )

            summaries.append(
                {
                    "test_id": control["test_id"],
                    "address": address,
                    "routing_address": routing_address,
                    "resolution_mode": resolution_mode,
                    "fallback_provider": fallback_provider,
                    "matched_address": payload.get("input", {}).get(
                        "matched_address"
                    ),
                    "jurisdiction_id": case["gps_jurisdiction_id"],
                    "adapter_id": case["adapter_id"],
                    "district_key": got_key,
                    "division_ocdid": model["resolved_division_ocdid"],
                    "office_count": len(actual_offices),
                    "status": "PASS",
                }
            )

    if len(summaries) != 8:
        raise AssertionError(
            f"expected 8 governed local district controls, got {len(summaries)}"
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CIVIC-GPS-GOVERNED-LOCAL-001",
                "controls": summaries,
                "routing_only_civic_fact_rows": 0,
                "canonical_writes": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
