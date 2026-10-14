"""Validate explicitly declared, bounded factory Office and current-role counts.

This gate verifies count interpretation only. It supplies no identities, geography,
approval or exact service dates, and does not modify source records.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

PROFILES_PATH = Path(__file__).with_name("Civic_Tracker_Count_Profiles.json")
CONTRACT_SCHEMA = "CIVIC_FACTORY_COUNT_CONTRACT_v0.1"
BASES = {"OFFICE_CONTAINERS", "SEAT_CAPACITY"}


class CountContractError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CountContractError(f"Duplicate count-profile key: {key}")
        result[key] = value
    return result


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if value is None or isinstance(value, bool) or not str(value).strip():
        raise CountContractError(f"{label} requires an integer")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise CountContractError(f"{label} requires an integer") from exc
    if not number.is_finite() or number != number.to_integral_value() or number < minimum:
        raise CountContractError(f"{label} requires an integer >= {minimum}")
    return int(number)


def assess_factory_counts(package: Mapping[str, Any]) -> dict[str, Any] | None:
    """Gate declared pilots; leave unprofiled legacy packages without a sidecar unchanged."""
    try:
        raw = PROFILES_PATH.read_bytes()
        registry = json.loads(raw, object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CountContractError("Count-profile registry is missing or malformed") from exc
    if not isinstance(registry, dict) or registry.get("schema") != "CIVIC_TRACKER_COUNT_PROFILES_v0.1":
        raise CountContractError("Unsupported count-profile registry schema")
    profiles = registry.get("profiles")
    if not isinstance(profiles, dict) or registry.get("unlisted_jurisdiction_basis") != "SEAT_CAPACITY":
        raise CountContractError("Invalid count-profile registry")
    for jid, profile in profiles.items():
        if not isinstance(jid, str) or not jid.startswith("jurisdiction-") or jid != jid.strip() or not isinstance(profile, dict) or not isinstance(profile.get("tracker_count_basis"), str) or profile["tracker_count_basis"] not in BASES:
            raise CountContractError("Invalid jurisdiction count profile")
    jurisdiction = package.get("jurisdiction")
    if not isinstance(jurisdiction, Mapping):
        raise CountContractError("jurisdiction object is required")
    jid = jurisdiction.get("jurisdiction_id")
    qa = package.get("qa")
    contract_present = isinstance(qa, Mapping) and "factory_count_contract" in qa
    contract = qa.get("factory_count_contract") if isinstance(qa, Mapping) else None
    profile = profiles.get(jid) if isinstance(jid, str) else None
    if not contract_present and profile is None:
        return None
    if not isinstance(contract, Mapping):
        raise CountContractError(f"{jid}: qa.factory_count_contract is required")
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("jurisdiction_id") != jid:
        raise CountContractError("Count contract schema or jurisdiction binding is invalid")
    if contract.get("scope") != "ACTIVE_OFFICES_CURRENT_ROLE_TERMS":
        raise CountContractError("Count contract must declare its active/current record scope")
    basis = contract.get("tracker_count_basis")
    if not isinstance(basis, str) or basis not in BASES or (profile is not None and basis != profile["tracker_count_basis"]):
        raise CountContractError("Count basis is missing, invalid or disagrees with the jurisdiction profile")
    source_hash = contract.get("source_workbook_sha256")
    if not isinstance(source_hash, str) or re.fullmatch(r"[a-f0-9]{64}", source_hash) is None:
        raise CountContractError("Count contract requires the captured workbook SHA256")
    counts = {name: _integer(contract.get(name), name) for name in ("active_offices", "current_role_terms", "vacant_offices")}
    records = package.get("records")
    if not isinstance(records, Mapping) or not isinstance(records.get("offices"), list) or not isinstance(records.get("role_terms"), list):
        raise CountContractError("Count contract requires Office and RoleTerm record lists")
    offices = {}
    for row in records["offices"]:
        if not isinstance(row, Mapping) or row.get("jurisdiction_id") != jid or row.get("status") != "ACTIVE":
            raise CountContractError("Count scope must contain exact-jurisdiction ACTIVE Office rows")
        oid = row.get("office_id")
        if not isinstance(oid, str) or not oid.strip() or oid in offices:
            raise CountContractError("Office IDs must be present and unique")
        seats = _integer(row.get("seats"), f"{oid}.seats", 1)
        if "seat_count" in row and _integer(row["seat_count"], f"{oid}.seat_count", 1) != seats:
            raise CountContractError("Conflicting seats and seat_count")
        offices[oid] = (seats, row.get("occupancy_status"))
    if not offices:
        raise CountContractError("Count contract has no active Offices")
    terms = set()
    person_office_pairs = set()
    occupancy = Counter()
    for row in records["role_terms"]:
        if not isinstance(row, Mapping) or row.get("jurisdiction_id") != jid or row.get("status") != "CURRENT":
            raise CountContractError("Count scope must contain exact-jurisdiction CURRENT RoleTerm rows")
        rid, person, oid = row.get("role_term_id"), row.get("person_id"), row.get("office_id")
        if not isinstance(rid, str) or not rid.strip() or rid in terms or not isinstance(person, str) or not person.strip() or not isinstance(oid, str) or oid not in offices:
            raise CountContractError("RoleTerm identity or Office link is invalid")
        if (person, oid) in person_office_pairs:
            raise CountContractError("Duplicate current person/Office occupancy")
        terms.add(rid); person_office_pairs.add((person, oid)); occupancy[oid] += 1
    vacancy = 0
    for oid, (seats, status) in offices.items():
        if status == "FILLED" and occupancy[oid] == seats:
            continue
        if status == "VACANT" and occupancy[oid] == 0:
            vacancy += seats
            continue
        raise CountContractError(f"{oid}: observed occupancy disagrees with capacity/status")
    capacity = sum(seats for seats, _ in offices.values())
    reported_active = len(offices) if basis == "OFFICE_CONTAINERS" else capacity
    if counts != {"active_offices": reported_active, "current_role_terms": len(terms), "vacant_offices": vacancy}:
        raise CountContractError("Declared tracker counts disagree with observed scoped rows")
    return {
        "schema": CONTRACT_SCHEMA,
        "jurisdiction_id": jid,
        "tracker_count_basis": basis,
        "active_office_containers": len(offices),
        "seat_capacity": capacity,
        "current_role_terms": len(terms),
        "explicit_vacant_seats": vacancy,
        "source_workbook_sha256": source_hash,
        "profile_registry_sha256": hashlib.sha256(raw).hexdigest(),
        "status": "COUNT_CONTRACT_PASS",
    }
