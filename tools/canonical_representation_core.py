#!/usr/bin/env python3
"""Canonical Representation Core v0.1 validator and legacy package adapter."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any, Mapping

LEVELS = {"FEDERAL", "STATE", "COUNTY", "MUNICIPAL", "OTHER"}
DIVISION_TYPES = {
    "COUNTRY",
    "STATE",
    "COUNTY",
    "MUNICIPALITY",
    "CONGRESSIONAL_DISTRICT",
    "STATE_LEGISLATIVE_DISTRICT",
    "LOCAL_DISTRICT",
    "OTHER",
}
RECORD_STATUSES = {"ACTIVE", "INACTIVE", "UNKNOWN"}
ORGANIZATION_TYPES = {"EXECUTIVE", "LEGISLATURE", "COUNCIL", "BOARD", "COMMISSION", "OTHER"}
SELECTION_METHODS = {"ELECTED", "APPOINTED", "EX_OFFICIO", "OTHER", "UNKNOWN"}
MEMBERSHIP_STATUSES = {"CURRENT", "FORMER", "UNKNOWN"}
CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
SOURCE_CLASSES = {"OFFICIAL", "PARTNER", "INTERNAL", "OTHER"}
NORMALIZATION_STATUSES = {"RAW", "NORMALIZED"}
REVIEW_STATUSES = {
    "UNREVIEWED",
    "ACCEPTED",
    "REJECTED",
    "NEEDS_EVIDENCE",
    "IDENTITY_CONFLICT",
    "SCOPE_CONFLICT",
}
SNAPSHOT_REVIEW_STATUSES = {"DRAFT", "REVIEW", "READY", "BLOCKED"}
QA_RESULTS = {"PASS", "FAIL", "NOT_RUN"}
CERTIFICATION_STATUSES = {
    "uncertified",
    "evidence_review",
    "external_blocker",
    "rule_fix",
    "certified",
}

PRIMARY_KEYS = {
    "jurisdictions": "jurisdiction_ocdid",
    "divisions": "division_ocdid",
    "organizations": "organization_id",
    "roles": "role_id",
    "posts": "post_id",
    "people": "person_id",
    "memberships": "membership_id",
    "evidence": "evidence_id",
    "assertions": "assertion_id",
}

SUBJECT_INDEX = {
    "jurisdiction": ("jurisdictions", "jurisdiction_ocdid"),
    "division": ("divisions", "division_ocdid"),
    "organization": ("organizations", "organization_id"),
    "role": ("roles", "role_id"),
    "post": ("posts", "post_id"),
    "person": ("people", "person_id"),
    "membership": ("memberships", "membership_id"),
}


class CanonicalCoreError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _stable_slug(value: Any) -> str:
    text = _clean(value).lower().replace("_", "-")
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def _status(value: Any) -> str:
    text = _clean(value).upper()
    if text in {"ACTIVE", "CURRENT"}:
        return "ACTIVE"
    if text in {"INACTIVE", "FORMER", "RETIRED"}:
        return "INACTIVE"
    return "UNKNOWN"


def _membership_status(value: Any) -> str:
    text = _clean(value).upper()
    if text == "CURRENT":
        return "CURRENT"
    if text in {"FORMER", "ENDED", "INACTIVE"}:
        return "FORMER"
    return "UNKNOWN"


def _confidence(value: Any, default: str = "MEDIUM") -> str:
    text = _clean(value).upper()
    return text if text in CONFIDENCE else default


def _source_class(authority_level: Any) -> str:
    text = _clean(authority_level).upper()
    if "OFFICIAL" in text:
        return "OFFICIAL"
    if "INTERNAL" in text or "REFERENCE" in text:
        return "INTERNAL"
    if "PARTNER" in text:
        return "PARTNER"
    return "OTHER"


def _source_confidence(authority_level: Any) -> str:
    text = _clean(authority_level).upper()
    if text.startswith("PRIMARY"):
        return "HIGH"
    if text.startswith("SECONDARY") or "INTERNAL" in text:
        return "MEDIUM"
    return "LOW"


def _level(jurisdiction: Mapping[str, Any]) -> str:
    text = " ".join(
        _clean(jurisdiction.get(key))
        for key in ("jurisdiction_type", "municipal_type", "classification")
    ).lower()
    if "municip" in text or "town" in text or "city" in text or "village" in text:
        return "MUNICIPAL"
    if "county" in text:
        return "COUNTY"
    if "state" in text:
        return "STATE"
    if "federal" in text or "national" in text:
        return "FEDERAL"
    return "OTHER"


def _division_type(row: Mapping[str, Any]) -> str:
    text = " ".join(
        _clean(row.get(key))
        for key in ("division_type", "division_subtype", "name")
    ).lower()
    if "congress" in text:
        return "CONGRESSIONAL_DISTRICT"
    if "legislative" in text or "state_house" in text or "state_senate" in text:
        return "STATE_LEGISLATIVE_DISTRICT"
    if "municip" in text or "place" in text or "town" in text or "city" in text:
        return "MUNICIPALITY"
    if "county" in text:
        return "COUNTY"
    if text.strip() == "state":
        return "STATE"
    if "district" in text or "ward" in text:
        return "LOCAL_DISTRICT"
    return "OTHER"


def _org_type(row: Mapping[str, Any]) -> str:
    text = " ".join(_clean(row.get(k)) for k in ("body_type", "branch", "name")).upper()
    if "COMMISSION" in text:
        return "COMMISSION"
    if "COUNCIL" in text:
        return "COUNCIL"
    if "BOARD" in text or "TRUSTEE" in text:
        return "BOARD"
    if "LEGISLAT" in text or "HOUSE" in text or "SENATE" in text:
        return "LEGISLATURE"
    if "EXECUTIVE" in text or "MAYOR" in text:
        return "EXECUTIVE"
    return "OTHER"


def _selection_method(value: Any) -> str:
    text = _clean(value).upper().replace("-", "_")
    if text in SELECTION_METHODS:
        return text
    if text == "EXOFFICIO":
        return "EX_OFFICIO"
    return "UNKNOWN"


def _required_string(row: Mapping[str, Any], field: str, errors: set[str], code: str) -> None:
    if not isinstance(row.get(field), str) or not row.get(field).strip():
        errors.add(code)


def _ids(rows: Any, key: str, errors: set[str], collection: str) -> set[str]:
    result: set[str] = set()
    if not isinstance(rows, list):
        errors.add(f"COLLECTION_INVALID:{collection}")
        return result
    for row in rows:
        if not isinstance(row, Mapping):
            errors.add(f"ROW_INVALID:{collection}")
            continue
        value = row.get(key)
        if not isinstance(value, str) or not value:
            errors.add(f"PRIMARY_KEY_REQUIRED:{collection}")
            continue
        if value in result:
            errors.add(f"DUPLICATE_PRIMARY_KEY:{collection}:{value}")
        result.add(value)
    return result


def validate_core(snapshot: Mapping[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not isinstance(snapshot, Mapping):
        return ["SNAPSHOT_INVALID"]

    required_root = {
        "schema_version",
        "snapshot_id",
        "jurisdictions",
        "divisions",
        "organizations",
        "roles",
        "posts",
        "people",
        "memberships",
        "evidence",
        "assertions",
        "review",
        "certification",
    }
    missing = required_root - set(snapshot)
    if missing:
        errors.add("ROOT_REQUIRED_FIELDS")
    if snapshot.get("schema_version") != "0.1":
        errors.add("SCHEMA_VERSION_INVALID")
    if not _clean(snapshot.get("snapshot_id")):
        errors.add("SNAPSHOT_ID_REQUIRED")

    id_sets: dict[str, set[str]] = {}
    for collection, key in PRIMARY_KEYS.items():
        id_sets[collection] = _ids(snapshot.get(collection), key, errors, collection)

    evidence_ids = id_sets["evidence"]

    for row in snapshot.get("evidence", []) if isinstance(snapshot.get("evidence"), list) else []:
        if not isinstance(row, Mapping):
            continue
        for field in ("source_url", "source_type", "retrieved_at"):
            _required_string(row, field, errors, f"EVIDENCE_REQUIRED:{field}")
        if row.get("source_class") not in SOURCE_CLASSES:
            errors.add("SOURCE_CLASS_INVALID")
        if row.get("confidence") not in CONFIDENCE:
            errors.add("CONFIDENCE_INVALID:evidence")

    def check_sources(rows: Any, collection: str) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            sources = row.get("source_ids")
            if not isinstance(sources, list):
                errors.add(f"SOURCE_IDS_INVALID:{collection}")
                continue
            if any(source not in evidence_ids for source in sources):
                errors.add(f"SOURCE_REFERENCE_INVALID:{collection}")

    for collection in ("jurisdictions","divisions","organizations","roles","posts","people","memberships"):
        check_sources(snapshot.get(collection), collection)

    jurisdictions = snapshot.get("jurisdictions", [])
    if isinstance(jurisdictions, list):
        for row in jurisdictions:
            if not isinstance(row, Mapping):
                continue
            if row.get("level") not in LEVELS:
                errors.add("JURISDICTION_LEVEL_INVALID")
            if row.get("record_status") not in RECORD_STATUSES:
                errors.add("RECORD_STATUS_INVALID:jurisdiction")
            if row.get("division_ocdid") not in id_sets["divisions"]:
                errors.add("JURISDICTION_DIVISION_FK")
            parent = row.get("parent_jurisdiction_ocdid")
            if parent not in (None, "") and parent not in id_sets["jurisdictions"]:
                errors.add("PARENT_JURISDICTION_FK")

    divisions = snapshot.get("divisions", [])
    if isinstance(divisions, list):
        for row in divisions:
            if not isinstance(row, Mapping):
                continue
            if row.get("division_type") not in DIVISION_TYPES:
                errors.add("DIVISION_TYPE_INVALID")
            if row.get("record_status") not in RECORD_STATUSES:
                errors.add("RECORD_STATUS_INVALID:division")
            parent = row.get("parent_division_ocdid")
            if parent not in (None, "") and parent not in id_sets["divisions"]:
                errors.add("PARENT_DIVISION_FK")

    organizations = snapshot.get("organizations", [])
    if isinstance(organizations, list):
        for row in organizations:
            if not isinstance(row, Mapping):
                continue
            if row.get("jurisdiction_ocdid") not in id_sets["jurisdictions"]:
                errors.add("ORGANIZATION_JURISDICTION_FK")
            if row.get("organization_type") not in ORGANIZATION_TYPES:
                errors.add("ORGANIZATION_TYPE_INVALID")
            if row.get("record_status") not in RECORD_STATUSES:
                errors.add("RECORD_STATUS_INVALID:organization")
            parent = row.get("parent_organization_id")
            if parent not in (None, "") and parent not in id_sets["organizations"]:
                errors.add("PARENT_ORGANIZATION_FK")

    roles = snapshot.get("roles", [])
    if isinstance(roles, list):
        for row in roles:
            if not isinstance(row, Mapping):
                continue
            _required_string(row, "label", errors, "ROLE_LABEL_REQUIRED")
            if row.get("record_status") not in RECORD_STATUSES:
                errors.add("RECORD_STATUS_INVALID:role")

    posts = snapshot.get("posts", [])
    if isinstance(posts, list):
        for row in posts:
            if not isinstance(row, Mapping):
                continue
            if row.get("organization_id") not in id_sets["organizations"]:
                errors.add("POST_ORGANIZATION_FK")
            if row.get("role_id") not in id_sets["roles"]:
                errors.add("POST_ROLE_FK")
            if row.get("division_ocdid") not in id_sets["divisions"]:
                errors.add("POST_DIVISION_FK")
            seats = row.get("seats")
            if isinstance(seats, bool) or not isinstance(seats, int) or seats < 1:
                errors.add("POST_SEATS_INVALID")
            if row.get("selection_method") not in SELECTION_METHODS:
                errors.add("SELECTION_METHOD_INVALID")
            if row.get("record_status") not in RECORD_STATUSES:
                errors.add("RECORD_STATUS_INVALID:post")

    people = snapshot.get("people", [])
    if isinstance(people, list):
        for row in people:
            if not isinstance(row, Mapping):
                continue
            _required_string(row, "name", errors, "PERSON_NAME_REQUIRED")
            if row.get("record_status") not in RECORD_STATUSES:
                errors.add("RECORD_STATUS_INVALID:person")

    memberships = snapshot.get("memberships", [])
    if isinstance(memberships, list):
        for row in memberships:
            if not isinstance(row, Mapping):
                continue
            if row.get("person_id") not in id_sets["people"]:
                errors.add("MEMBERSHIP_PERSON_FK")
            if row.get("post_id") not in id_sets["posts"]:
                errors.add("MEMBERSHIP_POST_FK")
            if row.get("membership_status") not in MEMBERSHIP_STATUSES:
                errors.add("MEMBERSHIP_STATUS_INVALID")
            if row.get("confidence") not in CONFIDENCE:
                errors.add("CONFIDENCE_INVALID:membership")

    subject_ids = {
        subject_type: id_sets[collection]
        for subject_type, (collection, _) in SUBJECT_INDEX.items()
    }
    assertions = snapshot.get("assertions", [])
    if isinstance(assertions, list):
        for row in assertions:
            if not isinstance(row, Mapping):
                continue
            subject_type = row.get("subject_type")
            if subject_type not in set(SUBJECT_INDEX) | {"other"}:
                errors.add("ASSERTION_SUBJECT_TYPE_INVALID")
            elif subject_type != "other" and row.get("subject_id") not in subject_ids[subject_type]:
                errors.add("ASSERTION_SUBJECT_FK")
            evidence_refs = row.get("evidence_ids")
            if not isinstance(evidence_refs, list) or not evidence_refs:
                errors.add("ASSERTION_EVIDENCE_REQUIRED")
            elif any(ref not in evidence_ids for ref in evidence_refs):
                errors.add("ASSERTION_EVIDENCE_FK")
            if row.get("normalization_status") not in NORMALIZATION_STATUSES:
                errors.add("ASSERTION_NORMALIZATION_STATUS_INVALID")
            if row.get("review_status") not in REVIEW_STATUSES:
                errors.add("ASSERTION_REVIEW_STATUS_INVALID")
            if row.get("confidence") not in CONFIDENCE:
                errors.add("CONFIDENCE_INVALID:assertion")

    review = snapshot.get("review")
    if not isinstance(review, Mapping):
        errors.add("REVIEW_INVALID")
    else:
        if review.get("status") not in SNAPSHOT_REVIEW_STATUSES:
            errors.add("SNAPSHOT_REVIEW_STATUS_INVALID")
        if review.get("qa_result") not in QA_RESULTS:
            errors.add("QA_RESULT_INVALID")
        if not isinstance(review.get("parity_ok"), bool):
            errors.add("REVIEW_PARITY_INVALID")
        for field in ("reviewer", "reviewed_at"):
            if not _clean(review.get(field)):
                errors.add(f"REVIEW_REQUIRED:{field}")

    certification = snapshot.get("certification")
    if not isinstance(certification, Mapping):
        errors.add("CERTIFICATION_INVALID")
    else:
        if certification.get("status") not in CERTIFICATION_STATUSES:
            errors.add("CERTIFICATION_STATUS_INVALID")
        gates = [
            certification.get("raw_complete"),
            certification.get("normalized_complete"),
            certification.get("qa_passed"),
            certification.get("parity_ok"),
        ]
        if any(not isinstance(value, bool) for value in gates):
            errors.add("CERTIFICATION_GATES_INVALID")
        if certification.get("status") == "certified":
            if gates != [True, True, True, True]:
                errors.add("CERTIFIED_GATES_INCOMPLETE")
            if review and isinstance(review, Mapping):
                if review.get("qa_result") != "PASS" or review.get("parity_ok") is not True:
                    errors.add("CERTIFIED_REVIEW_GATES_INCOMPLETE")
            if not _clean(certification.get("reviewer")) or not _clean(certification.get("verified_at")):
                errors.add("CERTIFICATION_REVIEW_REQUIRED")

    return sorted(errors)


def _map_assertion_subject(
    row: Mapping[str, Any],
    *,
    leadership_to_membership: Mapping[str, str],
    jurisdiction_native_id: str,
    jurisdiction_ocdid: str,
    division_ocdid_by_native: Mapping[str, str],
) -> tuple[str, str]:
    subject_type = _clean(row.get("subject_type")).lower()
    subject_id = _clean(row.get("subject_id"))
    mapping = {
        "jurisdiction": "jurisdiction",
        "division": "division",
        "body": "organization",
        "organization": "organization",
        "office": "post",
        "post": "post",
        "person": "person",
        "roleterm": "membership",
        "membership": "membership",
        "role": "role",
    }
    if subject_type == "leadershiprole":
        membership_id = leadership_to_membership.get(subject_id)
        return ("membership", membership_id) if membership_id else ("other", subject_id)
    canonical_type = mapping.get(subject_type, "other")
    if canonical_type == "jurisdiction" and subject_id == jurisdiction_native_id:
        return "jurisdiction", jurisdiction_ocdid
    if canonical_type == "division":
        return "division", division_ocdid_by_native.get(subject_id, subject_id)
    return canonical_type, subject_id


def from_jurisdiction_package(pkg: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a v0.1/v0.2 Jurisdiction Package into the core shape.

    Existing native IDs are preserved. This adapter does not mint shared
    cross-system identity IDs.
    """
    if not isinstance(pkg, Mapping):
        raise CanonicalCoreError("PACKAGE_INVALID")
    jurisdiction = pkg.get("jurisdiction")
    records = pkg.get("records")
    provenance = pkg.get("provenance")
    qa = pkg.get("qa")
    if not all(isinstance(x, Mapping) for x in (jurisdiction, records, provenance, qa)):
        raise CanonicalCoreError("PACKAGE_SHAPE_INVALID")

    divisions_raw = records.get("divisions", [])
    bodies_raw = records.get("bodies", [])
    offices_raw = records.get("offices", [])
    people_raw = records.get("people", [])
    terms_raw = records.get("role_terms", [])
    leadership_raw = records.get("leadership_roles", [])
    evidence_raw = provenance.get("source_evidence", [])
    assertions_raw = provenance.get("source_assertions", [])

    division_ocdid_by_native: dict[str, str] = {}
    divisions: list[dict[str, Any]] = []
    for row in divisions_raw:
        if not isinstance(row, Mapping):
            continue
        native_id = _clean(row.get("division_id") or row.get("id"))
        ocdid = _clean(row.get("ocd_division_id") or row.get("division_ocdid"))
        if not native_id or not ocdid:
            continue
        division_ocdid_by_native[native_id] = ocdid
        parent_native = _clean(row.get("parent_division_id"))
        divisions.append(
            {
                "division_ocdid": ocdid,
                "name": _clean(row.get("name")) or ocdid,
                "division_type": _division_type(row),
                "record_status": _status(row.get("status")),
                "parent_division_ocdid": division_ocdid_by_native.get(parent_native) if parent_native else None,
                "source_ids": _split_ids(row.get("source_ids")),
            }
        )

    jurisdiction_ocdid = _clean(
        jurisdiction.get("ocd_jurisdiction_id")
        or jurisdiction.get("jurisdiction_ocdid")
    )
    if not jurisdiction_ocdid:
        raise CanonicalCoreError("PACKAGE_JURISDICTION_OCDID_REQUIRED")

    jurisdiction_division = None
    for row in divisions:
        if row["division_type"] in {"MUNICIPALITY", "COUNTY", "STATE", "COUNTRY"}:
            jurisdiction_division = row["division_ocdid"]
            break
    if jurisdiction_division is None and divisions:
        jurisdiction_division = divisions[0]["division_ocdid"]
    if jurisdiction_division is None:
        raise CanonicalCoreError("PACKAGE_BASE_DIVISION_REQUIRED")

    jurisdictions = [
        {
            "jurisdiction_ocdid": jurisdiction_ocdid,
            "division_ocdid": jurisdiction_division,
            "name": _clean(jurisdiction.get("name")) or jurisdiction_ocdid,
            "level": _level(jurisdiction),
            "record_status": _status(jurisdiction.get("status")),
            "parent_jurisdiction_ocdid": None,
            "source_ids": _split_ids(jurisdiction.get("source_ids")),
        }
    ]

    organizations: list[dict[str, Any]] = []
    for row in bodies_raw:
        if not isinstance(row, Mapping):
            continue
        organization_id = _clean(row.get("body_id") or row.get("id"))
        if not organization_id:
            continue
        organizations.append(
            {
                "organization_id": organization_id,
                "jurisdiction_ocdid": jurisdiction_ocdid,
                "name": _clean(row.get("name")) or organization_id,
                "organization_type": _org_type(row),
                "record_status": _status(row.get("status")),
                "parent_organization_id": _clean(row.get("parent_body_id")) or None,
                "source_ids": _split_ids(row.get("source_ids")),
            }
        )

    roles_by_id: dict[str, dict[str, Any]] = {}
    posts: list[dict[str, Any]] = []
    for row in offices_raw:
        if not isinstance(row, Mapping):
            continue
        post_id = _clean(row.get("office_id") or row.get("id"))
        organization_id = _clean(row.get("body_id"))
        represented_native = _clean(row.get("represented_division_id"))
        role_id = _stable_slug(row.get("office_type") or row.get("office_name"))
        if not post_id or not organization_id or represented_native not in division_ocdid_by_native:
            continue
        sources = _split_ids(row.get("source_ids"))
        roles_by_id.setdefault(
            role_id,
            {
                "role_id": role_id,
                "label": _clean(row.get("office_name")) or role_id,
                "record_status": _status(row.get("status")),
                "aliases": [],
                "source_ids": sources,
            },
        )
        posts.append(
            {
                "post_id": post_id,
                "organization_id": organization_id,
                "role_id": role_id,
                "division_ocdid": division_ocdid_by_native[represented_native],
                "seats": int(row.get("seats") or 1),
                "selection_method": _selection_method(row.get("selection_method")),
                "record_status": _status(row.get("status")),
                "source_ids": sources,
            }
        )

    people: list[dict[str, Any]] = []
    for row in people_raw:
        if not isinstance(row, Mapping):
            continue
        person_id = _clean(row.get("person_id") or row.get("id"))
        if not person_id:
            continue
        people.append(
            {
                "person_id": person_id,
                "name": _clean(row.get("canonical_name") or row.get("name")) or person_id,
                "record_status": _status(row.get("status")),
                "source_ids": _split_ids(row.get("source_ids")),
            }
        )

    memberships: list[dict[str, Any]] = []
    membership_by_person_post: dict[tuple[str, str], str] = {}
    for row in terms_raw:
        if not isinstance(row, Mapping):
            continue
        membership_id = _clean(row.get("role_term_id") or row.get("term_id") or row.get("id"))
        person_id = _clean(row.get("person_id"))
        post_id = _clean(row.get("office_id"))
        if not membership_id or not person_id or not post_id:
            continue
        membership_by_person_post[(person_id, post_id)] = membership_id
        memberships.append(
            {
                "membership_id": membership_id,
                "person_id": person_id,
                "post_id": post_id,
                "membership_status": _membership_status(row.get("status") or row.get("role_term_status")),
                "start_date": row.get("valid_from") or row.get("term_start_date") or None,
                "end_date": row.get("valid_to") or row.get("term_end_date") or None,
                "label": None,
                "designations": [],
                "source_ids": _split_ids(row.get("source_ids")),
                "confidence": _confidence(row.get("confidence"), "MEDIUM"),
            }
        )

    leadership_to_membership: dict[str, str] = {}
    for row in leadership_raw:
        if not isinstance(row, Mapping):
            continue
        leadership_id = _clean(row.get("leadership_id") or row.get("leadership_role_id"))
        key = (_clean(row.get("person_id")), _clean(row.get("office_id")))
        membership_id = membership_by_person_post.get(key)
        if leadership_id and membership_id:
            leadership_to_membership[leadership_id] = membership_id
            for membership in memberships:
                if membership["membership_id"] == membership_id:
                    membership["label"] = _clean(row.get("role_title")) or membership["label"]
                    break

    evidence: list[dict[str, Any]] = []
    for row in evidence_raw:
        if not isinstance(row, Mapping):
            continue
        evidence_id = _clean(row.get("source_id") or row.get("evidence_id"))
        url = _clean(row.get("url") or row.get("source_url"))
        if not evidence_id or not url:
            continue
        evidence.append(
            {
                "evidence_id": evidence_id,
                "source_url": url,
                "source_class": _source_class(row.get("authority_level")),
                "source_type": _clean(row.get("source_type")) or "UNKNOWN",
                "retrieved_at": _clean(row.get("accessed_at") or row.get("retrieved_at")) or "UNKNOWN",
                "confidence": _source_confidence(row.get("authority_level")),
            }
        )

    assertions: list[dict[str, Any]] = []
    for row in assertions_raw:
        if not isinstance(row, Mapping):
            continue
        assertion_id = _clean(row.get("assertion_id"))
        evidence_ids = _split_ids(row.get("source_id") or row.get("source_ids"))
        if not assertion_id or not evidence_ids:
            continue
        subject_type, subject_id = _map_assertion_subject(
            row,
            leadership_to_membership=leadership_to_membership,
            jurisdiction_native_id=_clean(jurisdiction.get("jurisdiction_id")),
            jurisdiction_ocdid=jurisdiction_ocdid,
            division_ocdid_by_native=division_ocdid_by_native,
        )
        normalized = _clean(row.get("normalized_status")).upper() == "NORMALIZED"
        assertions.append(
            {
                "assertion_id": assertion_id,
                "subject_type": subject_type,
                "subject_id": subject_id or assertion_id,
                "field_path": _clean(row.get("predicate")) or "value",
                "value": deepcopy(row.get("object_value")),
                "evidence_ids": evidence_ids,
                "normalization_status": "NORMALIZED" if normalized else "RAW",
                "review_status": "ACCEPTED" if normalized else "UNREVIEWED",
                "confidence": _confidence(row.get("confidence"), "MEDIUM"),
            }
        )

    qa_passed = qa.get("qa_fail_count") == 0 and qa.get("blocking_gap_count") == 0
    parity_ok = qa.get("parity_ok") is True
    raw_complete = bool(evidence)
    normalized_complete = bool(assertions) and all(
        row["normalization_status"] == "NORMALIZED" for row in assertions
    )
    certified = raw_complete and normalized_complete and qa_passed and parity_ok
    reviewed_at = _clean(jurisdiction.get("row_updated_at")) or "UNKNOWN"

    core = {
        "schema_version": "0.1",
        "snapshot_id": f"factory:{_clean(jurisdiction.get('jurisdiction_id'))}:{reviewed_at}",
        "jurisdictions": jurisdictions,
        "divisions": divisions,
        "organizations": organizations,
        "roles": sorted(roles_by_id.values(), key=lambda row: row["role_id"]),
        "posts": posts,
        "people": people,
        "memberships": memberships,
        "evidence": evidence,
        "assertions": assertions,
        "review": {
            "status": "READY" if certified else "BLOCKED",
            "reviewer": "jurisdiction_factory",
            "reviewed_at": reviewed_at,
            "qa_result": "PASS" if qa_passed else "FAIL",
            "parity_ok": parity_ok,
        },
        "certification": {
            "status": "certified" if certified else "evidence_review",
            "raw_complete": raw_complete,
            "normalized_complete": normalized_complete,
            "qa_passed": qa_passed,
            "parity_ok": parity_ok,
            "reviewer": "jurisdiction_factory" if certified else None,
            "verified_at": reviewed_at if certified else None,
        },
        "extensions": {
            "jurisdiction_package": {
                "native_jurisdiction_id": _clean(jurisdiction.get("jurisdiction_id")),
                "tracker_synced": bool(
                    qa.get("tracker_complete")
                    or qa.get("tracker_synced")
                    or jurisdiction.get("tracker_complete")
                    or jurisdiction.get("tracker_synced")
                ),
            }
        },
    }
    return core
