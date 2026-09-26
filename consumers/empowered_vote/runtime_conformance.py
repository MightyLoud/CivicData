#!/usr/bin/env python3
"""Generic governed-address runtime conformance for Empowered Vote Contract v1.

Factory address controls are the governed address -> division/office fixtures.
This module tests the actual Contract-v1 runtime join after that geography
boundary. It does not claim that Civic GPS performed a live network lookup.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from consumers.empowered_vote.contract_v1 import (
    build_representation_from_civic_gps_result,
    validate_contract,
)

RESOLUTION_SOURCE = "GOVERNED_FACTORY_ADDRESS_CONTROL"


class RuntimeConformanceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_semicolon(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return sorted({_clean(item) for item in value if _clean(item)})
    return sorted(
        {
            part.strip()
            for part in str(value).split(";")
            if part.strip()
        }
    )


def _native_identifier(row: Mapping[str, Any], scheme: str) -> str | None:
    for identifier in row.get("identifiers") or []:
        if (
            isinstance(identifier, Mapping)
            and identifier.get("scheme") == scheme
            and identifier.get("id") not in (None, "")
        ):
            return str(identifier["id"])
    return None


def _division_crosswalk(package: Mapping[str, Any]) -> dict[str, str]:
    rows = package.get("records", {}).get("divisions", [])
    out: dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        native = _clean(row.get("division_id") or row.get("id"))
        ocdid = _clean(row.get("ocd_division_id") or row.get("division_ocdid"))
        if native and ocdid.startswith("ocd-division/"):
            out[native] = ocdid
    return out


def _contract_office_ids(contract: Mapping[str, Any]) -> set[str]:
    return {
        native
        for row in contract.get("posts", [])
        if isinstance(row, Mapping)
        for native in [_native_identifier(row, "civicdata_factory_office")]
        if native
    }


def _fixture_jurisdiction_id(package: Mapping[str, Any]) -> str:
    native = _clean(package.get("jurisdiction", {}).get("jurisdiction_id"))
    if not native:
        raise RuntimeConformanceError("PACKAGE_JURISDICTION_ID_REQUIRED")
    return "fixture:" + native


def _base_division_ocdid(contract: Mapping[str, Any]) -> str | None:
    jurisdiction = _clean(
        contract.get("jurisdiction", {}).get("jurisdiction_ocdid")
    )
    prefix = "ocd-jurisdiction/"
    suffix = "/government"
    if not jurisdiction.startswith(prefix) or not jurisdiction.endswith(suffix):
        return None
    return "ocd-division/" + jurisdiction[len(prefix):-len(suffix)]


def _gps_fixture(
    *,
    address: str,
    matched_address: str,
    fixture_jurisdiction_id: str,
    district_adapter_id: str | None = None,
    district_key: str | None = None,
) -> dict[str, Any]:
    assignments = []
    if district_adapter_id is not None:
        if district_key is None:
            raise RuntimeConformanceError("DISTRICT_KEY_REQUIRED")
        assignments.append(
            {
                "adapter_id": district_adapter_id,
                "district_key": district_key,
            }
        )
    return {
        "payload": {
            "input": {"matched_address": matched_address or address},
            "jurisdictions": [
                {"jurisdiction_id": fixture_jurisdiction_id}
            ],
            "district_assignments": assignments,
        }
    }


def evaluate_address_control(
    package: Mapping[str, Any],
    contract: Mapping[str, Any],
    control: Mapping[str, Any],
) -> dict[str, Any]:
    if control.get("result") is not True:
        return {
            "test_id": control.get("test_id"),
            "address": control.get("address_input"),
            "status": "BLOCKED",
            "error": "FACTORY_ADDRESS_CONTROL_NOT_PASSING",
        }

    address = _clean(control.get("address_input"))
    if not address:
        return {
            "test_id": control.get("test_id"),
            "address": None,
            "status": "BLOCKED",
            "error": "FACTORY_ADDRESS_CONTROL_ADDRESS_MISSING",
        }

    divisions = _division_crosswalk(package)
    expected_native_division = _clean(control.get("expected_division_id"))
    expected_division_ocdid = divisions.get(expected_native_division)
    if expected_division_ocdid is None:
        return {
            "test_id": control.get("test_id"),
            "address": address,
            "status": "BLOCKED",
            "error": "EXPECTED_DIVISION_CROSSWALK_MISSING",
            "expected_division_id": expected_native_division,
        }

    expected_offices = _split_semicolon(control.get("expected_office_ids"))
    if not expected_offices:
        return {
            "test_id": control.get("test_id"),
            "address": address,
            "status": "BLOCKED",
            "error": "EXPECTED_OFFICES_MISSING",
        }

    known_offices = _contract_office_ids(contract)
    missing_offices = sorted(set(expected_offices) - known_offices)
    if missing_offices:
        return {
            "test_id": control.get("test_id"),
            "address": address,
            "status": "BLOCKED",
            "error": "EXPECTED_OFFICE_NOT_IN_CONTRACT",
            "missing_office_ids": missing_offices,
        }

    fixture_jurisdiction_id = _fixture_jurisdiction_id(package)
    binding = {
        "contract_jurisdiction_ocdid": contract["jurisdiction"]["jurisdiction_ocdid"],
        "civic_gps_jurisdiction_id": fixture_jurisdiction_id,
    }
    base_division = _base_division_ocdid(contract)
    if expected_division_ocdid == base_division:
        binding["division_ocdid"] = expected_division_ocdid
        district_adapter_id = None
        district_key = None
    else:
        district_adapter_id = (
            "fixture:"
            + _clean(package.get("jurisdiction", {}).get("jurisdiction_id"))
            + ":district"
        )
        district_key = expected_native_division
        binding["district_adapter_id"] = district_adapter_id
        binding["district_division_map"] = {
            district_key: expected_division_ocdid,
        }

    gps = _gps_fixture(
        address=address,
        matched_address=_clean(control.get("normalized_address")),
        fixture_jurisdiction_id=fixture_jurisdiction_id,
        district_adapter_id=district_adapter_id,
        district_key=district_key,
    )
    model = build_representation_from_civic_gps_result(
        dict(contract),
        address,
        gps,
        binding=binding,
        resolution_source=RESOLUTION_SOURCE,
    )
    if model.get("status") != "PASS":
        return {
            "test_id": control.get("test_id"),
            "address": address,
            "status": "BLOCKED",
            "error": model.get("error") or "EV_RUNTIME_FAILED",
            "detail": model.get("detail"),
        }

    actual_offices = sorted(
        str(row.get("office_id"))
        for row in model.get("applicable_offices", [])
        if row.get("office_id")
    )
    errors: list[str] = []
    if model.get("resolved_division_ocdid") != expected_division_ocdid:
        errors.append("RESOLVED_DIVISION_MISMATCH")
    if actual_offices != expected_offices:
        errors.append("APPLICABLE_OFFICES_MISMATCH")
    if model.get("address_resolution_source") != RESOLUTION_SOURCE:
        errors.append("RESOLUTION_SOURCE_MISMATCH")
    if model.get("canonical_writes") != 0:
        errors.append("CANONICAL_WRITE_FORBIDDEN")

    expected_holder_count = 0
    expected_capacity = 0
    for office in model.get("applicable_offices", []):
        holders = office.get("holders")
        if isinstance(holders, list):
            expected_holder_count += len(holders)
        capacity = office.get("seat_capacity")
        if isinstance(capacity, int):
            expected_capacity += capacity
    if model.get("current_holder_count") != expected_holder_count:
        errors.append("CURRENT_HOLDER_COUNT_MISMATCH")

    return {
        "test_id": control.get("test_id"),
        "address": address,
        "normalized_address": control.get("normalized_address"),
        "status": "PASS" if not errors else "LOSSY",
        "errors": errors,
        "expected_division_id": expected_native_division,
        "expected_division_ocdid": expected_division_ocdid,
        "resolved_division_ocdid": model.get("resolved_division_ocdid"),
        "expected_office_ids": expected_offices,
        "actual_office_ids": actual_offices,
        "current_holder_count": model.get("current_holder_count"),
        "selected_seat_capacity": expected_capacity,
        "resolution_source": model.get("address_resolution_source"),
        "canonical_writes": model.get("canonical_writes"),
    }


def _division_coverage_gaps(
    package: Mapping[str, Any],
    controls: Sequence[Mapping[str, Any]],
) -> list[str]:
    used = {
        _clean(row.get("expected_division_id"))
        for row in controls
        if isinstance(row, Mapping)
        and row.get("result") is True
        and _clean(row.get("expected_division_id"))
    }
    gaps: list[str] = []
    for row in package.get("records", {}).get("divisions", []):
        if not isinstance(row, Mapping):
            continue
        native = _clean(row.get("division_id") or row.get("id"))
        ocdid = _clean(row.get("ocd_division_id") or row.get("division_ocdid"))
        kind = _clean(row.get("division_type")).lower()
        if native and native not in used and kind in {
            "ward",
            "district",
            "council_district",
            "local_district",
        }:
            gaps.append(f"NO_GOVERNED_ADDRESS_CONTROL:{native}:{ocdid}")
    return sorted(gaps)


def evaluate_governed_address_runtime(
    package: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    contract_errors = validate_contract(contract, require_certified=True)
    if contract_errors:
        return {
            "status": "BLOCKED",
            "mode": "GOVERNED_ADDRESS_FIXTURE_RUNTIME",
            "controls_total": 0,
            "controls_passed": 0,
            "controls_lossy": 0,
            "controls_blocked": 0,
            "controls": [],
            "geography_gaps": [],
            "untested_capabilities": ["live_civic_gps_network"],
            "errors": contract_errors,
        }

    raw_controls = package.get("qa", {}).get("address_tests", [])
    if not isinstance(raw_controls, list) or not raw_controls:
        return {
            "status": "NOT_TESTED",
            "mode": "GOVERNED_ADDRESS_FIXTURE_RUNTIME",
            "controls_total": 0,
            "controls_passed": 0,
            "controls_lossy": 0,
            "controls_blocked": 0,
            "controls": [],
            "geography_gaps": [],
            "untested_capabilities": [
                "governed_address_controls",
                "live_civic_gps_network",
            ],
            "errors": [],
        }

    controls = [
        evaluate_address_control(package, contract, row)
        for row in raw_controls
        if isinstance(row, Mapping)
    ]
    counts = {
        status: sum(1 for row in controls if row.get("status") == status)
        for status in ("PASS", "LOSSY", "BLOCKED")
    }
    if counts["BLOCKED"]:
        status = "BLOCKED"
    elif counts["LOSSY"]:
        status = "LOSSY"
    elif counts["PASS"] == len(controls) and controls:
        status = "PASS"
    else:
        status = "NOT_TESTED"

    geography_gaps = _division_coverage_gaps(package, raw_controls)
    untested = ["live_civic_gps_network"]
    if geography_gaps:
        untested.append("district_address_runtime_coverage")

    return {
        "status": status,
        "mode": "GOVERNED_ADDRESS_FIXTURE_RUNTIME",
        "controls_total": len(controls),
        "controls_passed": counts["PASS"],
        "controls_lossy": counts["LOSSY"],
        "controls_blocked": counts["BLOCKED"],
        "controls": controls,
        "geography_gaps": geography_gaps,
        "untested_capabilities": untested,
        "errors": sorted(
            {
                str(row.get("error"))
                for row in controls
                if row.get("error")
            }
        ),
    }
