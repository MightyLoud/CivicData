"""Deterministic successor receipt for the bounded Texas two-office package.

This builder is for a successor civic-fact package after a governed upstream
identity change. Historical live acceptance is carried only as a pinned
geography-evidence reference; old captured representation output is never
replayed as though its pre-change Person fields were current.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from civic_gps_extensions.texas_legislative import build_texas_internal_configuration
from tools.jurisdiction_package import canonical_json, validate_identity_graph, validate_role_term_sources

SCHEMA = "texas-bounded-acceptance/0.1"


class SuccessorContractError(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SuccessorContractError(code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pin(value: str, width: int, code: str) -> None:
    _require(isinstance(value, str) and re.fullmatch(rf"[a-f0-9]{{{width}}}", value) is not None, code)


def _status(person: dict[str, Any]) -> str | None:
    values = [person[key] for key in ("person_status", "identity_resolution_status", "status", "current_status")
              if person.get(key) not in (None, "")]
    normalized = [str(value).strip().upper() for value in values]
    if "PROVISIONAL" in normalized:
        return "PROVISIONAL"
    value = person.get("person_status") or person.get("identity_resolution_status")
    return str(value).strip().upper() if value not in (None, "") else None


def build_successor_contract(
    package_bytes: bytes,
    *,
    historical_live_evidence_sha256: str,
    historical_live_tested_commit: str,
    runtime_zip_sha256: str,
    identity_resolution_head: str,
    source_workbook_id: str,
    source_workbook_modified_time: str,
    house_division_id: str,
    senate_division_id: str,
) -> dict[str, Any]:
    """Build a fresh receipt for current package bytes without mutating source data."""
    _pin(historical_live_evidence_sha256, 64, "HISTORICAL_EVIDENCE_PIN_INVALID")
    _pin(historical_live_tested_commit, 40, "HISTORICAL_TESTED_COMMIT_INVALID")
    _pin(runtime_zip_sha256, 64, "RUNTIME_PIN_INVALID")
    _pin(identity_resolution_head, 40, "IDENTITY_RESOLUTION_HEAD_INVALID")
    _require(isinstance(source_workbook_id, str) and bool(source_workbook_id.strip()), "SOURCE_WORKBOOK_ID_INVALID")
    _require(isinstance(source_workbook_modified_time, str) and bool(source_workbook_modified_time.strip()),
             "SOURCE_WORKBOOK_MODIFIED_TIME_INVALID")
    try:
        package = json.loads(package_bytes)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SuccessorContractError("PACKAGE_JSON_INVALID") from exc
    _require(isinstance(package, dict) and package.get("schema_version") == "0.1", "PACKAGE_VERSION_UNSUPPORTED")
    _require(not validate_identity_graph(package.get("records")), "PACKAGE_IDENTITY_INVALID")
    records = package.get("records")
    _require(isinstance(records, dict), "PACKAGE_RECORDS_INVALID")
    _require(not validate_role_term_sources(records, package.get("provenance")), "PACKAGE_PROVENANCE_INVALID")

    jurisdiction = package.get("jurisdiction")
    qa = package.get("qa")
    _require(isinstance(jurisdiction, dict) and jurisdiction.get("state_abbr") == "TX" and jurisdiction.get("geoid") == "48",
             "TEXAS_PACKAGE_REQUIRED")
    _require(isinstance(qa, dict), "PACKAGE_QA_INVALID")
    for block in (jurisdiction, qa):
        _require(block.get("complete_jurisdiction") is False and block.get("publication_eligible") is False,
                 "EXPLICIT_BOUNDED_SCOPE_REQUIRED")
    _require(qa.get("parity_ok") is True and qa.get("qa_fail_count") == 0, "SOURCE_QA_FAILED")
    _require(type(qa.get("blocking_gap_count")) is int and qa["blocking_gap_count"] >= 0,
             "SOURCE_GAP_COUNT_INVALID")
    _require(isinstance(qa.get("blocking_gaps"), list)
             and len(qa["blocking_gaps"]) == qa["blocking_gap_count"], "SOURCE_GAP_COUNT_DRIFT")
    _require(isinstance(qa.get("address_tests"), list), "SOURCE_ADDRESS_TESTS_INVALID")

    for table in ("divisions", "offices", "people", "role_terms"):
        _require(isinstance(records.get(table), list) and len(records[table]) == 2,
                 "EXACT_TWO_CHAINS_REQUIRED")
    for table in ("bodies", "leadership_roles", "identifier_crosswalk"):
        _require(isinstance(records.get(table), list) and not records[table], "ADDITIONAL_SCOPE_UNSUPPORTED")
    _require(not any(records.get(table) for table in ("elections", "contests", "candidacies")),
             "ELECTION_SCOPE_UNSUPPORTED")

    statuses = {
        str(person.get("person_id") or person.get("id")): _status(person)
        for person in records["people"] if isinstance(person, dict)
    }
    _require(len(statuses) == 2 and all(value == "AUTHORITATIVE" for value in statuses.values()),
             "AUTHORITATIVE_PERSON_IDENTITY_REQUIRED")

    _, bindings = build_texas_internal_configuration(
        package, house_division_id=house_division_id, senate_division_id=senate_division_id)
    package_sha = _sha(package_bytes)
    office_ids = sorted(str(row.get("office_id") or row.get("id")) for row in records["offices"])
    person_ids = sorted(str(row.get("person_id") or row.get("id")) for row in records["people"])
    term_ids = sorted(str(row.get("role_term_id") or row.get("term_id") or row.get("id")) for row in records["role_terms"])

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA,
        "status": "INTERNAL_REVIEW_ACCEPTED",
        "scope": {
            "profile": "EXACT_TWO_OFFICE_REPRESENTATION",
            "jurisdiction_id": jurisdiction["jurisdiction_id"],
            "coverage_rule": "ALL_BINDINGS_REQUIRED",
            "address_domain": "HOUSE_49_INTERSECTION_SENATE_14",
            "bindings": bindings,
            "office_ids": office_ids,
            "person_ids": person_ids,
            "role_term_ids": term_ids,
            "omitted_data_meaning": "NOT_INCLUDED_NOT_ABSENT",
            "elections_included": False,
        },
        "authority": {
            "civic_facts": "CURRENT_GOVERNED_TX_WORKBOOK_SUCCESSOR_PACKAGE",
            "geography": "HISTORICAL_LIVE_ACCEPTANCE_PLUS_CURRENT_VERSION_GOVERNANCE",
            "canonical_ids": "PASS_THROUGH",
            "unknown_dates": "PRESERVE_UNKNOWN",
            "person_identity": "EXPLICIT_AUTHORITATIVE",
        },
        "person_identity_status": statuses,
        "inputs": {
            "package_sha256": package_sha,
            "live_evidence_zip_sha256": historical_live_evidence_sha256,
            "live_tested_commit": historical_live_tested_commit,
            "runtime_zip_sha256": runtime_zip_sha256,
            "identity_resolution_head": identity_resolution_head,
            "source_workbook_id": source_workbook_id,
            "source_workbook_modified_time": source_workbook_modified_time,
        },
        "acceptance": {
            "historical_live_address_controls": 2,
            "historical_live_boundary_coordinate_controls": 6,
            "historical_captured_integrity_checks": 26,
            "successor_civic_fact_validation": "PASS",
            "successor_identity_validation": "PASS",
            "geometry_evidence_reuse_scope": "GEOGRAPHY_ONLY__NO_OLD_REPRESENTATION_REPLAY",
            "geometry_governance_policy": "texas-legislative-geometry-governance/0.1",
        },
        "source_qa_preserved": {
            "blocking_gap_count": qa["blocking_gap_count"],
            "address_test_count": len(qa["address_tests"]),
            "qa_sha256": _sha(canonical_json(qa).encode("utf-8")),
        },
        "gate_disposition": {
            "BOUNDED_COVERAGE_CONTRACT": "RESOLVED_INTERNAL_ONLY",
            "GPS_BINDINGS": "VERIFIED_CAPTURED_CANDIDATE",
            "LIVE_ADDRESS_CONTROLS": "VERIFIED_HISTORICAL_GEOGRAPHY_EVIDENCE",
            "GEOMETRY_VERSION_GOVERNANCE": "RESOLVED_INTERNAL_ONLY",
            "PUBLIC_PERSON_IDENTITY": "RESOLVED_AUTHORITATIVE",
            "PRODUCTION_PARTIAL_PACKAGE_PROFILE": "SUPPORTED_NOT_ACTIVATED",
            "REPOSITORY_ACTIVATION": "NOT_ACTIVATED",
        },
        "complete_jurisdiction": False,
        "publication_eligible": False,
        "production_release_eligible": False,
        "canonical_writes": 0,
        "successor_note": (
            "Fresh receipt for successor package after Person identity resolution. Historical live evidence is carried "
            "only for geography controls; old captured representation output is not asserted equal to the successor "
            "authoritative package."
        ),
    }
    receipt["deterministic_sha256"] = _sha(canonical_json(receipt).encode("utf-8"))
    return receipt
