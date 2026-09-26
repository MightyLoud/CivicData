#!/usr/bin/env python3
"""Export a governed CivicData Jurisdiction Package to Representation Contract v1.

This is a projection only. It preserves factory IDs as external identifiers and
mints deterministic UUIDv5 contract IDs so the legacy jurisdiction package stays
unchanged while consumers migrate.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from adapters.shared_identity import SharedIdentityResolutionError, SharedIdentityResolver

SCHEMA_VERSION = "1.0.0-draft"
CONTRACT_NAMESPACE = uuid5(NAMESPACE_URL, "https://civicdata.tech/representation-contract/v1")


class ExportError(ValueError):
    """Raised when a Factory package cannot be projected without guessing."""


def _contract_uuid(kind: str, source_id: str) -> str:
    return str(uuid5(CONTRACT_NAMESPACE, f"factory:{kind}:{source_id}"))


def _identifier(kind: str, source_id: str) -> dict[str, Any]:
    return {"scheme": f"civicdata_factory_{kind}", "id": source_id, "url": None}


def _split_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ExportError(f"cannot derive role slug from {value!r}")
    return slug


def _selection(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "election": "elected",
        "elected": "elected",
        "appointment": "appointed",
        "appointed": "appointed",
        "ex_officio": "ex_officio",
        "mixed": "mixed",
    }
    return aliases.get(normalized, "unknown")


def _legacy_jurisdiction_ocdid(source_id: str) -> str | None:
    match = re.fullmatch(r"jurisdiction:us/([a-z]{2})/([^/]+)", source_id)
    if not match:
        return None
    state, place = match.groups()
    return f"ocd-jurisdiction/country:us/state:{state}/place:{place}/government"


def _legacy_division_ocdid(source_id: str) -> str | None:
    match = re.fullmatch(
        r"division:us/([a-z]{2})/([^/]+)(?:/council_district_([^/]+))?",
        source_id,
    )
    if not match:
        return None
    state, place, district = match.groups()
    base = f"ocd-division/country:us/state:{state}/place:{place}"
    return base if district is None else f"{base}/council_district:{district}"


def _legacy_municipal_jurisdiction_to_ocd(value: str, jurisdiction: Mapping[str, Any]) -> str | None:
    """Convert only the governed legacy municipal ID shape; never guess counties or states."""
    match = re.fullmatch(r"jurisdiction:us/([a-z]{2})/([a-z0-9_-]+)", value)
    if not match:
        return None
    declared = " ".join(
        str(jurisdiction.get(key) or "")
        for key in ("jurisdiction_type", "municipal_type", "classification", "government_form")
    ).lower()
    municipal_markers = ("municip", "city", "town", "village", "borough")
    if declared and not any(marker in declared for marker in municipal_markers):
        return None
    state, place = match.groups()
    return f"ocd-jurisdiction/country:us/state:{state}/place:{place}/government"


def _legacy_division_to_ocd(value: str, *, jurisdiction_ocdid: str) -> str | None:
    """Convert legacy municipal division paths only when they agree with the jurisdiction OCDID."""
    match = re.fullmatch(
        r"division:us/([a-z]{2})/([a-z0-9_-]+)(?:/(council_district|ward|district)_([a-z0-9_-]+))?",
        value,
    )
    if not match:
        return None
    state, place, district_kind, district_key = match.groups()
    base = f"ocd-division/country:us/state:{state}/place:{place}"
    expected_jurisdiction = base.replace("ocd-division/", "ocd-jurisdiction/") + "/government"
    if expected_jurisdiction != jurisdiction_ocdid:
        return None
    if district_kind:
        return f"{base}/{district_kind}:{district_key}"
    return base


def _iso(value: Any, *, fallback: str | None = None) -> str:
    """Normalize Factory date/time text to JSON-Schema date-time."""
    if value in (None, ""):
        if fallback is None:
            raise ExportError("timestamp is required")
        return fallback
    text = str(value).strip()
    if text.endswith("Z"):
        return text
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError:
        pass
    try:
        parsed_date = date.fromisoformat(text)
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)\s+([A-Za-z_]+/[A-Za-z_]+)",
        text,
    )
    if match:
        clock = match.group(2)
        if len(clock) == 5:
            clock += ":00"
        parsed = datetime.fromisoformat(f"{match.group(1)}T{clock}")
        return parsed.replace(tzinfo=ZoneInfo(match.group(3))).isoformat()
    if fallback is not None:
        return fallback
    raise ExportError(f"unsupported timestamp {value!r}")


def _evidence_type(source_type: Any) -> str:
    value = str(source_type or "").upper()
    if "GIS" in value or "CENSUS" in value:
        return "gis"
    if "ELECTION" in value:
        return "election_record"
    if "CODE" in value or "CHARTER" in value or "ORDINANCE" in value or "DOCUMENT" in value:
        return "official_document"
    if "OFFICIAL" in value or "DIRECTORY" in value:
        return "official_web"
    return "other"


def _require_records(package: Mapping[str, Any]) -> Mapping[str, Any]:
    records = package.get("records")
    if not isinstance(records, Mapping):
        raise ExportError("records object is required")
    for table in ("divisions", "bodies", "offices", "people", "role_terms"):
        if not isinstance(records.get(table), list):
            raise ExportError(f"records.{table} must be a list")
    return records


def export_factory_package(
    package: Mapping[str, Any],
    *,
    generated_at: str | None = None,
    governed_package: bool = False,
    identity_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(package, Mapping):
        raise ExportError("package must be an object")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    try:
        identity_resolver = SharedIdentityResolver(identity_registry)
    except SharedIdentityResolutionError as exc:
        raise ExportError(str(exc)) from exc
    records = _require_records(package)
    jurisdiction = package.get("jurisdiction")
    if not isinstance(jurisdiction, Mapping):
        raise ExportError("jurisdiction object is required")

    jurisdiction_id = str(jurisdiction.get("jurisdiction_id") or "")
    ocdid = str(jurisdiction.get("ocd_jurisdiction_id") or jurisdiction.get("jurisdiction_ocdid") or "")
    if not ocdid and jurisdiction_id:
        ocdid = _legacy_municipal_jurisdiction_to_ocd(jurisdiction_id, jurisdiction) or ""
    if not jurisdiction_id or not ocdid.startswith("ocd-jurisdiction/"):
        raise ExportError("Factory jurisdiction_id and a governed jurisdiction OCDID/crosswalk are required")
    name = str(jurisdiction.get("name") or "").strip()
    if not name:
        raise ExportError("jurisdiction.name is required")

    divisions_by_id: dict[str, Mapping[str, Any]] = {}
    for row in records["divisions"]:
        source_id = str(row.get("division_id") or row.get("id") or "")
        division_ocdid = str(row.get("ocd_division_id") or row.get("division_ocdid") or "")
        if not division_ocdid and source_id:
            division_ocdid = _legacy_division_to_ocd(source_id, jurisdiction_ocdid=ocdid) or ""
        if not source_id or not division_ocdid.startswith("ocd-division/"):
            raise ExportError(
                f"Factory division lacks a governed OCD crosswalk: {source_id or '<missing>'}"
            )
        normalized_row = dict(row)
        normalized_row["_contract_division_ocdid"] = division_ocdid
        divisions_by_id[source_id] = normalized_row

    evidence_rows = package.get("provenance", {}).get("source_evidence", [])
    if not isinstance(evidence_rows, list):
        raise ExportError("provenance.source_evidence must be a list")
    evidence_id_map: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []
    for source in evidence_rows:
        source_id = str(source.get("source_id") or source.get("Source_ID") or "")
        url = str(
            source.get("url")
            or source.get("Source_URL_or_File")
            or source.get("source_url")
            or ""
        )
        if not source_id or not url:
            raise ExportError("Factory evidence requires source_id + url")
        contract_id = _contract_uuid("evidence", source_id)
        evidence_id_map[source_id] = contract_id
        evidence.append(
            {
                "id": contract_id,
                "source_system": "jurisdiction_factory",
                "source_type": _evidence_type(source.get("source_type")),
                "url": url,
                "title": source.get("title") or source.get("Title"),
                "captured_at": _iso(
                    source.get("accessed_at")
                    or source.get("Verified_As_Of_ISO")
                    or source.get("verified_as_of"),
                    fallback=generated_at,
                ),
                "content_hash": source.get("content_hash") or None,
                "raw_record": copy.deepcopy(dict(source)),
            }
        )

    organizations: list[dict[str, Any]] = []
    organization_id_map: dict[str, str] = {}
    for body in records["bodies"]:
        body_id = str(body.get("body_id") or body.get("id") or "")
        if not body_id:
            raise ExportError("Factory body_id is required")
        contract_id = _contract_uuid("organization", body_id)
        organization_id_map[body_id] = contract_id
        parent_source = body.get("parent_body_id")
        try:
            shared_identity_id = identity_resolver.resolve(
                entity_type="organization",
                system="jurisdiction_factory",
                external_id=body_id,
            )
        except SharedIdentityResolutionError as exc:
            raise ExportError(str(exc)) from exc
        organizations.append(
            {
                "id": contract_id,
                "shared_identity_id": shared_identity_id,
                "jurisdiction_ocdid": ocdid,
                "name": str(body.get("name") or body_id),
                "classification": "board" if "BOARD" in str(body.get("body_type") or "").upper() else "other",
                "parent_organization_id": (
                    _contract_uuid("organization", str(parent_source)) if parent_source else None
                ),
                "url": body.get("official_url") or body.get("url") or None,
                "is_default": len(records["bodies"]) == 1,
                "identifiers": [_identifier("body", body_id)],
            }
        )

    roles_by_slug: dict[str, dict[str, Any]] = {}
    posts: list[dict[str, Any]] = []
    post_id_map: dict[str, str] = {}
    office_role: dict[str, str] = {}
    office_body_map: dict[str, str] = {}
    for office in records["offices"]:
        office_id = str(office.get("office_id") or office.get("id") or "")
        body_id = str(office.get("body_id") or office.get("parent_id") or "")
        represented = str(
            office.get("represented_division_id")
            or office.get("geography_id")
            or office.get("division_id")
            or ""
        )
        if not body_id and office_id.startswith("office:"):
            exact_body = "body:" + office_id.removeprefix("office:")
            if exact_body in organization_id_map:
                body_id = exact_body
        if not body_id and len(organization_id_map) == 1:
            body_id = next(iter(organization_id_map))
        if not office_id or body_id not in organization_id_map or represented not in divisions_by_id:
            raise ExportError(
                "Factory office graph is incomplete: "
                f"{office_id or '<missing>'}; body={body_id or '<missing>'}; "
                f"division={represented or '<missing>'}; "
                f"known_bodies={sorted(organization_id_map)}; "
                f"known_divisions={sorted(divisions_by_id)}; "
                f"raw_office={dict(office)}"
            )
        office_body_map[office_id] = body_id
        role_label = str(
            office.get("office_name")
            or office.get("name")
            or office.get("Canonical_Name")
            or office.get("office_type")
            or office.get("classification_or_role")
            or ""
        ).strip()
        role_id = _slug(
            str(
                office.get("office_type")
                or office.get("classification_or_role")
                or office.get("role")
                or role_label
            ).replace("_", " ")
        )
        office_role[office_id] = role_id
        roles_by_slug.setdefault(
            role_id,
            {
                "id": role_id,
                "label": role_label or role_id.replace("-", " ").title(),
                "status": "active",
                "is_unique": int(office.get("seats") or office.get("seat_count") or 1) == 1,
                "aliases": [],
                "identifiers": [],
            },
        )
        contract_id = _contract_uuid("post", office_id)
        post_id_map[office_id] = contract_id
        division_ocdid = str(
            divisions_by_id[represented].get("_contract_division_ocdid")
            or divisions_by_id[represented].get("ocd_division_id")
            or divisions_by_id[represented].get("division_ocdid")
        )
        posts.append(
            {
                "id": contract_id,
                "jurisdiction_ocdid": ocdid,
                "organization_id": organization_id_map[body_id],
                "role_id": role_id,
                "label": role_label or None,
                "division_ocdid": division_ocdid,
                "electorate_division_ocdid": None,
                "meta_headcount": int(office.get("seats") or office.get("seat_count") or 1),
                "meta_is_tracked": str(
                    office.get("status") or office.get("current_status") or "ACTIVE"
                ).upper() in {"ACTIVE", "CURRENT", "CURRENT_VERIFIED"},
                "selection_method": _selection(office.get("selection_method")),
                "identifiers": [_identifier("office", office_id)],
            }
        )

    people: list[dict[str, Any]] = []
    person_id_map: dict[str, str] = {}
    for person in records["people"]:
        person_id = str(person.get("person_id") or person.get("id") or "")
        person_name = str(person.get("canonical_name") or person.get("name") or "").strip()
        if not person_id or not person_name:
            raise ExportError("Factory person requires person_id + canonical_name")
        contract_id = _contract_uuid("person", person_id)
        person_id_map[person_id] = contract_id
        try:
            shared_identity_id = identity_resolver.resolve(
                entity_type="person",
                system="jurisdiction_factory",
                external_id=person_id,
            )
        except SharedIdentityResolutionError as exc:
            raise ExportError(str(exc)) from exc
        people.append(
            {
                "id": contract_id,
                "shared_identity_id": shared_identity_id,
                "name": person_name,
                "other_names": _split_ids(person.get("aliases")),
                "phones": [str(person["phone"])] if person.get("phone") else [],
                "emails": [str(person["email"])] if person.get("email") else [],
                "urls": (
                    [str(person["official_url"])]
                    if person.get("official_url")
                    else ([str(person["url"])] if person.get("url") else [])
                ),
                "image": person.get("image_url") or None,
                "identifiers": [_identifier("person", person_id)],
            }
        )

    leadership_by_pair: dict[tuple[str, str], Mapping[str, Any]] = {}
    leadership_subject_map: dict[str, str] = {}
    for leadership in records.get("leadership_roles", []):
        person_id = str(leadership.get("person_id") or "")
        office_id = str(leadership.get("office_id") or "")
        if person_id and office_id:
            leadership_by_pair[(person_id, office_id)] = leadership

    assertions_by_role_term: dict[str, list[Mapping[str, Any]]] = {}
    source_assertions = package.get("provenance", {}).get("source_assertions", [])
    if not isinstance(source_assertions, list):
        raise ExportError("provenance.source_assertions must be a list")
    for assertion in source_assertions:
        if str(assertion.get("subject_type") or "").lower() == "roleterm":
            assertions_by_role_term.setdefault(str(assertion.get("subject_id") or ""), []).append(assertion)

    memberships: list[dict[str, Any]] = []
    membership_id_map: dict[str, str] = {}
    for term in records["role_terms"]:
        term_id = str(term.get("role_term_id") or term.get("term_id") or term.get("id") or "")
        person_id = str(term.get("person_id") or "")
        office_id = str(term.get("office_id") or "")
        body_id = str(term.get("body_id") or "")
        if not body_id:
            body_id = office_body_map.get(office_id, "")
        if not body_id:
            source_office = next(
                (
                    row for row in records["offices"]
                    if str(row.get("office_id") or row.get("id") or "") == office_id
                ),
                None,
            )
            body_id = str(
                (source_office or {}).get("body_id")
                or (source_office or {}).get("parent_id")
                or ""
            )
            if not body_id and office_id.startswith("office:"):
                exact_body = "body:" + office_id.removeprefix("office:")
                if exact_body in organization_id_map:
                    body_id = exact_body
            if not body_id and len(organization_id_map) == 1:
                body_id = next(iter(organization_id_map))
        if (
            not term_id
            or person_id not in person_id_map
            or office_id not in post_id_map
            or body_id not in organization_id_map
        ):
            raise ExportError(f"Factory role term graph is incomplete: {term_id or '<missing>'}")
        contract_id = _contract_uuid("membership", term_id)
        membership_id_map[term_id] = contract_id

        source_ids = _split_ids(term.get("source_ids") or term.get("source_id"))
        if term.get("source_id"):
            source_ids.append(str(term["source_id"]))
        sources: list[dict[str, Any]] = []
        evidence_by_source = {
            str(row.get("source_id") or row.get("Source_ID")): row
            for row in evidence_rows
            if row.get("source_id") or row.get("Source_ID")
        }
        for source_id in source_ids:
            source = evidence_by_source.get(source_id)
            if source:
                source_url = (
                    source.get("url")
                    or source.get("Source_URL_or_File")
                    or source.get("source_url")
                )
                if source_url:
                    sources.append(
                        {
                            "url": str(source_url),
                            "note": source.get("title") or source.get("Title"),
                        }
                    )
        if not sources:
            raise ExportError(f"Factory role term has no resolvable source URL: {term_id}")

        source_end = (
            term.get("valid_to")
            or term.get("term_end")
            or term.get("end_date")
            or term.get("term_end_date")
            or term.get("term_expiration_year")
        )
        if not source_end:
            for assertion in assertions_by_role_term.get(term_id, []):
                if assertion.get("predicate") == "term_expiration_year" and assertion.get("object_value"):
                    source_end = str(assertion["object_value"])
                    break

        leadership = leadership_by_pair.get((person_id, office_id))
        label = (
            str(leadership.get("role_title") or leadership.get("role"))
            if leadership and (leadership.get("role_title") or leadership.get("role"))
            else None
        )
        if leadership and leadership.get("leadership_id"):
            leadership_subject_map[str(leadership["leadership_id"])] = contract_id

        memberships.append(
            {
                "id": contract_id,
                "post_id": post_id_map[office_id],
                "organization_id": organization_id_map[body_id],
                "person_id": person_id_map[person_id],
                "designations": [],
                "label": label,
                "start_date": (
                    term.get("valid_from")
                    or term.get("term_start")
                    or term.get("start_date")
                    or term.get("term_start_date")
                    or None
                ),
                "end_date": source_end or None,
                "opened_at": _iso(
                    term.get("row_updated_at") or term.get("observed_at"),
                    fallback=generated_at,
                ),
                "closed_at": (
                    None
                    if str(
                        term.get("status")
                        or term.get("currentness_status")
                        or term.get("role_term_status")
                        or ""
                    ).upper()
                    in {"CURRENT", "CURRENT_VERIFIED"}
                    else generated_at
                ),
                "sources": sources,
                "identifiers": [_identifier("role_term", term_id)],
            }
        )


    election_tables = ("elections", "contests", "candidacies")
    election_presence = [isinstance(records.get(name), list) for name in election_tables]
    if any(election_presence) and not all(election_presence):
        raise ExportError("Election extension requires elections + contests + candidacies together")

    elections: list[dict[str, Any]] = []
    contests: list[dict[str, Any]] = []
    candidacies: list[dict[str, Any]] = []
    election_id_map: dict[str, str] = {}
    contest_id_map: dict[str, str] = {}
    candidacy_id_map: dict[str, str] = {}

    def election_evidence_ids(source_refs: Any, *, context: str) -> list[str]:
        refs = _split_ids(source_refs)
        if not refs:
            raise ExportError(f"{context} requires source evidence")
        resolved = []
        for source_id in refs:
            evidence_id = evidence_id_map.get(source_id)
            if evidence_id is None:
                raise ExportError(f"{context} references missing evidence: {source_id}")
            resolved.append(evidence_id)
        return resolved

    if all(election_presence):
        for election in records["elections"]:
            source_id = str(election.get("election_id") or election.get("id") or "")
            election_date = str(election.get("election_date") or "")
            if not source_id or re.fullmatch(r"\d{4}-\d{2}-\d{2}", election_date) is None:
                raise ExportError("Election requires election_id + YYYY-MM-DD election_date")
            contract_id = _contract_uuid("election", source_id)
            election_id_map[source_id] = contract_id
            elections.append(
                {
                    "id": contract_id,
                    "jurisdiction_ocdid": ocdid,
                    "election_date": election_date,
                    "name": election.get("election_name") or election.get("name") or None,
                    "identifiers": [_identifier("election", source_id)],
                    "evidence_ids": election_evidence_ids(
                        election.get("source_ids") or election.get("source_id"),
                        context=f"election {source_id}",
                    ),
                }
            )

        for contest in records["contests"]:
            source_id = str(contest.get("contest_id") or contest.get("id") or "")
            election_source_id = str(contest.get("election_id") or "")
            office_source_id = str(contest.get("office_id") or "")
            name = str(contest.get("contest_name") or contest.get("name") or "").strip()
            if (
                not source_id
                or election_source_id not in election_id_map
                or office_source_id not in post_id_map
                or not name
            ):
                raise ExportError(f"Contest graph is incomplete: {source_id or '<missing>'}")
            contract_id = _contract_uuid("contest", source_id)
            contest_id_map[source_id] = contract_id
            contests.append(
                {
                    "id": contract_id,
                    "election_id": election_id_map[election_source_id],
                    "post_id": post_id_map[office_source_id],
                    "name": name,
                    "identifiers": [_identifier("contest", source_id)],
                    "evidence_ids": election_evidence_ids(
                        contest.get("source_ids") or contest.get("source_id"),
                        context=f"contest {source_id}",
                    ),
                }
            )

        for candidacy in records["candidacies"]:
            source_id = str(candidacy.get("candidacy_id") or candidacy.get("id") or "")
            contest_source_id = str(candidacy.get("contest_id") or "")
            source_candidate_id = str(candidacy.get("source_candidate_id") or "")
            candidate_name = str(candidacy.get("candidate_name") or "").strip()
            raw_kind = str(candidacy.get("candidate_kind") or "").strip().upper()
            if raw_kind == "PERSON":
                candidate_kind = "person"
                source_person_id = str(candidacy.get("person_id") or "")
                if source_person_id not in person_id_map:
                    raise ExportError(f"Named candidacy has unresolved person: {source_id}")
                contract_person_id: str | None = person_id_map[source_person_id]
            elif raw_kind == "WRITE_IN_BUCKET":
                candidate_kind = "write_in_bucket"
                if candidacy.get("person_id") not in (None, ""):
                    raise ExportError(f"Write-in bucket cannot resolve to Person: {source_id}")
                contract_person_id = None
            else:
                raise ExportError(f"Unsupported candidate_kind for {source_id}: {raw_kind or '<missing>'}")

            if (
                not source_id
                or contest_source_id not in contest_id_map
                or not source_candidate_id
                or not candidate_name
            ):
                raise ExportError(f"Candidacy graph is incomplete: {source_id or '<missing>'}")

            raw_outcome = candidacy.get("outcome")
            outcome = None
            if raw_outcome not in (None, ""):
                normalized_outcome = str(raw_outcome).strip().lower()
                outcome = normalized_outcome if normalized_outcome in {"winner", "loser", "other"} else "unknown"

            contract_id = _contract_uuid("candidacy", source_id)
            candidacy_id_map[source_id] = contract_id
            candidacies.append(
                {
                    "id": contract_id,
                    "contest_id": contest_id_map[contest_source_id],
                    "candidate_kind": candidate_kind,
                    "source_candidate_id": source_candidate_id,
                    "person_id": contract_person_id,
                    "candidate_name": candidate_name,
                    "ballot_name": candidacy.get("ballot_name") or None,
                    "outcome": outcome,
                    "votes": int(candidacy["votes"]) if candidacy.get("votes") not in (None, "") else None,
                    "vote_share": float(candidacy["vote_share"]) if candidacy.get("vote_share") not in (None, "") else None,
                    "identifiers": [_identifier("candidacy", source_id)],
                    "evidence_ids": election_evidence_ids(
                        candidacy.get("source_id") or candidacy.get("source_ids"),
                        context=f"candidacy {source_id}",
                    ),
                }
            )

    subject_maps: dict[str, dict[str, str]] = {
        "jurisdiction": {jurisdiction_id: ocdid},
        "body": organization_id_map,
        "office": post_id_map,
        "person": person_id_map,
        "roleterm": membership_id_map,
        "leadershiprole": leadership_subject_map,
        "election": election_id_map,
        "contest": contest_id_map,
        "candidacy": candidacy_id_map,
    }
    subject_types = {
        "jurisdiction": "jurisdiction",
        "body": "organization",
        "office": "post",
        "person": "person",
        "roleterm": "membership",
        "leadershiprole": "membership",
        "election": "election",
        "contest": "contest",
        "candidacy": "candidacy",
    }
    assertions: list[dict[str, Any]] = []
    for source_assertion in source_assertions:
        source_type = str(source_assertion.get("subject_type") or "").lower()
        source_subject = str(source_assertion.get("subject_id") or "")
        subject_id = subject_maps.get(source_type, {}).get(source_subject)
        if subject_id is None:
            continue
        source_id = str(source_assertion.get("source_id") or "")
        evidence_id = evidence_id_map.get(source_id)
        if evidence_id is None:
            continue
        assertion_id = str(source_assertion.get("assertion_id") or "")
        if not assertion_id:
            raise ExportError("Factory source assertion requires assertion_id")
        field_path = str(source_assertion.get("predicate") or "").strip()
        if source_type == "leadershiprole":
            field_path = f"leadership.{field_path}"
        source_normalization_status = str(
            source_assertion.get("normalized_status") or ""
        ).strip().upper()
        if source_normalization_status == "NORMALIZED":
            review_status = "accepted"
            reviewed_at = generated_at
        elif source_normalization_status == "CONFLICT":
            review_status = "held"
            reviewed_at = generated_at
        else:
            review_status = "proposed"
            reviewed_at = None
        assertions.append(
            {
                "id": _contract_uuid("assertion", assertion_id),
                "subject_type": subject_types[source_type],
                "subject_id": subject_id,
                "field_path": field_path or "unknown",
                "value": source_assertion.get("object_value"),
                "evidence_ids": [evidence_id],
                "source_system": "jurisdiction_factory",
                "review_status": review_status,
                "confidence": None,
                "asserted_at": generated_at,
                "reviewed_at": reviewed_at,
            }
        )

    qa = package.get("qa")
    if not isinstance(qa, Mapping):
        raise ExportError("qa object is required")
    raw_complete = bool(evidence)
    normalized_complete = all(
        isinstance(records.get(table), list) and bool(records.get(table))
        for table in ("divisions", "bodies", "offices", "people", "role_terms")
    )
    qa_passed = (
        qa.get("qa_fail_count") == 0
        and qa.get("blocking_gap_count") == 0
        and qa.get("qa_passed", True) is not False
    )
    parity_ok = qa.get("parity_ok") is True
    address_tests = qa.get("address_tests", [])
    address_controls_passed = (
        isinstance(address_tests, list)
        and len(address_tests) >= 2
        and all(
            isinstance(row, Mapping) and row.get("result") is True
            for row in address_tests
        )
    )
    explicit_complete = any(
        jurisdiction.get(field) is True
        for field in ("release_ready", "complete_flag", "complete_jurisdiction")
    )
    # Older governed package archives predate release_ready/complete_flag. They may
    # be promoted only when the caller explicitly establishes that they came through
    # the governed catalog boundary; the ordinary exporter never assumes this.
    factory_complete = explicit_complete or (governed_package and address_controls_passed)
    certified = raw_complete and normalized_complete and qa_passed and parity_ok and factory_complete

    election_extension_present = all(election_presence)
    election_scope_complete = package.get("qa", {}).get("election_scope_complete") is True
    unexplained_loss_raw = package.get("qa", {}).get("unexplained_loss")
    unexplained_loss = (
        int(unexplained_loss_raw)
        if unexplained_loss_raw not in (None, "")
        else 0
    )
    election_certified = (
        election_extension_present
        and certified
        and election_scope_complete
        and unexplained_loss == 0
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "jurisdiction": {
            "jurisdiction_ocdid": ocdid,
            "name": name,
            "classification": jurisdiction.get("classification") or jurisdiction.get("jurisdiction_type"),
            "url": jurisdiction.get("official_url") or jurisdiction.get("url") or None,
            "identifiers": [_identifier("jurisdiction", jurisdiction_id)],
        },
        "organizations": organizations,
        "roles": sorted(roles_by_slug.values(), key=lambda row: row["id"]),
        "posts": posts,
        "people": people,
        "memberships": memberships,
        "evidence": evidence,
        "assertions": assertions,
        "certification": {
            "status": "certified" if certified else ("evidence_review" if raw_complete else "uncertified"),
            "raw_complete": raw_complete,
            "normalized_complete": normalized_complete,
            "qa_passed": qa_passed,
            "parity_ok": parity_ok,
            "verified_at": _iso(jurisdiction.get("row_updated_at"), fallback=generated_at),
            "factory_extension": {
                "factory_complete": factory_complete,
                "blocker_code": None if certified else "FACTORY_GATES_INCOMPLETE",
            },
        },
    }

    if election_extension_present:
        payload["elections"] = elections
        payload["contests"] = contests
        payload["candidacies"] = candidacies
        payload["election_certification"] = {
            "status": "certified" if election_certified else "incomplete",
            "scope_complete": election_scope_complete,
            "unexplained_loss": unexplained_loss,
            "qa_passed": qa_passed,
            "verified_at": _iso(jurisdiction.get("row_updated_at"), fallback=generated_at),
        }

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CivicData jurisdiction.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at", help="Deterministic date-time for reproducible builds")
    parser.add_argument(
        "--identity-registry",
        type=Path,
        help="Optional reviewed shared identity registry JSON",
    )
    args = parser.parse_args(argv)
    package = json.loads(args.input.read_text(encoding="utf-8"))
    identity_registry = (
        json.loads(args.identity_registry.read_text(encoding="utf-8"))
        if args.identity_registry
        else None
    )
    payload = export_factory_package(
        package,
        generated_at=args.generated_at,
        identity_registry=identity_registry,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
