#!/usr/bin/env python3
"""Explicit Kauaʻi Mayor/Council preview; never used by catalog selection."""
from __future__ import annotations

import copy
from typing import Any

from consumers.empowered_vote import representation

package_source = representation.package_source
PACKAGE_ID = "jurisdiction-hi-kauai-county"
CIVIC_ID = "jur-us-hi-kauai-county"
OFFICES = {
    "office-hi-kauai-mayor": ("COUNTYWIDE", 1),
    "office-hi-kauai-council-member-multiseat": ("COUNTYWIDE_AT_LARGE", 7),
}


class PreviewError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PreviewError(code)


def source_ids(row: dict[str, Any], known: set[str]) -> None:
    refs = row.get("source_ids", [])
    if isinstance(refs, str):
        refs = [value.strip() for value in refs.split(";") if value.strip()]
    require(isinstance(refs, list), "PREVIEW_SOURCE_REFERENCES_INVALID")
    refs = refs + ([row["source_id"]] if row.get("source_id") else [])
    require(bool(refs) and all(isinstance(ref, str) and ref in known for ref in refs),
            "PREVIEW_SOURCE_EVIDENCE_MISSING")


def _build(package: dict[str, Any], address: str, geographic: Any,
           binding: dict[str, Any] | None) -> dict[str, Any]:
    require(isinstance(binding, dict), "COUNTYWIDE_PREVIEW_BINDING_REQUIRED")
    require(binding.get("preview_version") == "0.1"
            and binding.get("binding_id") == "preview-hi-kauai-countywide-v0.1"
            and binding.get("mode") == "COUNTYWIDE_PREVIEW"
            and binding.get("preview_only") is True
            and binding.get("publication_eligible") is False
            and binding.get("complete_jurisdiction") is False,
            "COUNTYWIDE_PREVIEW_CONTRACT_INVALID")
    require(binding.get("package_jurisdiction_id") == PACKAGE_ID
            and binding.get("civic_gps_jurisdiction_id") == CIVIC_ID
            and binding.get("geoid") == "15007"
            and not any(binding.get(k) for k in ("district_adapter_id", "division_template", "district_division_map")),
            "COUNTYWIDE_PREVIEW_BINDING_UNSUPPORTED")
    package_source._validate_package_shape(package)
    jurisdiction = package["jurisdiction"]
    require(jurisdiction.get("jurisdiction_id") == PACKAGE_ID
            and jurisdiction.get("geoid") == "15007"
            and jurisdiction.get("state_abbr") == "HI"
            and jurisdiction.get("jurisdiction_type") == "county",
            "COUNTYWIDE_PREVIEW_PACKAGE_MISMATCH")
    records = package["records"]
    require(records["divisions"] == [] and not jurisdiction.get("division_id"),
            "COUNTYWIDE_PREVIEW_DIVISION_SEMANTICS_UNSUPPORTED")

    normalized = representation.live_civic_gps.normalize_civic_gps_result(address, geographic)
    require(normalized.get("status") == "PASS", str(normalized.get("error") or "PREVIEW_GEOGRAPHY_INVALID"))
    require(CIVIC_ID in normalized["jurisdiction_ids"], "CIVIC_GPS_JURISDICTION_NOT_ACTIVE")
    counties = [value for value in normalized["jurisdiction_ids"] if value.endswith("-county")]
    require(counties == [CIVIC_ID], "COUNTYWIDE_PREVIEW_AMBIGUOUS_COUNTY")

    contracts = binding.get("offices")
    require(isinstance(contracts, list) and len(contracts) == 2, "COUNTYWIDE_PREVIEW_OFFICE_CONTRACT_INVALID")
    expected = {row["office_id"]: row for row in contracts}
    require(set(expected) == set(OFFICES), "COUNTYWIDE_PREVIEW_OFFICE_CONTRACT_INVALID")
    offices = {row["office_id"]: row for row in records["offices"]}
    require(set(offices) == set(OFFICES), "COUNTYWIDE_PREVIEW_OFFICE_SCOPE_DRIFT")
    sources = {row["source_id"] for row in package["provenance"]["source_evidence"]}
    people = {row["person_id"]: row for row in records["people"]}
    terms = [representation.project_role_term(row) for row in records["role_terms"]]
    current = [row for row in terms if representation._is_current(row)]
    require(len(current) == 8, "COUNTYWIDE_PREVIEW_HOLDER_COUNT_DRIFT")
    current_people = [row["person_id"] for row in current]
    require(len(set(current_people)) == 8, "COUNTYWIDE_PREVIEW_DUPLICATE_HOLDER")
    lead_rows = records["leadership_roles"]
    require(isinstance(binding.get("expected_leadership_ids"), list)
            and len(binding["expected_leadership_ids"]) == 2
            and len(set(binding["expected_leadership_ids"])) == 2
            and sorted(row.get("leadership_id") for row in lead_rows) == sorted(binding["expected_leadership_ids"]),
            "COUNTYWIDE_PREVIEW_LEADERSHIP_SET_DRIFT")
    for lead in lead_rows:
        require(lead.get("jurisdiction_id") == PACKAGE_ID
                and lead.get("body_id") == "body-hi-kauai-county-council"
                and lead.get("office_id") == "office-hi-kauai-council-member-multiseat"
                and lead.get("status") == "CURRENT"
                and any(row["person_id"] == lead.get("person_id")
                    and row["office_id"] == lead.get("office_id") for row in current),
                "COUNTYWIDE_PREVIEW_LEADERSHIP_JOIN_INVALID")
        source_ids(lead, sources)

    projected = []
    for office_id in sorted(OFFICES):
        office, contract = offices[office_id], expected[office_id]
        constituency, seats = OFFICES[office_id]
        require(contract.get("constituency") == constituency
                and type(contract.get("seats")) is int and contract["seats"] == seats,
                "COUNTYWIDE_PREVIEW_OFFICE_CONTRACT_INVALID")
        require(office.get("jurisdiction_id") == PACKAGE_ID
                and office.get("constituency") == constituency
                and office.get("status") == "ACTIVE"
                and not any(office.get(k) for k in ("represented_division_id", "geography_id", "division_id")),
                "COUNTYWIDE_PREVIEW_CONSTITUENCY_INVALID")
        require(type(office.get("seats")) is int and office["seats"] == seats,
                "COUNTYWIDE_PREVIEW_SEAT_CAPACITY_DRIFT")
        selected = [row for row in current if row["office_id"] == office_id]
        require(len(selected) == seats, "COUNTYWIDE_PREVIEW_OFFICE_HOLDER_COUNT_DRIFT")
        ids = contract.get("expected_person_ids")
        require(isinstance(ids, list) and len(ids) == seats and len(set(ids)) == seats
                and all(isinstance(value, str) and value for value in ids),
                "COUNTYWIDE_PREVIEW_PERSON_CONTRACT_INVALID")
        require(set(ids) == {row["person_id"] for row in selected}, "COUNTYWIDE_PREVIEW_PERSON_SET_DRIFT")
        source_ids(office, sources)
        holders = []
        for term in sorted(selected, key=lambda row: row["person_id"]):
            person = people[term["person_id"]]
            require(term.get("jurisdiction_id") == PACKAGE_ID
                    and person.get("jurisdiction_id") == PACKAGE_ID,
                    "COUNTYWIDE_PREVIEW_HOLDER_JURISDICTION_DRIFT")
            source_ids(term, sources)
            source_ids(person, sources)
            name = representation._person_name(person)
            require(isinstance(name, str) and bool(name.strip()), "COUNTYWIDE_PREVIEW_PERSON_NAME_MISSING")
            holders.append({
                "person_id": person["person_id"], "name": name,
                "person": copy.deepcopy(person), "role_term": copy.deepcopy(term),
                "leadership_roles": copy.deepcopy([row for row in lead_rows
                    if row.get("person_id") == person["person_id"] and row.get("office_id") == office_id]),
            })
        projected.append({"office_id": office_id, "office_name": representation._office_name(office),
                          "seat_capacity": seats, "constituency": constituency,
                          "office": copy.deepcopy(office), "holders": holders})

    return {"status": "PASS", "preview_gate": "EV-KAUAI-PREVIEW-001",
            "scope": "KAUAI_COUNTYWIDE_MAYOR_AND_COUNCIL_ONLY", "preview_only": True,
            "publication_eligible": False, "complete_jurisdiction": False, "canonical_writes": 0,
            "input_address": address, "matched_address": normalized.get("matched_address"),
            "package_jurisdiction_id": PACKAGE_ID, "civic_gps_jurisdiction_id": CIVIC_ID,
            "county_geoid": "15007", "applicable_offices": projected,
            "office_count": 2, "current_holder_count": 8,
            "source_evidence": copy.deepcopy(package["provenance"]["source_evidence"]),
            "source_assertions": copy.deepcopy(package["provenance"]["source_assertions"]),
            "warnings": copy.deepcopy(package["warnings"])}


def preview_countywide_representation(package: dict[str, Any], address: str, civic_gps_result: Any,
                                     *, binding: dict[str, Any] | None = None) -> dict[str, Any]:
    """Consume a validated package with an explicit preview binding; no production fallback."""
    try:
        result = _build(package, address, civic_gps_result, binding)
    except (PreviewError, package_source.PackageContractError) as exc:
        result = {"status": "FAIL-CLOSED", "error": getattr(exc, "code", str(exc)),
                  "preview_only": True, "publication_eligible": False,
                  "complete_jurisdiction": False, "canonical_writes": 0}
    except (KeyError, TypeError, ValueError, AttributeError):
        result = {"status": "FAIL-CLOSED", "error": "COUNTYWIDE_PREVIEW_INPUT_INVALID",
                  "preview_only": True, "publication_eligible": False,
                  "complete_jurisdiction": False, "canonical_writes": 0}
    result["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(result))
    return result
