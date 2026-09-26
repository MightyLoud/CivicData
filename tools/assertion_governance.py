#!/usr/bin/env python3
"""Append-only partner assertion review, promotion, and certification helpers."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

DEFAULT_AUTHORITY_MATRIX = {
    "jurisdiction": "openstates_jurisdictions",
    "division": "openstates_jurisdictions",
    "organization": "civicdata_representation",
    "post": "civicdata_representation",
    "person": "civicdata_representation",
    "membership": "civicdata_representation",
    "certification": "civicdata_certification",
}

REVIEW_OUTCOMES = {
    "accepted",
    "rejected",
    "needs_evidence",
    "identity_conflict",
    "scope_conflict",
}

PROMOTABLE_SUBJECTS = {
    "jurisdiction": ("jurisdiction", "jurisdiction_id"),
    "division": ("divisions", "division_id"),
    "organization": ("organizations", "organization_id"),
    "post": ("posts", "post_id"),
    "person": ("people", "person_id"),
    "membership": ("memberships", "membership_id"),
}

PROTECTED_IDENTITY_FIELDS = {
    "jurisdiction_id",
    "division_id",
    "organization_id",
    "post_id",
    "person_id",
    "membership_id",
    "role_id",
    "jurisdiction_ocdid",
    "division_ocdid",
    "canonical_id",
}


class AssertionGovernanceError(ValueError):
    """Fail-closed assertion-governance violation."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _valid_timestamp(value: Any) -> bool:
    text = _clean(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def expected_authority(
    subject_type: str,
    authority_matrix: Mapping[str, str] | None = None,
) -> str:
    matrix = DEFAULT_AUTHORITY_MATRIX if authority_matrix is None else authority_matrix
    subject = _clean(subject_type).lower()
    authority = matrix.get(subject)
    if not isinstance(authority, str) or not authority:
        raise AssertionGovernanceError("SUBJECT_AUTHORITY_UNDEFINED")
    return authority


def validate_assertion(
    assertion: Mapping[str, Any],
    authority_matrix: Mapping[str, str] | None = None,
) -> list[str]:
    errors: set[str] = set()
    if not isinstance(assertion, Mapping):
        return ["ASSERTION_INVALID"]

    required = {
        "assertion_id",
        "source_system",
        "subject_type",
        "subject_id",
        "field_path",
        "value",
        "evidence",
        "asserted_at",
        "base_snapshot_id",
        "review_status",
        "review_history",
    }
    if set(assertion) != required:
        if required - set(assertion):
            errors.add("ASSERTION_REQUIRED_FIELDS")
        if set(assertion) - required:
            errors.add("ASSERTION_EXTRA_FIELDS")

    if not _clean(assertion.get("assertion_id")):
        errors.add("ASSERTION_ID_REQUIRED")
    if not _clean(assertion.get("source_system")):
        errors.add("SOURCE_SYSTEM_REQUIRED")
    subject_type = _clean(assertion.get("subject_type")).lower()
    if subject_type not in DEFAULT_AUTHORITY_MATRIX:
        errors.add("SUBJECT_TYPE_INVALID")
    if not _clean(assertion.get("subject_id")):
        errors.add("SUBJECT_ID_REQUIRED")
    if not _clean(assertion.get("field_path")):
        errors.add("FIELD_PATH_REQUIRED")
    if not _clean(assertion.get("base_snapshot_id")):
        errors.add("BASE_SNAPSHOT_REQUIRED")
    if not _valid_timestamp(assertion.get("asserted_at")):
        errors.add("ASSERTED_AT_INVALID")

    evidence = assertion.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.add("EVIDENCE_REQUIRED")
    else:
        seen: set[str] = set()
        for row in evidence:
            if not isinstance(row, Mapping) or set(row) != {
                "evidence_id",
                "locator",
                "captured_at",
            }:
                errors.add("EVIDENCE_INVALID")
                continue
            evidence_id = _clean(row.get("evidence_id"))
            if not evidence_id or evidence_id in seen:
                errors.add("EVIDENCE_ID_INVALID")
            seen.add(evidence_id)
            if not _clean(row.get("locator")) or not _valid_timestamp(row.get("captured_at")):
                errors.add("EVIDENCE_INVALID")

    status = assertion.get("review_status")
    if status not in {"proposed"} | REVIEW_OUTCOMES:
        errors.add("REVIEW_STATUS_INVALID")

    matrix = DEFAULT_AUTHORITY_MATRIX if authority_matrix is None else authority_matrix
    history = assertion.get("review_history")
    if not isinstance(history, list):
        errors.add("REVIEW_HISTORY_INVALID")
    else:
        for row in history:
            if not isinstance(row, Mapping) or set(row) != {
                "outcome",
                "reviewer",
                "authority",
                "reviewed_at",
                "reason",
            }:
                errors.add("REVIEW_HISTORY_INVALID")
                continue
            if row.get("outcome") not in REVIEW_OUTCOMES:
                errors.add("REVIEW_OUTCOME_INVALID")
            if not _clean(row.get("reviewer")) or not _clean(row.get("authority")):
                errors.add("REVIEWER_INVALID")
            expected = matrix.get(subject_type)
            if expected and _clean(row.get("authority")) != expected:
                errors.add("REVIEW_AUTHORITY_HISTORY_MISMATCH")
            if not _valid_timestamp(row.get("reviewed_at")) or not _clean(row.get("reason")):
                errors.add("REVIEW_HISTORY_INVALID")

        if status == "proposed" and history:
            errors.add("PROPOSED_ASSERTION_HAS_REVIEW")
        if status != "proposed":
            if not history or history[-1].get("outcome") != status:
                errors.add("REVIEW_STATUS_HISTORY_MISMATCH")

    return sorted(errors)


def review_assertion(
    assertion: Mapping[str, Any],
    *,
    outcome: str,
    reviewer: str,
    reviewer_authority: str,
    reviewed_at: str,
    reason: str,
    authority_matrix: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    errors = validate_assertion(assertion, authority_matrix=authority_matrix)
    if errors:
        raise AssertionGovernanceError("ASSERTION_INVALID:" + ",".join(errors))
    if assertion["review_status"] != "proposed":
        raise AssertionGovernanceError("ASSERTION_ALREADY_REVIEWED")

    outcome = _clean(outcome).lower()
    if outcome not in REVIEW_OUTCOMES:
        raise AssertionGovernanceError("REVIEW_OUTCOME_INVALID")
    if not _clean(reviewer) or not _clean(reason) or not _valid_timestamp(reviewed_at):
        raise AssertionGovernanceError("REVIEW_METADATA_INVALID")

    required_authority = expected_authority(
        assertion["subject_type"],
        authority_matrix=authority_matrix,
    )
    if _clean(reviewer_authority) != required_authority:
        raise AssertionGovernanceError("REVIEW_AUTHORITY_MISMATCH")

    result = deepcopy(dict(assertion))
    result["review_status"] = outcome
    result["review_history"].append(
        {
            "outcome": outcome,
            "reviewer": _clean(reviewer),
            "authority": required_authority,
            "reviewed_at": _clean(reviewed_at),
            "reason": _clean(reason),
        }
    )
    errors = validate_assertion(result, authority_matrix=authority_matrix)
    if errors:
        raise AssertionGovernanceError("ASSERTION_INVALID:" + ",".join(errors))
    return result


def _subject_record(snapshot: dict[str, Any], subject_type: str, subject_id: str) -> dict[str, Any]:
    location = PROMOTABLE_SUBJECTS.get(subject_type)
    if location is None:
        raise AssertionGovernanceError("SUBJECT_NOT_PROMOTABLE")
    container_name, id_field = location
    container = snapshot.get(container_name)

    if subject_type == "jurisdiction":
        if not isinstance(container, dict):
            raise AssertionGovernanceError("SUBJECT_CONTAINER_INVALID")
        matches = [container] if container.get(id_field) == subject_id else []
    else:
        if not isinstance(container, list):
            raise AssertionGovernanceError("SUBJECT_CONTAINER_INVALID")
        matches = [
            row
            for row in container
            if isinstance(row, dict) and row.get(id_field) == subject_id
        ]

    if len(matches) != 1:
        raise AssertionGovernanceError(
            "SUBJECT_NOT_FOUND" if not matches else "SUBJECT_AMBIGUOUS"
        )
    return matches[0]


def _set_existing_path(record: dict[str, Any], field_path: str, value: Any) -> Any:
    parts = [_clean(part) for part in field_path.split(".")]
    if not parts or any(not part for part in parts):
        raise AssertionGovernanceError("FIELD_PATH_INVALID")
    if any(part in PROTECTED_IDENTITY_FIELDS for part in parts):
        raise AssertionGovernanceError("IDENTITY_FIELD_WRITE_FORBIDDEN")

    current: dict[str, Any] = record
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            raise AssertionGovernanceError("FIELD_PATH_NOT_FOUND")
        current = child
    leaf = parts[-1]
    if leaf not in current:
        raise AssertionGovernanceError("FIELD_PATH_NOT_FOUND")
    previous = deepcopy(current[leaf])
    current[leaf] = deepcopy(value)
    return previous


def validate_certification(certification: Mapping[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not isinstance(certification, Mapping):
        return ["CERTIFICATION_INVALID"]
    required = {
        "status",
        "raw_complete",
        "normalized_complete",
        "qa_passed",
        "parity_ok",
        "verified_at",
    }
    if set(certification) != required:
        errors.add("CERTIFICATION_FIELDS_INVALID")
        return sorted(errors)

    status = certification.get("status")
    if status not in {
        "uncertified",
        "evidence_review",
        "external_blocker",
        "rule_fix",
        "certified",
    }:
        errors.add("CERTIFICATION_STATUS_INVALID")

    gates = [
        certification.get("raw_complete"),
        certification.get("normalized_complete"),
        certification.get("qa_passed"),
        certification.get("parity_ok"),
    ]
    if any(not isinstance(value, bool) for value in gates):
        errors.add("CERTIFICATION_GATES_INVALID")
    if status == "certified":
        if gates != [True, True, True, True]:
            errors.add("CERTIFIED_GATES_INCOMPLETE")
        if not _valid_timestamp(certification.get("verified_at")):
            errors.add("CERTIFICATION_VERIFIED_AT_INVALID")
    elif certification.get("verified_at") not in (None, ""):
        if not _valid_timestamp(certification.get("verified_at")):
            errors.add("CERTIFICATION_VERIFIED_AT_INVALID")
    return sorted(errors)


def promote_accepted_assertion(
    snapshot: Mapping[str, Any],
    assertion: Mapping[str, Any],
    *,
    new_snapshot_id: str,
    promoted_at: str,
) -> dict[str, Any]:
    errors = validate_assertion(assertion)
    if errors:
        raise AssertionGovernanceError("ASSERTION_INVALID:" + ",".join(errors))
    if assertion["review_status"] != "accepted":
        raise AssertionGovernanceError("ASSERTION_NOT_ACCEPTED")
    if assertion["subject_type"] == "certification":
        raise AssertionGovernanceError("CERTIFICATION_DIRECT_PROMOTION_FORBIDDEN")
    if not isinstance(snapshot, Mapping):
        raise AssertionGovernanceError("SNAPSHOT_INVALID")
    if assertion["base_snapshot_id"] != snapshot.get("snapshot_id"):
        raise AssertionGovernanceError("BASE_SNAPSHOT_STALE")
    if not _clean(new_snapshot_id) or new_snapshot_id == snapshot.get("snapshot_id"):
        raise AssertionGovernanceError("NEW_SNAPSHOT_ID_INVALID")
    if not _valid_timestamp(promoted_at):
        raise AssertionGovernanceError("PROMOTED_AT_INVALID")

    result = deepcopy(dict(snapshot))
    record = _subject_record(
        result,
        assertion["subject_type"],
        assertion["subject_id"],
    )
    previous = _set_existing_path(
        record,
        assertion["field_path"],
        assertion["value"],
    )

    result["snapshot_id"] = _clean(new_snapshot_id)
    applied = result.setdefault("assertion_ids_applied", [])
    if not isinstance(applied, list):
        raise AssertionGovernanceError("ASSERTION_LEDGER_INVALID")
    if assertion["assertion_id"] in applied:
        raise AssertionGovernanceError("ASSERTION_ALREADY_APPLIED")
    applied.append(assertion["assertion_id"])

    history = result.setdefault("promotion_history", [])
    if not isinstance(history, list):
        raise AssertionGovernanceError("PROMOTION_HISTORY_INVALID")
    history.append(
        {
            "assertion_id": assertion["assertion_id"],
            "base_snapshot_id": assertion["base_snapshot_id"],
            "new_snapshot_id": result["snapshot_id"],
            "subject_type": assertion["subject_type"],
            "subject_id": assertion["subject_id"],
            "field_path": assertion["field_path"],
            "previous_value": previous,
            "new_value": deepcopy(assertion["value"]),
            "promoted_at": _clean(promoted_at),
            "review": deepcopy(assertion["review_history"][-1]),
        }
    )

    result["certification"] = {
        "status": "uncertified",
        "raw_complete": False,
        "normalized_complete": False,
        "qa_passed": False,
        "parity_ok": False,
        "verified_at": None,
    }
    return result


def certify_snapshot(
    snapshot: Mapping[str, Any],
    *,
    raw_complete: bool,
    normalized_complete: bool,
    qa_passed: bool,
    parity_ok: bool,
    verified_at: str,
    reviewer: str,
    reviewer_authority: str,
    reason: str,
    authority_matrix: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    required_authority = expected_authority(
        "certification",
        authority_matrix=authority_matrix,
    )
    if _clean(reviewer_authority) != required_authority:
        raise AssertionGovernanceError("CERTIFICATION_AUTHORITY_MISMATCH")
    if not _clean(reviewer) or not _clean(reason) or not _valid_timestamp(verified_at):
        raise AssertionGovernanceError("CERTIFICATION_REVIEW_METADATA_INVALID")

    gates = [raw_complete, normalized_complete, qa_passed, parity_ok]
    if any(not isinstance(value, bool) for value in gates):
        raise AssertionGovernanceError("CERTIFICATION_GATES_INVALID")
    if gates != [True, True, True, True]:
        raise AssertionGovernanceError("CERTIFICATION_GATES_INCOMPLETE")

    result = deepcopy(dict(snapshot))
    result["certification"] = {
        "status": "certified",
        "raw_complete": True,
        "normalized_complete": True,
        "qa_passed": True,
        "parity_ok": True,
        "verified_at": _clean(verified_at),
    }
    history = result.setdefault("certification_history", [])
    if not isinstance(history, list):
        raise AssertionGovernanceError("CERTIFICATION_HISTORY_INVALID")
    history.append(
        {
            "snapshot_id": result.get("snapshot_id"),
            "reviewer": _clean(reviewer),
            "authority": required_authority,
            "verified_at": _clean(verified_at),
            "reason": _clean(reason),
        }
    )
    errors = validate_certification(result["certification"])
    if errors:
        raise AssertionGovernanceError("CERTIFICATION_INVALID:" + ",".join(errors))
    return result
