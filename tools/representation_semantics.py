#!/usr/bin/env python3
"""Deterministic helpers for role/post/membership interoperability semantics.

This module intentionally does not infer legal office structure from raw title
strings. Callers must classify an observation using governed evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TITLE_CLASSES = {"FORMAL_ROLE", "INTERNAL_TITLE", "RAW_ONLY"}


class RepresentationSemanticsError(ValueError):
    """Fail-closed representation semantics violation."""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _same_label(left: str, right: str) -> bool:
    return _clean(left).casefold() == _clean(right).casefold()


def vacancy_count(seats: int, active_memberships: int) -> int:
    """Return open capacity without creating a fake vacancy Person."""
    if isinstance(seats, bool) or not isinstance(seats, int) or seats < 0:
        raise RepresentationSemanticsError("POST_SEATS_INVALID")
    if (
        isinstance(active_memberships, bool)
        or not isinstance(active_memberships, int)
        or active_memberships < 0
        or active_memberships > seats
    ):
        raise RepresentationSemanticsError("ACTIVE_MEMBERSHIP_COUNT_INVALID")
    return seats - active_memberships


def normalize_observation(
    *,
    formal_role_id: str,
    formal_role_label: str,
    base_division_ocdid: str,
    source_title: str | None,
    classification: str,
    seats: int = 1,
    active_memberships: int = 0,
    seat_designation: str | None = None,
    seat_is_geographic: bool = False,
    geographic_division_ocdid: str | None = None,
    formal_role_override_reviewed: bool = False,
) -> dict[str, Any]:
    """Project a governed title observation into Role/Post/Membership semantics.

    Raw source text is preserved. It cannot silently change the canonical role.
    """
    role_id = _clean(formal_role_id)
    role_label = _clean(formal_role_label)
    base_division = _clean(base_division_ocdid)
    source = _clean(source_title)
    classification = _clean(classification).upper()
    designation = _clean(seat_designation)
    geographic_division = _clean(geographic_division_ocdid)

    if not role_id or not role_label:
        raise RepresentationSemanticsError("FORMAL_ROLE_REQUIRED")
    if not base_division.startswith("ocd-division/"):
        raise RepresentationSemanticsError("BASE_DIVISION_OCDID_INVALID")
    if classification not in TITLE_CLASSES:
        raise RepresentationSemanticsError("TITLE_CLASSIFICATION_INVALID")

    post_division = base_division
    membership_designations: list[str] = []

    if seat_is_geographic:
        if not geographic_division.startswith("ocd-division/"):
            raise RepresentationSemanticsError("GEOGRAPHIC_SEAT_DIVISION_REQUIRED")
        post_division = geographic_division
    elif designation:
        membership_designations.append(designation)

    membership_label = None
    normalized_role_label = role_label

    if classification == "INTERNAL_TITLE":
        if not source:
            raise RepresentationSemanticsError("INTERNAL_TITLE_REQUIRED")
        membership_label = source
    elif classification == "FORMAL_ROLE":
        if not source:
            raise RepresentationSemanticsError("FORMAL_ROLE_SOURCE_TITLE_REQUIRED")
        if not _same_label(source, role_label):
            if not formal_role_override_reviewed:
                raise RepresentationSemanticsError("FORMAL_ROLE_OVERRIDE_REVIEW_REQUIRED")
            normalized_role_label = source
    # RAW_ONLY deliberately has no canonical effect.

    result = {
        "role": {
            "role_id": role_id,
            "label": normalized_role_label,
        },
        "post": {
            "role_id": role_id,
            "division_ocdid": post_division,
            "seats": seats,
        },
        "membership": {
            "label": membership_label,
            "designations": membership_designations,
        },
        "observation": {
            "source_title": source or None,
            "classification": classification,
            "canonical_write": classification == "FORMAL_ROLE",
        },
        "vacancy_count": vacancy_count(seats, active_memberships),
    }
    return result


def validate_no_fake_vacancy_person(person: dict[str, Any]) -> None:
    """Reject synthetic vacancy placeholders at the Person layer."""
    name = _clean(
        person.get("canonical_name")
        or person.get("name")
        or person.get("display_name")
    ).casefold()
    person_id = _clean(person.get("person_id") or person.get("id")).casefold()
    forbidden = {"vacant", "vacancy", "open seat", "unfilled"}
    if name in forbidden or person_id in forbidden:
        raise RepresentationSemanticsError("FAKE_VACANCY_PERSON_FORBIDDEN")
