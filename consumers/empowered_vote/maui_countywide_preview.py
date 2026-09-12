#!/usr/bin/env python3
"""Explicit held Maui preview; residency qualifications never filter voters."""
from __future__ import annotations

import copy
import re
from typing import Any

from consumers.empowered_vote import representation
from consumers.empowered_vote.countywide_preview import PreviewError, require, source_ids

package_source = representation.package_source
GATE = "EV-MAUI-PREVIEW-001"
PACKAGE_ID = "jurisdiction-hi-maui-county"
CIVIC_ID = "jur-us-hi-maui-county"
CONSTITUENCY = "COUNTYWIDE_AT_LARGE_WITH_RESIDENCY_REQUIREMENT"
COUNCIL = {
    "wailuku-waihee-waikapu": "alice-lee",
    "upcountry": "yuki-lei-sugimura",
    "kahului": "kauanoe-batangan",
    "south-maui": "tom-cook",
    "lanai": "gabe-johnson",
    "west-maui": "tamara-paltin",
    "molokai": "keani-rawlins-fernandez",
    "east-maui": "shane-sinenci",
    "makawao-haiku-paia": "nohelani-uu-hodgins",
}
LEADERSHIP = {
    "leadership-hi-maui-chair-alice-lee": ("wailuku-waihee-waikapu", "alice-lee", "CHAIR", "Council Chair"),
    "leadership-hi-maui-vice-chair-yuki-lei-sugimura": ("upcountry", "yuki-lei-sugimura", "VICE_CHAIR", "Council Vice Chair"),
}


def office_contracts():
    return [{"office_id": "office-hi-maui-mayor", "constituency": "COUNTYWIDE", "seats": 1,
             "expected_person_id": "person-hi-maui-richard-bissen", "residency_area_id": None}] + [
        {"office_id": "office-hi-maui-council-" + area, "constituency": CONSTITUENCY, "seats": 1,
         "expected_person_id": "person-hi-maui-" + person,
         "residency_area_id": "division-hi-maui-residency-" + area}
        for area, person in COUNCIL.items()]


def _build(package, address, geographic, binding):
    require(isinstance(binding, dict), "MAUI_PREVIEW_BINDING_REQUIRED")
    require(binding.get("preview_version") == "0.1"
            and binding.get("binding_id") == "preview-hi-maui-countywide-v0.1"
            and binding.get("mode") == "MAUI_COUNTYWIDE_RESIDENCY_PREVIEW"
            and binding.get("preview_only") is True
            and binding.get("publication_eligible") is False
            and binding.get("complete_jurisdiction") is False,
            "MAUI_PREVIEW_CONTRACT_INVALID")
    require(binding.get("package_jurisdiction_id") == PACKAGE_ID
            and binding.get("civic_gps_jurisdiction_id") == CIVIC_ID
            and binding.get("geoid") == "15009"
            and not any(binding.get(k) for k in ("district_adapter_id", "division_template", "district_division_map")),
            "MAUI_PREVIEW_BINDING_UNSUPPORTED")
    expected = office_contracts()
    require(isinstance(binding.get("offices"), list)
            and sorted(binding["offices"], key=lambda row: row["office_id"])
                == sorted(expected, key=lambda row: row["office_id"])
            and all(type(row.get("seats")) is int for row in binding["offices"])
            and binding.get("expected_leadership_ids") == list(LEADERSHIP),
            "MAUI_PREVIEW_ROSTER_CONTRACT_INVALID")
    package_source._validate_package_shape(package)
    jurisdiction = package["jurisdiction"]
    require(jurisdiction.get("jurisdiction_id") == PACKAGE_ID
            and jurisdiction.get("geoid") == "15009" and jurisdiction.get("state_abbr") == "HI"
            and jurisdiction.get("jurisdiction_type") == "county" and not jurisdiction.get("division_id"),
            "MAUI_PREVIEW_PACKAGE_MISMATCH")
    normalized = representation.live_civic_gps.normalize_civic_gps_result(address, geographic)
    require(normalized.get("status") == "PASS", str(normalized.get("error") or "MAUI_GEOGRAPHY_INVALID"))
    require(CIVIC_ID in normalized["jurisdiction_ids"], "CIVIC_GPS_JURISDICTION_NOT_ACTIVE")
    require([j for j in normalized["jurisdiction_ids"] if j.endswith("-county")] == [CIVIC_ID],
            "MAUI_PREVIEW_AMBIGUOUS_COUNTY")
    records = package["records"]
    divisions = {r["division_id"]: r for r in records["divisions"]}
    require(len(records["divisions"]) == 9 and set(divisions) == {
        "division-hi-maui-residency-" + area for area in COUNCIL}, "MAUI_RESIDENCY_SET_DRIFT")
    sources = {r["source_id"] for r in package["provenance"]["source_evidence"]}
    require(len(sources) == len(package["provenance"]["source_evidence"]), "MAUI_DUPLICATE_SOURCE")
    for division in divisions.values():
        require(division.get("jurisdiction_id") == PACKAGE_ID
                and division.get("division_type") == "COUNCIL_RESIDENCY_AREA"
                and division.get("address_routing_level") == "RESIDENCY_QUALIFICATION",
                "MAUI_RESIDENCY_SEMANTICS_INVALID")
        source_ids(division, sources)
    offices = {r["office_id"]: r for r in records["offices"]}
    people = {r["person_id"]: r for r in records["people"]}
    terms = [representation.project_role_term(r) for r in records["role_terms"]]
    require(len(offices) == len(records["offices"]) == 10
            and set(offices) == {r["office_id"] for r in expected}, "MAUI_OFFICE_SET_DRIFT")
    require(len(terms) == len(people) == len(records["people"]) == 10
            and all(representation._is_current(t) for t in terms)
            and len({t["person_id"] for t in terms}) == 10,
            "MAUI_CURRENT_HOLDER_SET_DRIFT")
    leads = records["leadership_roles"]
    require(len(leads) == 2 and {r["leadership_id"] for r in leads} == set(LEADERSHIP),
            "MAUI_LEADERSHIP_SET_DRIFT")
    for lead in leads:
        area, person, role_type, role_title = LEADERSHIP[lead["leadership_id"]]
        require(lead.get("jurisdiction_id") == PACKAGE_ID
                and lead.get("body_id") == "body-hi-maui-county-council"
                and lead.get("office_id") == "office-hi-maui-council-" + area
                and lead.get("person_id") == "person-hi-maui-" + person
                and lead.get("role_type") == role_type and lead.get("role_title") == role_title
                and lead.get("status") == "CURRENT", "MAUI_LEADERSHIP_JOIN_INVALID")
        source_ids(lead, sources)
    projected = []
    for contract in expected:
        office = offices[contract["office_id"]]
        area_id = contract["residency_area_id"]
        require(office.get("jurisdiction_id") == PACKAGE_ID
                and office.get("constituency") == contract["constituency"]
                and office.get("selection_method") == "ELECTED"
                and office.get("status") == "ACTIVE" and type(office.get("seats")) is int
                and office["seats"] == 1 and office.get("represented_division_id") == area_id,
                "MAUI_OFFICE_SEMANTICS_INVALID")
        selected = [t for t in terms if t["office_id"] == office["office_id"]]
        require(len(selected) == 1 and selected[0]["person_id"] == contract["expected_person_id"],
                "MAUI_OFFICE_HOLDER_JOIN_INVALID")
        term = selected[0]
        expected_method = "APPOINTED" if term["person_id"] == "person-hi-maui-kauanoe-batangan" else "ELECTED"
        require(term.get("selection_type") == expected_method, "MAUI_HOLDER_SELECTION_INVALID")
        person = people[term["person_id"]]
        require(person.get("jurisdiction_id") == term.get("jurisdiction_id") == PACKAGE_ID,
                "MAUI_HOLDER_JURISDICTION_DRIFT")
        name = representation._person_name(person)
        require(isinstance(name, str) and bool(name.strip()), "MAUI_PERSON_NAME_MISSING")
        for row in (office, term, person):
            source_ids(row, sources)
        projected.append({"office_id": office["office_id"], "office_name": representation._office_name(office),
            "seat_capacity": 1, "constituency": contract["constituency"],
            "representation_scope": "COUNTYWIDE", "office": copy.deepcopy(office),
            "residency_qualification": copy.deepcopy(divisions.get(area_id)),
            "holders": [{"person_id": person["person_id"], "name": name,
                "person": copy.deepcopy(person), "role_term": copy.deepcopy(term),
                "leadership_roles": copy.deepcopy([r for r in leads if r["person_id"] == person["person_id"]])}]})
    digest = package_source.sha256_bytes(package_source.canonical_json_bytes(package))
    require(re.fullmatch(r"[a-f0-9]{64}", str(binding.get("expected_package_sha256", ""))) is not None
            and digest == binding["expected_package_sha256"], "MAUI_CORRECTED_PACKAGE_DIGEST_MISMATCH")
    return {"status": "PASS", "preview_gate": GATE, "scope": "MAUI_COUNTYWIDE_MAYOR_AND_COUNCIL_ONLY",
        "preview_only": True, "publication_eligible": False, "complete_jurisdiction": False,
        "canonical_writes": 0, "input_address": address, "matched_address": normalized.get("matched_address"),
        "package_jurisdiction_id": PACKAGE_ID, "civic_gps_jurisdiction_id": CIVIC_ID, "county_geoid": "15009",
        "office_count": 10, "current_holder_count": 10, "residency_area_count": 9,
        "applicable_offices": projected, "residency_areas": copy.deepcopy(records["divisions"]),
        "source_evidence": copy.deepcopy(package["provenance"]["source_evidence"]),
        "source_assertions": copy.deepcopy(package["provenance"]["source_assertions"]),
        "warnings": copy.deepcopy(package["warnings"])}


def preview_maui_representation(package: dict[str, Any], address: str, civic_gps_result: Any,
                                *, binding: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        result = _build(package, address, civic_gps_result, binding)
    except (PreviewError, package_source.PackageContractError) as exc:
        result = {"status": "FAIL-CLOSED", "error": getattr(exc, "code", str(exc))}
    except (KeyError, TypeError, ValueError, AttributeError):
        result = {"status": "FAIL-CLOSED", "error": "MAUI_PREVIEW_INPUT_INVALID"}
    result.update({"preview_only": True, "publication_eligible": False,
                   "complete_jurisdiction": False, "canonical_writes": 0})
    result["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(result))
    return result
