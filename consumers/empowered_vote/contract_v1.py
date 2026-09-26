#!/usr/bin/env python3
"""Empowered Vote read-only consumer for Representation Contract v1.

This module is deliberately parallel to the existing Jurisdiction Package
consumer. It consumes only certified representation snapshots for public output,
uses Civic GPS only for geography, and performs zero canonical writes.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import live_civic_gps, package_source

CONTRACT_VERSION = "1.0.0-draft"
CONSUMER_GATE = "EV-RC1-001"


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": CONSUMER_GATE,
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        out["detail"] = detail
    return out


def _identifier(row: Mapping[str, Any], scheme: str) -> str | None:
    for identifier in row.get("identifiers") or []:
        if (
            isinstance(identifier, Mapping)
            and identifier.get("scheme") == scheme
            and identifier.get("id") not in (None, "")
        ):
            return str(identifier["id"])
    return None


def _base_division_ocdid(jurisdiction_ocdid: str) -> str | None:
    if not jurisdiction_ocdid.startswith("ocd-jurisdiction/"):
        return None
    path = jurisdiction_ocdid.removeprefix("ocd-jurisdiction/")
    if "/" not in path:
        return None
    parent, classification = path.rsplit("/", 1)
    if classification not in {"government", "legislature"}:
        return None
    return "ocd-division/" + parent


def validate_contract(
    contract: Mapping[str, Any],
    *,
    require_certified: bool = True,
    require_elections: bool = False,
) -> list[str]:
    """Validate the semantic graph needed by the Empowered Vote consumer."""
    errors: list[str] = []
    if not isinstance(contract, Mapping):
        return ["CONTRACT_INVALID"]
    if contract.get("schema_version") != CONTRACT_VERSION:
        errors.append("CONTRACT_VERSION_UNSUPPORTED")

    jurisdiction = contract.get("jurisdiction")
    if not isinstance(jurisdiction, Mapping) or not str(
        jurisdiction.get("jurisdiction_ocdid") or ""
    ).startswith("ocd-jurisdiction/"):
        errors.append("CONTRACT_JURISDICTION_INVALID")

    collections = {}
    for name in ("organizations", "roles", "posts", "people", "memberships", "evidence", "assertions"):
        rows = contract.get(name)
        if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
            errors.append(f"CONTRACT_{name.upper()}_INVALID")
            collections[name] = []
        else:
            collections[name] = rows

    def unique_ids(name: str) -> dict[str, Mapping[str, Any]]:
        index: dict[str, Mapping[str, Any]] = {}
        for row in collections[name]:
            value = row.get("id")
            if not isinstance(value, str) or not value:
                errors.append(f"CONTRACT_{name.upper()}_ID_INVALID")
                continue
            if value in index:
                errors.append(f"CONTRACT_{name.upper()}_ID_DUPLICATE")
            index[value] = row
        return index

    organizations = unique_ids("organizations")
    posts = unique_ids("posts")
    people = unique_ids("people")
    evidence = unique_ids("evidence")

    shared_org_ids: set[str] = set()
    for row in organizations.values():
        value = row.get("shared_identity_id")
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or re.fullmatch(
                r"org-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
                r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
                value,
            )
            is None
        ):
            errors.append("CONTRACT_ORGANIZATION_SHARED_IDENTITY_INVALID")
        elif value in shared_org_ids:
            errors.append("CONTRACT_ORGANIZATION_SHARED_IDENTITY_DUPLICATE")
        else:
            shared_org_ids.add(value)

    shared_person_ids: set[str] = set()
    for row in people.values():
        value = row.get("shared_identity_id")
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or re.fullmatch(
                r"per-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
                r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
                value,
            )
            is None
        ):
            errors.append("CONTRACT_PERSON_SHARED_IDENTITY_INVALID")
        elif value in shared_person_ids:
            errors.append("CONTRACT_PERSON_SHARED_IDENTITY_DUPLICATE")
        else:
            shared_person_ids.add(value)
    roles: dict[str, Mapping[str, Any]] = {}
    for row in collections["roles"]:
        role_id = row.get("id")
        if not isinstance(role_id, str) or not role_id:
            errors.append("CONTRACT_ROLES_ID_INVALID")
            continue
        if role_id in roles:
            errors.append("CONTRACT_ROLES_ID_DUPLICATE")
        roles[role_id] = row

    membership_periods: set[tuple[str, str]] = set()
    open_post_counts: Counter[str] = Counter()
    open_person_org: set[tuple[str, str]] = set()
    membership_ids: set[str] = set()
    for row in collections["memberships"]:
        membership_id = row.get("id")
        opened_at = row.get("opened_at")
        if not isinstance(membership_id, str) or not membership_id or not isinstance(opened_at, str):
            errors.append("CONTRACT_MEMBERSHIP_ID_INVALID")
            continue
        period_key = (membership_id, opened_at)
        if period_key in membership_periods:
            errors.append("CONTRACT_MEMBERSHIP_PERIOD_DUPLICATE")
        membership_periods.add(period_key)
        membership_ids.add(membership_id)

        post_id = str(row.get("post_id") or "")
        person_id = str(row.get("person_id") or "")
        organization_id = str(row.get("organization_id") or "")
        post = posts.get(post_id)
        if post is None:
            errors.append("CONTRACT_MEMBERSHIP_POST_FK")
        if person_id not in people:
            errors.append("CONTRACT_MEMBERSHIP_PERSON_FK")
        if organization_id not in organizations:
            errors.append("CONTRACT_MEMBERSHIP_ORGANIZATION_FK")
        if post is not None and str(post.get("organization_id") or "") != organization_id:
            errors.append("CONTRACT_MEMBERSHIP_POST_ORGANIZATION_MISMATCH")
        sources = row.get("sources")
        if (
            not isinstance(sources, list)
            or not sources
            or any(not isinstance(source, Mapping) or not source.get("url") for source in sources)
        ):
            errors.append("CONTRACT_MEMBERSHIP_SOURCE_MISSING")
        if row.get("closed_at") is None:
            open_post_counts[post_id] += 1
            pair = (person_id, organization_id)
            if pair in open_person_org:
                errors.append("CONTRACT_PERSON_MULTIPLE_OPEN_POSTS_IN_BODY")
            open_person_org.add(pair)

    jurisdiction_ocdid = (
        str(jurisdiction.get("jurisdiction_ocdid")) if isinstance(jurisdiction, Mapping) else ""
    )
    for post_id, post in posts.items():
        if str(post.get("jurisdiction_ocdid") or "") != jurisdiction_ocdid:
            errors.append("CONTRACT_POST_JURISDICTION_MISMATCH")
        if str(post.get("organization_id") or "") not in organizations:
            errors.append("CONTRACT_POST_ORGANIZATION_FK")
        if str(post.get("role_id") or "") not in roles:
            errors.append("CONTRACT_POST_ROLE_FK")
        division = str(post.get("division_ocdid") or "")
        if not division.startswith("ocd-division/"):
            errors.append("CONTRACT_POST_DIVISION_INVALID")
        try:
            headcount = int(post.get("meta_headcount"))
            if headcount < 1:
                errors.append("CONTRACT_POST_HEADCOUNT_INVALID")
            if open_post_counts[post_id] > headcount:
                errors.append("CONTRACT_POST_OVER_CAPACITY")
        except (TypeError, ValueError):
            errors.append("CONTRACT_POST_HEADCOUNT_INVALID")

    allowed_subjects = {
        "jurisdiction": {jurisdiction_ocdid},
        "organization": set(organizations),
        "role": set(roles),
        "post": set(posts),
        "person": set(people),
        "membership": membership_ids,
    }
    assertion_ids: set[str] = set()
    for assertion in collections["assertions"]:
        assertion_id = assertion.get("id")
        if not isinstance(assertion_id, str) or not assertion_id:
            errors.append("CONTRACT_ASSERTION_ID_INVALID")
            continue
        if assertion_id in assertion_ids:
            errors.append("CONTRACT_ASSERTION_ID_DUPLICATE")
        assertion_ids.add(assertion_id)
        subject_type = assertion.get("subject_type")
        if (
            subject_type not in allowed_subjects
            or assertion.get("subject_id") not in allowed_subjects[subject_type]
        ):
            errors.append("CONTRACT_ASSERTION_SUBJECT_FK")
        evidence_ids = assertion.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or any(value not in evidence for value in evidence_ids)
        ):
            errors.append("CONTRACT_ASSERTION_EVIDENCE_FK")


    election_keys = ("elections", "contests", "candidacies", "election_certification")
    election_presence = [key in contract for key in election_keys]
    if any(election_presence) and not all(election_presence):
        errors.append("CONTRACT_ELECTION_EXTENSION_PARTIAL")
    if require_elections and not all(election_presence):
        errors.append("CONTRACT_ELECTION_EXTENSION_REQUIRED")

    if all(election_presence):
        election_rows = contract.get("elections")
        contest_rows = contract.get("contests")
        candidacy_rows = contract.get("candidacies")
        if not isinstance(election_rows, list):
            errors.append("CONTRACT_ELECTIONS_INVALID")
            election_rows = []
        if not isinstance(contest_rows, list):
            errors.append("CONTRACT_CONTESTS_INVALID")
            contest_rows = []
        if not isinstance(candidacy_rows, list):
            errors.append("CONTRACT_CANDIDACIES_INVALID")
            candidacy_rows = []

        def indexed(rows: list[Any], code: str) -> dict[str, Mapping[str, Any]]:
            index: dict[str, Mapping[str, Any]] = {}
            for row in rows:
                if not isinstance(row, Mapping):
                    errors.append(code + "_RECORD_INVALID")
                    continue
                row_id = row.get("id")
                if not isinstance(row_id, str) or not row_id:
                    errors.append(code + "_ID_INVALID")
                    continue
                if row_id in index:
                    errors.append(code + "_ID_DUPLICATE")
                index[row_id] = row
            return index

        election_index = indexed(election_rows, "CONTRACT_ELECTION")
        contest_index = indexed(contest_rows, "CONTRACT_CONTEST")
        candidacy_index = indexed(candidacy_rows, "CONTRACT_CANDIDACY")

        def evidence_links_ok(row: Mapping[str, Any], code: str) -> None:
            refs = row.get("evidence_ids")
            if (
                not isinstance(refs, list)
                or not refs
                or any(ref not in evidence for ref in refs)
            ):
                errors.append(code + "_EVIDENCE_FK")

        for row in election_index.values():
            if row.get("jurisdiction_ocdid") != jurisdiction_ocdid:
                errors.append("CONTRACT_ELECTION_JURISDICTION_MISMATCH")
            election_date = row.get("election_date")
            if not isinstance(election_date, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", election_date) is None:
                errors.append("CONTRACT_ELECTION_DATE_INVALID")
            evidence_links_ok(row, "CONTRACT_ELECTION")

        for row in contest_index.values():
            if row.get("election_id") not in election_index:
                errors.append("CONTRACT_CONTEST_ELECTION_FK")
            if row.get("post_id") not in posts:
                errors.append("CONTRACT_CONTEST_POST_FK")
            if not isinstance(row.get("name"), str) or not str(row.get("name")).strip():
                errors.append("CONTRACT_CONTEST_NAME_INVALID")
            evidence_links_ok(row, "CONTRACT_CONTEST")

        for row in candidacy_index.values():
            if row.get("contest_id") not in contest_index:
                errors.append("CONTRACT_CANDIDACY_CONTEST_FK")
            kind = row.get("candidate_kind")
            if kind == "person":
                if row.get("person_id") not in people:
                    errors.append("CONTRACT_CANDIDACY_PERSON_FK")
            elif kind == "write_in_bucket":
                if row.get("person_id") is not None:
                    errors.append("CONTRACT_WRITE_IN_PERSON_FORBIDDEN")
            else:
                errors.append("CONTRACT_CANDIDACY_KIND_INVALID")
            if not isinstance(row.get("source_candidate_id"), str) or not row.get("source_candidate_id"):
                errors.append("CONTRACT_CANDIDACY_SOURCE_ID_INVALID")
            if not isinstance(row.get("candidate_name"), str) or not row.get("candidate_name"):
                errors.append("CONTRACT_CANDIDACY_NAME_INVALID")
            votes = row.get("votes")
            if votes is not None and (not isinstance(votes, int) or votes < 0):
                errors.append("CONTRACT_CANDIDACY_VOTES_INVALID")
            share = row.get("vote_share")
            if share is not None and (
                not isinstance(share, (int, float))
                or isinstance(share, bool)
                or share < 0
                or share > 1
            ):
                errors.append("CONTRACT_CANDIDACY_VOTE_SHARE_INVALID")
            evidence_links_ok(row, "CONTRACT_CANDIDACY")

        election_certification = contract.get("election_certification")
        if not isinstance(election_certification, Mapping):
            errors.append("CONTRACT_ELECTION_CERTIFICATION_INVALID")
        elif require_elections:
            if election_certification.get("status") != "certified":
                errors.append("CONTRACT_ELECTIONS_NOT_CERTIFIED")
            if election_certification.get("scope_complete") is not True:
                errors.append("CONTRACT_ELECTION_SCOPE_INCOMPLETE")
            if election_certification.get("qa_passed") is not True:
                errors.append("CONTRACT_ELECTION_QA_NOT_PASSED")
            if election_certification.get("unexplained_loss") != 0:
                errors.append("CONTRACT_ELECTION_UNEXPLAINED_LOSS")

    certification = contract.get("certification")
    if not isinstance(certification, Mapping):
        errors.append("CONTRACT_CERTIFICATION_INVALID")
    elif require_certified:
        if certification.get("status") != "certified":
            errors.append("CONTRACT_NOT_CERTIFIED")
        for field in ("raw_complete", "normalized_complete", "qa_passed", "parity_ok"):
            if certification.get(field) is not True:
                errors.append("CONTRACT_CERTIFICATION_GATES_NOT_MET")
                break

    return sorted(set(errors))


def _resolve_division(
    contract: Mapping[str, Any],
    normalized: Mapping[str, Any],
    binding: Mapping[str, Any],
    address: str,
) -> tuple[str | None, dict[str, Any] | None, set[str]]:
    posts = [row for row in contract.get("posts", []) if isinstance(row, Mapping)]
    known_divisions = {str(row.get("division_ocdid")) for row in posts if row.get("division_ocdid")}
    base_division = _base_division_ocdid(
        str((contract.get("jurisdiction") or {}).get("jurisdiction_ocdid") or "")
    )

    adapter_id = binding.get("district_adapter_id")
    if adapter_id:
        district_key = normalized.get("district_assignments", {}).get(str(adapter_id))
        if district_key is None:
            return None, _fail(address, "CIVIC_GPS_REQUIRED_DISTRICT_MISSING", str(adapter_id)), set()
        mapping = binding.get("district_division_map")
        template = binding.get("division_template")
        if mapping is not None:
            if not isinstance(mapping, Mapping) or template:
                return None, _fail(address, "CONTRACT_DISTRICT_BINDING_INVALID", str(adapter_id)), set()
            division = mapping.get(str(district_key))
        else:
            if not isinstance(template, str) or "{district_key}" not in template:
                return None, _fail(address, "CONTRACT_DISTRICT_BINDING_INVALID", str(adapter_id)), set()
            division = template.format(district_key=district_key)
        if not isinstance(division, str) or not division.startswith("ocd-division/"):
            return None, _fail(address, "CONTRACT_DISTRICT_DIVISION_INVALID", str(adapter_id)), set()
        if division not in known_divisions:
            return None, _fail(address, "CIVIC_GPS_DISTRICT_NOT_IN_CONTRACT", division), set()
        applicable = {division}
        if base_division in known_divisions:
            applicable.add(str(base_division))
        return division, None, applicable

    explicit = binding.get("division_ocdid")
    if explicit is not None:
        if not isinstance(explicit, str) or explicit not in known_divisions:
            return None, _fail(address, "CONTRACT_DIVISION_BINDING_INVALID", str(explicit)), set()
        return explicit, None, {explicit}

    if base_division and base_division in known_divisions:
        return base_division, None, {base_division}
    if len(known_divisions) == 1:
        only = next(iter(known_divisions))
        return only, None, {only}
    return None, _fail(address, "CONTRACT_REPRESENTATION_DIVISION_AMBIGUOUS"), set()


def build_representation_from_civic_gps_result(
    contract: dict[str, Any],
    address: str,
    civic_gps_result: Any,
    *,
    binding: dict[str, Any],
) -> dict[str, Any]:
    """Join Civic GPS geography to a certified Contract v1 representation graph."""
    errors = validate_contract(contract, require_certified=True)
    if errors:
        primary = "CONTRACT_NOT_CERTIFIED" if "CONTRACT_NOT_CERTIFIED" in errors else "CONTRACT_INVALID"
        return _fail(address, primary, ",".join(errors))

    jurisdiction = contract["jurisdiction"]
    if binding.get("contract_jurisdiction_ocdid") not in (
        None,
        jurisdiction["jurisdiction_ocdid"],
    ):
        return _fail(address, "CONTRACT_JURISDICTION_BINDING_MISMATCH")

    normalized = live_civic_gps.normalize_civic_gps_result(address, civic_gps_result)
    if normalized.get("status") != "PASS":
        return _fail(
            address,
            str(normalized.get("error") or "CIVIC_GPS_GEOGRAPHY_INVALID"),
            normalized.get("detail"),
        )

    civic_jurisdiction_id = str(binding.get("civic_gps_jurisdiction_id") or "")
    if not civic_jurisdiction_id or civic_jurisdiction_id not in normalized["jurisdiction_ids"]:
        return _fail(address, "CIVIC_GPS_JURISDICTION_NOT_ACTIVE", civic_jurisdiction_id or None)

    resolved_division, failure, applicable_divisions = _resolve_division(
        contract, normalized, binding, address
    )
    if failure is not None:
        return failure
    assert resolved_division is not None

    organizations = {
        str(row["id"]): row
        for row in contract["organizations"]
        if isinstance(row, Mapping) and row.get("id")
    }
    roles = {
        str(row["id"]): row
        for row in contract["roles"]
        if isinstance(row, Mapping) and row.get("id")
    }
    people = {
        str(row["id"]): row
        for row in contract["people"]
        if isinstance(row, Mapping) and row.get("id")
    }
    memberships_by_post: dict[str, list[Mapping[str, Any]]] = {}
    for membership in contract["memberships"]:
        if membership.get("closed_at") is None:
            memberships_by_post.setdefault(str(membership["post_id"]), []).append(membership)

    offices: list[dict[str, Any]] = []
    current_holder_count = 0
    for post in contract["posts"]:
        if post.get("division_ocdid") not in applicable_divisions:
            continue
        post_id = str(post["id"])
        role = roles.get(str(post["role_id"]), {})
        holders: list[dict[str, Any]] = []
        for membership in memberships_by_post.get(post_id, []):
            person = people.get(str(membership["person_id"]))
            if person is None:
                return _fail(address, "CONTRACT_MEMBERSHIP_PERSON_FK", str(membership["id"]))
            factory_person_id = _identifier(person, "civicdata_factory_person")
            factory_term_id = _identifier(membership, "civicdata_factory_role_term")
            label = membership.get("label")
            holder = {
                "membership_id": str(membership["id"]),
                "role_term_id": factory_term_id,
                "contract_person_id": str(person["id"]),
                "shared_person_id": person.get("shared_identity_id"),
                "person_id": factory_person_id or str(person["id"]),
                "name": person.get("name"),
                "status": "CURRENT",
                "term_start": membership.get("start_date"),
                "term_end": membership.get("end_date"),
                "leadership_roles": [str(label)] if label else [],
                "designations": copy.deepcopy(membership.get("designations") or []),
                "sources": copy.deepcopy(membership.get("sources") or []),
            }
            holders.append(holder)
        holders.sort(key=lambda row: (str(row.get("name") or ""), str(row.get("person_id") or "")))
        headcount = int(post["meta_headcount"])
        if len(holders) > headcount:
            return _fail(address, "CONTRACT_REPRESENTATION_EXCEEDS_SEAT_CAPACITY", post_id)
        current_holder_count += len(holders)
        factory_office_id = _identifier(post, "civicdata_factory_office")
        organization = organizations.get(str(post.get("organization_id")), {})
        offices.append(
            {
                "post_id": post_id,
                "organization_id": post.get("organization_id"),
                "shared_organization_id": organization.get("shared_identity_id"),
                "office_id": factory_office_id or post_id,
                "office_name": post.get("label") or role.get("label") or post.get("role_id"),
                "role_id": post.get("role_id"),
                "division_ocdid": post.get("division_ocdid"),
                "seat_capacity": headcount,
                "vacancy_count": headcount - len(holders),
                "selection_method": post.get("selection_method"),
                "holders": holders,
                "identifiers": copy.deepcopy(post.get("identifiers") or []),
            }
        )
    offices.sort(key=lambda row: (str(row.get("office_name") or ""), str(row.get("post_id") or "")))
    if not offices:
        return _fail(address, "CONTRACT_REPRESENTATION_EMPTY")

    model: dict[str, Any] = {
        "status": "PASS",
        "consumer_gate": CONSUMER_GATE,
        "representation_contract_version": contract["schema_version"],
        "representation_only": True,
        "full_essentials_supported": False,
        "input_address": address,
        "matched_address": normalized.get("matched_address"),
        "address_resolution_source": "CIVIC_GPS_LIVE",
        "resolved_jurisdictions": normalized["jurisdiction_ids"],
        "district_assignments": normalized["district_assignments"],
        "resolved_division_ocdid": resolved_division,
        "jurisdiction": copy.deepcopy(jurisdiction),
        "applicable_offices": offices,
        "current_holder_count": current_holder_count,
        "source_evidence": copy.deepcopy(contract.get("evidence") or []),
        "source_assertions": copy.deepcopy(contract.get("assertions") or []),
        "certification": copy.deepcopy(contract["certification"]),
        "canonical_writes": 0,
    }
    model["deterministic_sha256"] = package_source.sha256_bytes(
        package_source.canonical_json_bytes(model)
    )
    return model
