#!/usr/bin/env python3
"""Representation-only projection from live Civic GPS geography to a governed package.

This path exists for governed Jurisdiction Package v0.1 artifacts that contain
current representation but do not yet govern Election/Contest/Candidacy data.
It never infers election facts and never writes to CivicData canonical data.
"""
from __future__ import annotations

import importlib.util
import copy
from datetime import date
import sys
from pathlib import Path
from typing import Any


def _load_sibling(module_name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


package_source = _load_sibling("ev_package_source_for_representation", "package_source.py")
live_civic_gps = _load_sibling("ev_live_civic_gps_for_representation", "live_civic_gps.py")


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": "EV-IMP-005",
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        out["detail"] = detail
    return out


def _id(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _person_name(row: dict[str, Any]) -> str | None:
    return row.get("name") or row.get("canonical_name") or row.get("Canonical_Name") or row.get("person_full_name")


def _office_name(row: dict[str, Any]) -> str | None:
    return row.get("name") or row.get("office_name") or row.get("Canonical_Name")


def _is_current(term: dict[str, Any]) -> bool:
    return str(term.get("status") or term.get("currentness_status") or "").upper() in {
        "CURRENT", "CURRENT_VERIFIED"
    }


def project_role_term(term: dict[str, Any]) -> dict[str, Any]:
    """Project known aliases without changing the canonical record or its IDs."""
    projected = copy.deepcopy(term)
    for destination, aliases in (
        ("status", ("status", "currentness_status", "role_term_status")),
        ("start_date", ("term_start", "start_date", "term_start_date")),
        ("end_date", ("term_end", "end_date", "term_end_date")),
    ):
        values = [term[key] if term[key] != "" else None for key in aliases if key in term]
        if any(value != values[0] for value in values[1:]):
            raise package_source.PackageContractError("ROLE_TERM_FIELD_CONFLICT", destination)
        if values:
            projected[destination] = values[0]
    for key in ("term_start_date", "term_end_date"):
        value = term.get(key)
        if value in (None, ""):
            continue
        try:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError("not an exact ISO date")
        except ValueError as exc:
            raise package_source.PackageContractError("ROLE_TERM_DATE_INVALID", key) from exc
    return projected


def _person_status(person: dict[str, Any]) -> str | None:
    # TX_PERSON's identity status must never be replaced by RoleTerm currentness.
    statuses = [person[key] for key in ("person_status", "status", "current_status", "identity_resolution_status")
                if person.get(key) not in (None, "")]
    if any(str(value).upper() == "PROVISIONAL" for value in statuses):
        return "PROVISIONAL"
    return person.get("person_status") or person.get("identity_resolution_status")


def _division_for_binding(
    package: dict[str, Any], normalized: dict[str, Any], binding: dict[str, Any], address: str
) -> tuple[str | None, dict[str, Any] | None]:
    if binding.get("district_adapter_id"):
        adapter_id = str(binding["district_adapter_id"])
        district_key = normalized["district_assignments"].get(adapter_id)
        if district_key is None:
            return None, _fail(address, "CIVIC_GPS_REQUIRED_DISTRICT_MISSING", adapter_id)
        mapping = binding.get("district_division_map")
        template = binding.get("division_template")
        if mapping is not None:
            if template or not isinstance(mapping, dict) or any(
                not isinstance(key, str) or not isinstance(value, str) or not value
                for key, value in mapping.items()
            ):
                return None, _fail(address, "CIVIC_GPS_DISTRICT_BINDING_INVALID", adapter_id)
            division_id = mapping.get(district_key)
            if division_id is None:
                return None, _fail(address, "CIVIC_GPS_DISTRICT_NOT_IN_BINDING", adapter_id)
        else:
            if not isinstance(template, str) or not template:
                return None, _fail(address, "CIVIC_GPS_DIVISION_TEMPLATE_MISSING", adapter_id)
            try:
                division_id = template.format(district_key=district_key)
            except (KeyError, ValueError, IndexError, AttributeError):
                return None, _fail(address, "CIVIC_GPS_DISTRICT_BINDING_INVALID", adapter_id)
    else:
        division_id = package.get("jurisdiction", {}).get("division_id")
        if not division_id:
            divisions = package.get("records", {}).get("divisions", [])
            if len(divisions) == 1 and isinstance(divisions[0], dict):
                division_id = _id(divisions[0], "division_id", "id")
    if not division_id:
        return None, _fail(address, "PACKAGE_REPRESENTATION_DIVISION_MISSING")
    package_divisions = {
        _id(row, "division_id", "id")
        for row in package.get("records", {}).get("divisions", [])
        if isinstance(row, dict)
    }
    if str(division_id) not in package_divisions:
        return None, _fail(address, "CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE", str(division_id))
    return str(division_id), None


def build_representation_from_civic_gps_result(
    package: dict[str, Any],
    address: str,
    civic_gps_result: Any,
    *,
    binding: dict[str, Any],
    identity_policy: str | None = None,
) -> dict[str, Any]:
    """Project current representation using Civic GPS only for geography."""
    caps = package_source.package_capabilities(package)
    if not caps.get("representation"):
        return _fail(address, "PACKAGE_REPRESENTATION_UNSUPPORTED")
    if identity_policy not in (None, "INTERNAL_REVIEW"):
        return _fail(address, "IDENTITY_POLICY_UNSUPPORTED")
    graph_errors = package_source.validate_identity_graph(package.get("records"))
    if graph_errors:
        return _fail(address, "PACKAGE_IDENTITY_GRAPH_INVALID", ",".join(graph_errors))
    evidence_errors = package_source.validate_role_term_sources(package["records"], package.get("provenance"))
    if evidence_errors:
        return _fail(address, "PACKAGE_ROLE_TERM_EVIDENCE_INVALID", ",".join(evidence_errors))
    if package.get("jurisdiction", {}).get("jurisdiction_id") != binding.get("package_jurisdiction_id"):
        return _fail(address, "CIVIC_GPS_PACKAGE_BINDING_UNSUPPORTED")

    normalized = live_civic_gps.normalize_civic_gps_result(address, civic_gps_result)
    if normalized.get("status") != "PASS":
        return _fail(address, str(normalized.get("error") or "CIVIC_GPS_GEOGRAPHY_INVALID"), normalized.get("detail"))

    civic_jurisdiction_id = str(binding.get("civic_gps_jurisdiction_id") or "")
    if not civic_jurisdiction_id or civic_jurisdiction_id not in normalized["jurisdiction_ids"]:
        return _fail(address, "CIVIC_GPS_JURISDICTION_NOT_ACTIVE", civic_jurisdiction_id or None)

    resolved_division_id, failure = _division_for_binding(package, normalized, binding, address)
    if failure is not None:
        return failure
    assert resolved_division_id is not None

    records = package["records"]
    people = {
        _id(row, "person_id", "id"): row
        for row in records.get("people", [])
        if isinstance(row, dict) and _id(row, "person_id", "id")
    }
    leadership = records.get("leadership_roles", [])
    try:
        projected_terms = [project_role_term(row) for row in records["role_terms"]]
    except package_source.PackageContractError as exc:
        return _fail(address, exc.code, exc.detail)
    current_terms = [row for row in projected_terms if _is_current(row)]
    warnings = copy.deepcopy(package.get("warnings", []))
    provisional_people: set[str] = set()

    offices: list[dict[str, Any]] = []
    for office in records.get("offices", []):
        if not isinstance(office, dict):
            continue
        geography = _id(office, "represented_division_id", "geography_id", "division_id")
        if geography != resolved_division_id:
            continue
        office_id = _id(office, "office_id", "id")
        if not office_id:
            return _fail(address, "PACKAGE_OFFICE_ID_MISSING")
        holders: list[dict[str, Any]] = []
        for term in current_terms:
            if _id(term, "office_id") != office_id:
                continue
            person_id = _id(term, "person_id")
            person = people.get(person_id, {}) if person_id else {}
            person_status = _person_status(person)
            if person_status == "PROVISIONAL":
                if identity_policy != "INTERNAL_REVIEW":
                    return _fail(address, "PERSON_IDENTITY_PROVISIONAL", person_id)
                provisional_people.add(person_id)
            roles = []
            for lead in leadership:
                if not isinstance(lead, dict):
                    continue
                if person_id and _id(lead, "person_id") != person_id:
                    continue
                lead_office = _id(lead, "office_id")
                if lead_office and lead_office != office_id:
                    continue
                if str(lead.get("status") or lead.get("currentness_status") or "CURRENT").upper() not in {"CURRENT", "CURRENT_VERIFIED"}:
                    continue
                role = lead.get("role") or lead.get("role_title")
                if role:
                    roles.append(str(role))
            holders.append({
                "role_term_id": _id(term, "role_term_id", "term_id", "id"),
                "person_id": person_id,
                "name": _person_name(person) if person else None,
                "selection_method": term.get("selection_method") or term.get("selection_type"),
                "status": term.get("status") or term.get("currentness_status"),
                "term_start": term.get("term_start") or term.get("start_date"),
                "term_end": term.get("term_end") or term.get("end_date"),
                "term_expiration_year": term.get("term_expiration_year"),
                "confidence": term.get("confidence"),
                "leadership_roles": sorted(set(roles)),
                "source_id": term.get("source_id"),
                "source_ids": term.get("source_ids"),
            })
            for key in ("source_record_id", "observed_at"):
                if key in term:
                    holders[-1][key] = term[key]
            if person_status is not None:
                holders[-1]["person_status"] = person_status
        holders.sort(key=lambda row: (str(row.get("name") or ""), str(row.get("person_id") or "")))
        seat_capacity = office.get("seats") or office.get("seat_count") or 1
        try:
            if int(seat_capacity) < len(holders):
                return _fail(address, "PACKAGE_REPRESENTATION_EXCEEDS_SEAT_CAPACITY", office_id)
        except (TypeError, ValueError):
            pass
        offices.append({
            "office_id": office_id,
            "office_name": _office_name(office),
            "classification_or_role": office.get("classification_or_role") or office.get("role"),
            "division_id": geography,
            "seat_capacity": seat_capacity,
            "current_status": office.get("current_status") or office.get("status"),
            "holders": holders,
            "source_id": office.get("source_id"),
            "source_ids": office.get("source_ids"),
        })
    offices.sort(key=lambda row: (str(row.get("office_name") or ""), str(row.get("office_id") or "")))

    holder_count = sum(len(row["holders"]) for row in offices)
    if not offices or holder_count == 0:
        return _fail(address, "PACKAGE_REPRESENTATION_EMPTY")

    for person_id in sorted(provisional_people):
        warning_id = "PROVISIONAL-PERSON:" + person_id
        if not any(row.get("warning_id") == warning_id for row in warnings if isinstance(row, dict)):
            warnings.append({"warning_id": warning_id, "person_id": person_id,
                             "status": "PROVISIONAL", "scope": "INTERNAL_REVIEW",
                             "summary": "Current service is recorded; Person identity remains provisional."})

    model: dict[str, Any] = {
        "status": "PASS",
        "consumer_gate": "EV-IMP-005",
        "representation_only": True,
        "full_essentials_supported": bool(caps.get("full_essentials")),
        "package_schema_version": package.get("schema_version"),
        "input_address": address,
        "matched_address": normalized.get("matched_address"),
        "address_resolution_source": "CIVIC_GPS_LIVE",
        "resolved_jurisdictions": normalized["jurisdiction_ids"],
        "district_assignments": normalized["district_assignments"],
        "resolved_division_id": resolved_division_id,
        "jurisdiction": package.get("jurisdiction"),
        "applicable_offices": offices,
        "current_holder_count": holder_count,
        "source_evidence": package.get("provenance", {}).get("source_evidence", []),
        "source_assertions": package.get("provenance", {}).get("source_assertions", []),
        "warnings": warnings,
        "canonical_writes": 0,
    }
    if identity_policy == "INTERNAL_REVIEW":
        model["identity_policy"] = identity_policy
        model["publication_eligible"] = False
    model["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(model))
    return model


def preview_representation_for_bindings(
    package: dict[str, Any], address: str, civic_gps_result: Any, *, bindings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compose an internal, bounded preview such as separate House/Senate joins.

    Bindings must be supplied by the caller. This creates no catalog entries,
    assumes no district IDs, and fails the whole preview if any binding fails.
    """
    if not isinstance(bindings, list) or not bindings:
        return _fail(address, "REPRESENTATION_BINDINGS_MISSING")
    names = [row.get("binding_id") if isinstance(row, dict) else None for row in bindings]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        return _fail(address, "REPRESENTATION_BINDING_ID_INVALID")
    projections, seen_offices = [], set()
    for binding in sorted(bindings, key=lambda row: row["binding_id"]):
        if not binding.get("district_adapter_id") or not (binding.get("division_template") or binding.get("district_division_map")):
            return _fail(address, "REPRESENTATION_DISTRICT_BINDING_REQUIRED", binding["binding_id"])
        model = build_representation_from_civic_gps_result(
            package, address, civic_gps_result, binding=binding, identity_policy="INTERNAL_REVIEW"
        )
        if model.get("status") != "PASS":
            return _fail(address, str(model.get("error")), binding["binding_id"])
        office_ids = {row["office_id"] for row in model["applicable_offices"]}
        if seen_offices & office_ids:
            return _fail(address, "REPRESENTATION_BINDING_OVERLAP", binding["binding_id"])
        seen_offices.update(office_ids)
        projections.append({"binding_id": binding["binding_id"], "representation": model})
    result = {"status": "PASS", "scope": "BOUND_BINDINGS_ONLY", "projections": projections,
              "complete_jurisdiction": False, "publication_eligible": False, "canonical_writes": 0}
    result["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(result))
    return result
