#!/usr/bin/env python3
"""Live Civic GPS geography bridge for Empowered.Vote.

EV-IMP-003 narrows Civic GPS authority to address -> jurisdiction/district
resolution. CivicData Jurisdiction Package v0.2 remains authoritative for
bodies, offices, people, currentness, terms, elections, contests, candidacies,
provenance, warnings, and all rendered civic facts.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

from consumers.empowered_vote import package_source

TACOMA_BINDING = {
    "package_jurisdiction_id": "jurisdiction:us/wa/tacoma",
    "civic_gps_jurisdiction_id": "jur-us-wa-tacoma",
    "district_adapter_id": "DIST-WA-TACOMA-COUNCIL",
    "division_prefix": "division:us/wa/tacoma/council_district_",
}


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": "EV-IMP-003",
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        result["detail"] = detail
    return result


def normalize_civic_gps_result(address: str, result: Any) -> dict[str, Any]:
    """Keep only stable geographic fields from a Civic GPS response."""
    if not isinstance(result, dict):
        return _fail(address, "CIVIC_GPS_RESPONSE_INVALID", "response is not an object")
    if "error" in result:
        error = result.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "CIVIC_GPS_ERROR")
            detail = str(error.get("message") or error)
        else:
            code = "CIVIC_GPS_ERROR"
            detail = str(error)
        return _fail(address, code, detail)

    payload = result.get("payload")
    if not isinstance(payload, dict):
        return _fail(address, "CIVIC_GPS_PAYLOAD_MISSING")
    jurisdictions = payload.get("jurisdictions")
    assignments = payload.get("district_assignments")
    if not isinstance(jurisdictions, list) or not isinstance(assignments, list):
        return _fail(address, "CIVIC_GPS_GEOGRAPHY_FIELDS_MISSING")

    jurisdiction_ids: list[str] = []
    for row in jurisdictions:
        if not isinstance(row, dict) or not row.get("jurisdiction_id"):
            return _fail(address, "CIVIC_GPS_JURISDICTION_INVALID")
        jurisdiction_ids.append(str(row["jurisdiction_id"]))

    district_assignments: dict[str, str] = {}
    for row in assignments:
        if not isinstance(row, dict) or not row.get("adapter_id") or row.get("district_key") is None:
            return _fail(address, "CIVIC_GPS_DISTRICT_ASSIGNMENT_INVALID")
        adapter_id = str(row["adapter_id"])
        district_key = str(row["district_key"])
        if adapter_id in district_assignments and district_assignments[adapter_id] != district_key:
            return _fail(address, "CIVIC_GPS_AMBIGUOUS_DISTRICT", adapter_id)
        district_assignments[adapter_id] = district_key

    input_block = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    return {
        "status": "PASS",
        "input_address": address,
        "matched_address": input_block.get("matched_address"),
        "jurisdiction_ids": sorted(set(jurisdiction_ids)),
        "district_assignments": dict(sorted(district_assignments.items())),
        "canonical_writes": 0,
    }


def build_essentials_from_civic_gps_result(
    package: dict[str, Any],
    address: str,
    civic_gps_result: Any,
    *,
    binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Join live Civic GPS geography to package-authoritative Essentials facts."""
    binding = TACOMA_BINDING if binding is None else binding
    if package.get("jurisdiction", {}).get("jurisdiction_id") != binding.get("package_jurisdiction_id"):
        return _fail(address, "CIVIC_GPS_PACKAGE_BINDING_UNSUPPORTED")

    normalized = normalize_civic_gps_result(address, civic_gps_result)
    if normalized.get("status") != "PASS":
        return normalized

    civic_jurisdiction_id = binding["civic_gps_jurisdiction_id"]
    active = civic_jurisdiction_id in normalized["jurisdiction_ids"]
    district_division_id: str | None = None

    if active:
        adapter_id = binding["district_adapter_id"]
        district_key = normalized["district_assignments"].get(adapter_id)
        if district_key is None:
            return _fail(address, "CIVIC_GPS_REQUIRED_DISTRICT_MISSING", adapter_id)
        district_division_id = f"{binding['division_prefix']}{district_key}"
        package_divisions = {
            str(row.get("division_id") or row.get("id"))
            for row in package.get("records", {}).get("divisions", [])
            if isinstance(row, dict)
        }
        if district_division_id not in package_divisions:
            return _fail(address, "CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE", district_division_id)

    # The existing package projection accepts a control-shaped geographic result.
    # Create an isolated package copy with only this live result; the governed
    # package itself is never mutated and remains the sole civic-fact authority.
    control = {
        "control_id": "EV-IMP-003-LIVE-CIVIC-GPS",
        "input": address,
        "result": True,
        "fixture_tacoma_division_id": district_division_id,
        "resolved_jurisdictions": normalized["jurisdiction_ids"],
        "district_assignments": normalized["district_assignments"],
    }
    shadow = copy.deepcopy(package)
    shadow["qa"] = dict(shadow["qa"])
    shadow["qa"]["address_tests"] = [control]

    model = package_source.build_essentials_from_package(shadow, address)
    if model.get("status") != "PASS":
        return model
    model.pop("deterministic_sha256", None)
    model["consumer_gate"] = "EV-IMP-003"
    model["address_resolution_source"] = "CIVIC_GPS_LIVE"
    model["matched_address"] = normalized.get("matched_address")
    model["canonical_writes"] = 0
    model["deterministic_sha256"] = package_source.sha256_bytes(
        package_source.canonical_json_bytes(model)
    )
    return model


def build_essentials_from_live_civic_gps(
    package: dict[str, Any],
    address: str,
    resolver: Any,
    *,
    binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve an address through Civic GPS and join to governed package facts."""
    try:
        result = resolver.resolve(address, observed_on=None)
    except Exception as exc:  # network/runtime exceptions must fail closed
        return _fail(address, "CIVIC_GPS_RESOLUTION_EXCEPTION", str(exc))
    return build_essentials_from_civic_gps_result(package, address, result, binding=binding)


def load_default_civic_gps_resolver(
    repo_root: str | Path | None = None,
    *,
    timeout_seconds: float = 30.0,
) -> Any:
    """Load the reconstructed Civic GPS runtime without embedding a second engine."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    engine_path = root / "civic_gps" / "engine.py"
    registry_path = root / "civic_gps" / "registry.json"
    if not engine_path.is_file() or not registry_path.is_file():
        raise FileNotFoundError("reconstructed Civic GPS runtime is not present")
    spec = importlib.util.spec_from_file_location("civic_gps_engine_for_ev", engine_path)
    if spec is None or spec.loader is None:
        raise ImportError("unable to load Civic GPS engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.CivicGPSOverlayEngine.from_file(registry_path, timeout_seconds=timeout_seconds)
