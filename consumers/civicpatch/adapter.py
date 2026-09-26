#!/usr/bin/env python3
"""CivicPatch candidate adapter for Canonical Representation Core snapshots.

v0.1 is intentionally candidate-only. It emits CivicPatch OpenStatesPersonRecord-
shaped records plus a sidecar receipt. Preview IDs are deterministic UUIDv5
values derived from canonical Person IDs and are NOT accepted CivicPatch
identities until partner review creates an explicit crosswalk.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re
import uuid
from typing import Any, Mapping, Sequence

from tools.canonical_representation_core import validate_core

ADAPTER_VERSION = "factory-core-to-civicpatch/0.1"
CIVICPATCH_OPEN_DATA_COMMIT = "69331c2b0d97e13695dab07ec1d6a969c99a3e4d"
CIVICPATCH_TOOLS_COMMIT = "072a8baf648542f66557fb30547ee3ba3a11ba6c"
PREVIEW_ID_NAMESPACE = uuid.UUID("7b0a9be7-73fc-4f32-9e63-41ef90b93634")
DATE_RE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")


class CivicPatchAdapterError(ValueError):
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


def _valid_partial_date(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and bool(DATE_RE.fullmatch(value))


def preview_civicpatch_id(person_id: str) -> str:
    value = _clean(person_id)
    if not value:
        raise CivicPatchAdapterError("PERSON_ID_REQUIRED")
    return str(uuid.uuid5(PREVIEW_ID_NAMESPACE, f"civicdata:civicpatch-preview:{value}"))


def validate_civicpatch_officials(officials: Sequence[Mapping[str, Any]]) -> list[str]:
    """Validate the pinned CivicPatch OpenStatesPersonRecord publish shape."""
    errors: set[str] = set()
    if not isinstance(officials, list):
        return ["OFFICIALS_INVALID"]

    expected_person_fields = {
        "id",
        "name",
        "other_names",
        "phones",
        "emails",
        "urls",
        "image",
        "cdn_image",
        "jurisdiction_ocdid",
        "source_urls",
        "updated_at",
        "roles",
    }
    expected_role_fields = {
        "name",
        "role_id",
        "jurisdiction_ocdid",
        "division_ocdid",
        "start_date",
        "end_date",
    }

    ids: set[str] = set()
    for official in officials:
        if not isinstance(official, Mapping):
            errors.add("OFFICIAL_INVALID")
            continue
        if set(official) != expected_person_fields:
            errors.add("OFFICIAL_FIELDS_INVALID")
        official_id = official.get("id")
        if not isinstance(official_id, str) or not official_id:
            errors.add("OFFICIAL_ID_REQUIRED")
        elif official_id in ids:
            errors.add("OFFICIAL_ID_DUPLICATE")
        else:
            ids.add(official_id)
        if not _clean(official.get("name")):
            errors.add("OFFICIAL_NAME_REQUIRED")
        for field in ("other_names", "phones", "emails", "urls", "source_urls", "roles"):
            if not isinstance(official.get(field), list):
                errors.add(f"OFFICIAL_LIST_INVALID:{field}")
        if not _clean(official.get("jurisdiction_ocdid")).startswith("ocd-jurisdiction/"):
            errors.add("OFFICIAL_JURISDICTION_INVALID")
        updated_at = official.get("updated_at")
        if updated_at is not None and not _valid_timestamp(updated_at):
            errors.add("OFFICIAL_UPDATED_AT_INVALID")

        roles = official.get("roles")
        if not isinstance(roles, list) or not roles:
            errors.add("OFFICIAL_ROLE_REQUIRED")
            continue
        for role in roles:
            if not isinstance(role, Mapping) or set(role) != expected_role_fields:
                errors.add("ROLE_FIELDS_INVALID")
                continue
            if not _clean(role.get("name")) or not _clean(role.get("role_id")):
                errors.add("ROLE_IDENTITY_REQUIRED")
            if role.get("jurisdiction_ocdid") != official.get("jurisdiction_ocdid"):
                errors.add("ROLE_JURISDICTION_MISMATCH")
            if not _clean(role.get("division_ocdid")).startswith("ocd-division/"):
                errors.add("ROLE_DIVISION_INVALID")
            if not _valid_partial_date(role.get("start_date")):
                errors.add("ROLE_START_DATE_INVALID")
            if not _valid_partial_date(role.get("end_date")):
                errors.add("ROLE_END_DATE_INVALID")
    return sorted(errors)


def _source_urls(source_ids: Sequence[str], evidence: Mapping[str, Mapping[str, Any]]) -> list[str]:
    urls = {
        _clean(evidence[source_id].get("source_url"))
        for source_id in source_ids
        if source_id in evidence and _clean(evidence[source_id].get("source_url"))
    }
    return sorted(urls)


def core_semantic_projection(core: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Representation facts that v0.1 must preserve through the bundle round trip."""
    errors = validate_core(core)
    if errors:
        raise CivicPatchAdapterError("CORE_INVALID:" + ",".join(errors))

    people = {row["person_id"]: row for row in core["people"]}
    posts = {row["post_id"]: row for row in core["posts"]}
    roles = {row["role_id"]: row for row in core["roles"]}
    organizations = {row["organization_id"]: row for row in core["organizations"]}

    rows: list[dict[str, Any]] = []
    for membership in core["memberships"]:
        if membership["membership_status"] != "CURRENT":
            continue
        person = people[membership["person_id"]]
        post = posts[membership["post_id"]]
        role = roles[post["role_id"]]
        organization = organizations[post["organization_id"]]
        rows.append(
            {
                "person_id": person["person_id"],
                "name": person["name"],
                "membership_id": membership["membership_id"],
                "post_id": post["post_id"],
                "organization_id": organization["organization_id"],
                "role_id": role["role_id"],
                "role_label": role["label"],
                "jurisdiction_ocdid": organization["jurisdiction_ocdid"],
                "division_ocdid": post["division_ocdid"],
                "start_date": membership.get("start_date"),
                "end_date": membership.get("end_date"),
                "internal_label": membership.get("label"),
            }
        )
    return sorted(rows, key=lambda row: (row["person_id"], row["membership_id"]))


def export_core_to_civicpatch(
    core: Mapping[str, Any],
    *,
    generated_at: str,
    source_package_path: str,
) -> dict[str, Any]:
    errors = validate_core(core)
    if errors:
        raise CivicPatchAdapterError("CORE_INVALID:" + ",".join(errors))
    if not _valid_timestamp(generated_at):
        raise CivicPatchAdapterError("GENERATED_AT_INVALID")
    if not _clean(source_package_path):
        raise CivicPatchAdapterError("SOURCE_PACKAGE_PATH_REQUIRED")
    if core["certification"]["status"] != "certified":
        raise CivicPatchAdapterError("SOURCE_CORE_NOT_CERTIFIED")

    people = {row["person_id"]: row for row in core["people"]}
    posts = {row["post_id"]: row for row in core["posts"]}
    roles = {row["role_id"]: row for row in core["roles"]}
    organizations = {row["organization_id"]: row for row in core["organizations"]}
    evidence = {row["evidence_id"]: row for row in core["evidence"]}

    by_person: dict[str, list[Mapping[str, Any]]] = {}
    for membership in core["memberships"]:
        if membership["membership_status"] == "CURRENT":
            by_person.setdefault(membership["person_id"], []).append(membership)

    officials: list[dict[str, Any]] = []
    receipt_memberships: list[dict[str, Any]] = []
    preview_crosswalks: list[dict[str, Any]] = []

    for person_id in sorted(by_person):
        person = people[person_id]
        candidate_id = preview_civicpatch_id(person_id)
        memberships = sorted(by_person[person_id], key=lambda row: row["membership_id"])
        role_rows: list[dict[str, Any]] = []
        all_source_ids = set(person.get("source_ids", []))
        jurisdiction_ids: set[str] = set()

        for role_index, membership in enumerate(memberships):
            post = posts[membership["post_id"]]
            role = roles[post["role_id"]]
            organization = organizations[post["organization_id"]]
            jurisdiction_ids.add(organization["jurisdiction_ocdid"])
            all_source_ids.update(membership.get("source_ids", []))
            all_source_ids.update(post.get("source_ids", []))
            all_source_ids.update(role.get("source_ids", []))
            all_source_ids.update(organization.get("source_ids", []))

            start_date = membership.get("start_date")
            end_date = membership.get("end_date")
            if not _valid_partial_date(start_date) or not _valid_partial_date(end_date):
                raise CivicPatchAdapterError("MEMBERSHIP_DATE_NOT_CIVICPATCH_COMPATIBLE")

            # Critical #72 rule: published formal role comes from Role/Post, not
            # Membership.label (Chair, Mayor Pro Tem, etc.).
            role_rows.append(
                {
                    "name": role["label"],
                    "role_id": role["role_id"],
                    "jurisdiction_ocdid": organization["jurisdiction_ocdid"],
                    "division_ocdid": post["division_ocdid"],
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            receipt_memberships.append(
                {
                    "candidate_official_id": candidate_id,
                    "role_index": role_index,
                    "core_person_id": person_id,
                    "core_membership_id": membership["membership_id"],
                    "core_post_id": post["post_id"],
                    "core_organization_id": organization["organization_id"],
                    "internal_label": membership.get("label"),
                    "internal_label_exported_as_formal_role": False,
                }
            )

        if len(jurisdiction_ids) != 1:
            raise CivicPatchAdapterError("PERSON_MULTIPLE_JURISDICTIONS_UNSUPPORTED")
        jurisdiction_ocdid = next(iter(jurisdiction_ids))

        officials.append(
            {
                "id": candidate_id,
                "name": person["name"],
                "other_names": [],
                "phones": [],
                "emails": [],
                "urls": [],
                "image": None,
                "cdn_image": None,
                "jurisdiction_ocdid": jurisdiction_ocdid,
                "source_urls": _source_urls(sorted(all_source_ids), evidence),
                "updated_at": generated_at,
                "roles": role_rows,
            }
        )
        preview_crosswalks.append(
            {
                "core_person_id": person_id,
                "candidate_civicpatch_id": candidate_id,
                "status": "PREVIEW_ONLY_REQUIRES_PARTNER_IDENTITY_REVIEW",
            }
        )

    errors = validate_civicpatch_officials(officials)
    if errors:
        raise CivicPatchAdapterError("CIVICPATCH_OUTPUT_INVALID:" + ",".join(errors))

    return {
        "adapter_contract_version": "0.1",
        "adapter_version": ADAPTER_VERSION,
        "target_contract": {
            "open_data_repository": "CivicPatch/open-data",
            "open_data_commit": CIVICPATCH_OPEN_DATA_COMMIT,
            "tools_repository": "CivicPatch/civicpatch-tools",
            "tools_commit": CIVICPATCH_TOOLS_COMMIT,
            "publish_model": "shared.schemas.OpenStatesPersonRecord",
        },
        "source": {
            "core_snapshot_id": core["snapshot_id"],
            "source_package_path": source_package_path,
            "core_schema_version": core["schema_version"],
            "certification": deepcopy(core["certification"]),
        },
        "candidate_id_policy": {
            "strategy": "UUIDV5_FROM_CANONICAL_PERSON_ID",
            "namespace": str(PREVIEW_ID_NAMESPACE),
            "accepted_civicpatch_identity": False,
        },
        "officials": officials,
        "receipt": {
            "person_crosswalks": preview_crosswalks,
            "membership_crosswalks": receipt_memberships,
            "loss_profile": {
                "preserved_in_civicpatch_file": [
                    "person display name",
                    "formal role_id and role label",
                    "jurisdiction_ocdid",
                    "division_ocdid",
                    "membership start_date",
                    "membership end_date",
                    "source URLs",
                ],
                "preserved_only_in_receipt": [
                    "core person_id",
                    "membership_id",
                    "post_id",
                    "organization_id",
                    "internal membership label",
                    "source certification",
                ],
                "not_promoted_without_partner_review": [
                    "candidate CivicPatch person IDs",
                ],
            },
        },
    }


def round_trip_semantic_projection(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    officials = bundle.get("officials")
    if not isinstance(officials, list):
        raise CivicPatchAdapterError("BUNDLE_OFFICIALS_INVALID")
    errors = validate_civicpatch_officials(officials)
    if errors:
        raise CivicPatchAdapterError("CIVICPATCH_OUTPUT_INVALID:" + ",".join(errors))

    membership_receipts = bundle.get("receipt", {}).get("membership_crosswalks", [])
    by_role = {
        (row["candidate_official_id"], row["role_index"]): row
        for row in membership_receipts
    }
    rows: list[dict[str, Any]] = []
    for official in officials:
        for index, role in enumerate(official["roles"]):
            receipt = by_role.get((official["id"], index))
            if receipt is None:
                raise CivicPatchAdapterError("MEMBERSHIP_RECEIPT_MISSING")
            rows.append(
                {
                    "person_id": receipt["core_person_id"],
                    "name": official["name"],
                    "membership_id": receipt["core_membership_id"],
                    "post_id": receipt["core_post_id"],
                    "organization_id": receipt["core_organization_id"],
                    "role_id": role["role_id"],
                    "role_label": role["name"],
                    "jurisdiction_ocdid": role["jurisdiction_ocdid"],
                    "division_ocdid": role["division_ocdid"],
                    "start_date": role["start_date"],
                    "end_date": role["end_date"],
                    "internal_label": receipt.get("internal_label"),
                }
            )
    return sorted(rows, key=lambda row: (row["person_id"], row["membership_id"]))


def compare_current_civicpatch(
    current_officials: Sequence[Mapping[str, Any]],
    candidate_officials: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Diagnostic only: exact display-name comparison is NOT identity resolution."""
    current = {_clean(row.get("name")): row for row in current_officials}
    candidate = {_clean(row.get("name")): row for row in candidate_officials}
    current_names = set(current)
    candidate_names = set(candidate)
    shared = sorted(current_names & candidate_names)

    role_differences: list[dict[str, Any]] = []
    for name in shared:
        current_roles = sorted(
            _clean(role.get("role_id"))
            for role in current[name].get("roles", [])
            if _clean(role.get("role_id"))
        )
        candidate_roles = sorted(
            _clean(role.get("role_id"))
            for role in candidate[name].get("roles", [])
            if _clean(role.get("role_id"))
        )
        if current_roles != candidate_roles:
            role_differences.append(
                {
                    "name": name,
                    "current_role_ids": current_roles,
                    "candidate_role_ids": candidate_roles,
                }
            )

    return {
        "comparison_method": "EXACT_DISPLAY_NAME_DIAGNOSTIC_ONLY",
        "identity_resolution_performed": False,
        "current_count": len(current_officials),
        "candidate_count": len(candidate_officials),
        "shared_names": shared,
        "candidate_only_names": sorted(candidate_names - current_names),
        "current_only_names": sorted(current_names - candidate_names),
        "role_differences_on_shared_names": role_differences,
        "potential_identity_matches_requiring_review": shared,
    }


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise CivicPatchAdapterError("YAML_SCALAR_UNSUPPORTED")


def render_civicpatch_yaml(officials: Sequence[Mapping[str, Any]]) -> str:
    errors = validate_civicpatch_officials(officials)
    if errors:
        raise CivicPatchAdapterError("CIVICPATCH_OUTPUT_INVALID:" + ",".join(errors))

    lines: list[str] = []
    for official in officials:
        lines.append(f"- id: {_yaml_scalar(official['id'])}")
        lines.append(f"  name: {_yaml_scalar(official['name'])}")
        for field in ("other_names", "phones", "emails", "urls"):
            values = official[field]
            if not values:
                lines.append(f"  {field}: []")
            else:
                lines.append(f"  {field}:")
                for value in values:
                    lines.append(f"  - {_yaml_scalar(value)}")
        lines.append(f"  image: {_yaml_scalar(official['image'])}")
        lines.append(f"  cdn_image: {_yaml_scalar(official['cdn_image'])}")
        lines.append(f"  jurisdiction_ocdid: {_yaml_scalar(official['jurisdiction_ocdid'])}")
        lines.append("  source_urls:")
        for value in official["source_urls"]:
            lines.append(f"  - {_yaml_scalar(value)}")
        lines.append(f"  updated_at: {_yaml_scalar(official['updated_at'])}")
        lines.append("  roles:")
        for role in official["roles"]:
            lines.append(f"  - name: {_yaml_scalar(role['name'])}")
            lines.append(f"    role_id: {_yaml_scalar(role['role_id'])}")
            lines.append(f"    jurisdiction_ocdid: {_yaml_scalar(role['jurisdiction_ocdid'])}")
            lines.append(f"    division_ocdid: {_yaml_scalar(role['division_ocdid'])}")
            lines.append(f"    start_date: {_yaml_scalar(role['start_date'])}")
            lines.append(f"    end_date: {_yaml_scalar(role['end_date'])}")
    return "\n".join(lines) + "\n"
