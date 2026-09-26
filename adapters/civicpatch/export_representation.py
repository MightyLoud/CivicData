#!/usr/bin/env python3
"""Export a read-only CivicPatch snapshot to Representation Contract v1.

The adapter deliberately does not write to CivicPatch or CivicData canonical data.
It accepts rows shaped like CivicPatch's canonical tables and emits the shared
representation envelope. CivicPatch publication/review state is not treated as
Factory certification; callers must provide certification explicitly.
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from adapters.shared_identity import SharedIdentityResolutionError, SharedIdentityResolver

SCHEMA_VERSION = "1.0.0-draft"


class ExportError(ValueError):
    """Raised when CivicPatch data cannot be exported without guessing."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(row: Mapping[str, Any], key: str, *, context: str) -> str:
    value = row.get(key)
    if value is None or str(value).strip() == "":
        raise ExportError(f"{context}.{key} is required")
    return str(value)


def _uuid(value: Any, *, context: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ExportError(f"{context} must be a UUID: {value!r}") from exc
    return str(parsed)


def _none_if_blank(value: Any) -> Any:
    return None if value == "" else value


def _optional_list(row: Mapping[str, Any], key: str) -> list[Any]:
    value = row.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ExportError(f"{key} must be a list")
    return copy.deepcopy(value)


def _identifiers(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = row.get("identifiers")
    if values is None:
        return []
    if not isinstance(values, list):
        raise ExportError("identifiers must be a list")
    return copy.deepcopy(values)


def _jurisdiction(row: Mapping[str, Any]) -> dict[str, Any]:
    data = row.get("data") if isinstance(row.get("data"), Mapping) else {}
    ocdid = row.get("jurisdiction_ocdid") or row.get("ocdid")
    if not isinstance(ocdid, str) or not ocdid.startswith("ocd-jurisdiction/"):
        raise ExportError("jurisdiction.jurisdiction_ocdid must be an ocd-jurisdiction ID")
    name = row.get("name") or data.get("name") or data.get("display_name")
    if not name:
        raise ExportError("jurisdiction.name is required")
    out: dict[str, Any] = {
        "jurisdiction_ocdid": ocdid,
        "name": str(name),
        "classification": row.get("classification") or data.get("classification") or "government",
        "url": _none_if_blank(row.get("url") or data.get("url") or data.get("website")),
        "identifiers": _identifiers(row),
    }
    return out


def _organization(
    row: Mapping[str, Any],
    jurisdiction_ocdid: str,
    identity_resolver: SharedIdentityResolver,
) -> dict[str, Any]:
    row_jurisdiction = _required_text(row, "jurisdiction_ocdid", context="organization")
    if row_jurisdiction != jurisdiction_ocdid:
        raise ExportError(f"organization jurisdiction mismatch: {row_jurisdiction}")
    is_default = bool(row.get("meta_is_default", row.get("is_default", False)))
    classification = row.get("classification")
    if not classification:
        classification = "government" if is_default else "other"
    organization_id = _uuid(row.get("id"), context="organization.id")
    try:
        shared_identity_id = identity_resolver.resolve(
            entity_type="organization",
            system="civicpatch",
            external_id=organization_id,
        )
    except SharedIdentityResolutionError as exc:
        raise ExportError(str(exc)) from exc
    return {
        "id": organization_id,
        "shared_identity_id": shared_identity_id,
        "jurisdiction_ocdid": jurisdiction_ocdid,
        "name": _required_text(row, "name", context="organization"),
        "classification": classification,
        "parent_organization_id": (
            _uuid(row["parent_organization_id"], context="organization.parent_organization_id")
            if row.get("parent_organization_id")
            else None
        ),
        "url": _none_if_blank(row.get("url")),
        "is_default": is_default,
        "identifiers": _identifiers(row),
    }


def _role(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _required_text(row, "id", context="role"),
        "label": _required_text(row, "label", context="role"),
        "status": row.get("status") or "active",
        "is_unique": bool(row.get("is_unique", False)),
        "aliases": _optional_list(row, "aliases"),
        "identifiers": _identifiers(row),
    }


def _post(row: Mapping[str, Any], jurisdiction_ocdid: str) -> dict[str, Any]:
    row_jurisdiction = _required_text(row, "jurisdiction_ocdid", context="post")
    if row_jurisdiction != jurisdiction_ocdid:
        raise ExportError(f"post jurisdiction mismatch: {row_jurisdiction}")
    division = _required_text(row, "division_ocdid", context="post")
    if not division.startswith("ocd-division/"):
        raise ExportError(f"post.division_ocdid is not an OCD division: {division}")
    return {
        "id": _uuid(row.get("id"), context="post.id"),
        "jurisdiction_ocdid": jurisdiction_ocdid,
        "organization_id": _uuid(row.get("organization_id"), context="post.organization_id"),
        "role_id": _required_text(row, "role_id", context="post"),
        "label": _none_if_blank(row.get("label")),
        "division_ocdid": division,
        "electorate_division_ocdid": _none_if_blank(row.get("electorate_division_ocdid")),
        "meta_headcount": int(row.get("meta_headcount", 1)),
        "meta_is_tracked": bool(row.get("meta_is_tracked", True)),
        "selection_method": row.get("selection_method") or "unknown",
        "identifiers": _identifiers(row),
    }


def _person(
    row: Mapping[str, Any],
    jurisdiction_ocdid: str,
    identity_resolver: SharedIdentityResolver,
) -> dict[str, Any]:
    row_jurisdiction = row.get("jurisdiction_ocdid")
    if row_jurisdiction not in (None, "", jurisdiction_ocdid):
        raise ExportError(f"person jurisdiction mismatch: {row_jurisdiction}")
    data = row.get("data") if isinstance(row.get("data"), Mapping) else {}
    name = row.get("name") or data.get("name")
    if not name:
        raise ExportError("person.name is required")
    if str(name).strip().casefold() in {"vacant", "vacancy"}:
        raise ExportError("fake vacancy person is forbidden; represent vacancy by an unfilled post")
    person_id = _uuid(row.get("id"), context="person.id")
    try:
        shared_identity_id = identity_resolver.resolve(
            entity_type="person",
            system="civicpatch",
            external_id=person_id,
        )
    except SharedIdentityResolutionError as exc:
        raise ExportError(str(exc)) from exc
    return {
        "id": person_id,
        "shared_identity_id": shared_identity_id,
        "name": str(name),
        "other_names": copy.deepcopy(row.get("other_names") or data.get("other_names") or []),
        "phones": copy.deepcopy(row.get("phones") or data.get("phones") or []),
        "emails": copy.deepcopy(row.get("emails") or data.get("emails") or []),
        "urls": copy.deepcopy(row.get("urls") or data.get("urls") or []),
        "image": _none_if_blank(row.get("image") or data.get("image")),
        "identifiers": _identifiers(row),
    }


def _membership(row: Mapping[str, Any]) -> dict[str, Any]:
    sources = row.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ExportError("membership.sources must contain at least one source")
    clean_sources: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping) or not source.get("url"):
            raise ExportError(f"membership.sources[{index}].url is required")
        clean_sources.append({"url": str(source["url"]), "note": source.get("note")})
    return {
        "id": _uuid(row.get("id"), context="membership.id"),
        "post_id": _uuid(row.get("post_id"), context="membership.post_id"),
        "organization_id": _uuid(row.get("organization_id"), context="membership.organization_id"),
        "person_id": _uuid(row.get("person_id"), context="membership.person_id"),
        "designations": copy.deepcopy(row.get("designations") or []),
        "label": _none_if_blank(row.get("label")),
        "start_date": _none_if_blank(row.get("start_date")),
        "end_date": _none_if_blank(row.get("end_date")),
        "opened_at": _required_text(row, "opened_at", context="membership"),
        "closed_at": _none_if_blank(row.get("closed_at")),
        "sources": clean_sources,
        "identifiers": _identifiers(row),
    }


def _evidence(row: Mapping[str, Any], jurisdiction_ocdid: str) -> dict[str, Any]:
    row_jurisdiction = row.get("jurisdiction_ocdid")
    if row_jurisdiction not in (None, "", jurisdiction_ocdid):
        raise ExportError(f"source_record jurisdiction mismatch: {row_jurisdiction}")
    source_url = row.get("source_url") or row.get("url")
    if not source_url:
        raise ExportError("source_record.source_url is required")
    created_at = row.get("created_at") or row.get("captured_at")
    if not created_at:
        raise ExportError("source_record.created_at is required")
    return {
        "id": _uuid(row.get("id"), context="source_record.id"),
        "source_system": "civicpatch",
        "source_type": row.get("source_type") or "official_web",
        "url": str(source_url),
        "title": row.get("title") or row.get("label"),
        "captured_at": str(created_at),
        "content_hash": _none_if_blank(row.get("content_hash")),
        "raw_record": copy.deepcopy(dict(row)),
    }


def _certification(value: Any, *, generated_at: str) -> dict[str, Any]:
    if value is None:
        return {
            "status": "uncertified",
            "raw_complete": False,
            "normalized_complete": False,
            "qa_passed": False,
            "parity_ok": False,
            "verified_at": generated_at,
        }
    if not isinstance(value, Mapping):
        raise ExportError("certification must be an object")
    out = {
        "status": value.get("status", "uncertified"),
        "raw_complete": bool(value.get("raw_complete", False)),
        "normalized_complete": bool(value.get("normalized_complete", False)),
        "qa_passed": bool(value.get("qa_passed", False)),
        "parity_ok": bool(value.get("parity_ok", False)),
        "verified_at": value.get("verified_at") or generated_at,
    }
    if "factory_extension" in value:
        out["factory_extension"] = copy.deepcopy(value["factory_extension"])
    if out["status"] == "certified" and not all(
        out[key] for key in ("raw_complete", "normalized_complete", "qa_passed", "parity_ok")
    ):
        raise ExportError("certified requires raw + normalized + QA + parity")
    return out


def _validate_graph(payload: Mapping[str, Any]) -> None:
    jurisdiction_ocdid = payload["jurisdiction"]["jurisdiction_ocdid"]
    organizations = {row["id"]: row for row in payload["organizations"]}
    roles = {row["id"]: row for row in payload["roles"]}
    posts = {row["id"]: row for row in payload["posts"]}
    people = {row["id"]: row for row in payload["people"]}
    evidence = {row["id"]: row for row in payload["evidence"]}

    if len(organizations) != len(payload["organizations"]):
        raise ExportError("duplicate organization id")
    if len(roles) != len(payload["roles"]):
        raise ExportError("duplicate role id")
    if len(posts) != len(payload["posts"]):
        raise ExportError("duplicate post id")
    if len(people) != len(payload["people"]):
        raise ExportError("duplicate person id")
    if len(evidence) != len(payload["evidence"]):
        raise ExportError("duplicate evidence id")

    open_counts: dict[str, int] = {}
    open_person_org: set[tuple[str, str]] = set()
    for post in posts.values():
        if post["jurisdiction_ocdid"] != jurisdiction_ocdid:
            raise ExportError("post belongs to another jurisdiction")
        if post["organization_id"] not in organizations:
            raise ExportError(f"post references missing organization: {post['id']}")
        if post["role_id"] not in roles:
            raise ExportError(f"post references missing role: {post['id']}")
        if post["meta_headcount"] < 1:
            raise ExportError(f"post.meta_headcount must be positive: {post['id']}")

    seen_periods: set[tuple[str, str]] = set()
    for membership in payload["memberships"]:
        period_key = (membership["id"], membership["opened_at"])
        if period_key in seen_periods:
            raise ExportError(f"duplicate membership period: {period_key}")
        seen_periods.add(period_key)
        post = posts.get(membership["post_id"])
        if post is None:
            raise ExportError(f"membership references missing post: {membership['id']}")
        if membership["person_id"] not in people:
            raise ExportError(f"membership references missing person: {membership['id']}")
        if membership["organization_id"] != post["organization_id"]:
            raise ExportError(f"membership organization/post mismatch: {membership['id']}")
        if membership["closed_at"] is None:
            open_counts[membership["post_id"]] = open_counts.get(membership["post_id"], 0) + 1
            person_org = (membership["person_id"], membership["organization_id"])
            if person_org in open_person_org:
                raise ExportError("person has more than one open post in the same organization")
            open_person_org.add(person_org)

    for post_id, count in open_counts.items():
        if count > posts[post_id]["meta_headcount"]:
            raise ExportError(f"negative derived vacancy count for post: {post_id}")

    subject_sets = {
        "jurisdiction": {jurisdiction_ocdid},
        "organization": set(organizations),
        "role": set(roles),
        "post": set(posts),
        "person": set(people),
        "membership": {row["id"] for row in payload["memberships"]},
    }
    seen_assertions: set[str] = set()
    for assertion in payload["assertions"]:
        assertion_id = _uuid(assertion.get("id"), context="assertion.id")
        if assertion_id in seen_assertions:
            raise ExportError("duplicate assertion id")
        seen_assertions.add(assertion_id)
        subject_type = assertion.get("subject_type")
        if subject_type not in subject_sets or assertion.get("subject_id") not in subject_sets[subject_type]:
            raise ExportError(f"assertion references missing subject: {assertion_id}")
        for evidence_id in assertion.get("evidence_ids") or []:
            if evidence_id not in evidence:
                raise ExportError(f"assertion references missing evidence: {assertion_id}")


def export_civicpatch_snapshot(
    snapshot: Mapping[str, Any],
    *,
    generated_at: str | None = None,
    certification: Mapping[str, Any] | None = None,
    identity_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert CivicPatch canonical rows into Representation Contract v1.

    Expected keys are jurisdiction, organizations, roles, posts, people,
    memberships, and optionally source_records and contract_assertions.
    The source object is never mutated.
    """
    if not isinstance(snapshot, Mapping):
        raise ExportError("snapshot must be an object")
    generated_at = generated_at or _now_iso()
    try:
        identity_resolver = SharedIdentityResolver(identity_registry)
    except SharedIdentityResolutionError as exc:
        raise ExportError(str(exc)) from exc
    jurisdiction = _jurisdiction(snapshot.get("jurisdiction") or {})
    jurisdiction_ocdid = jurisdiction["jurisdiction_ocdid"]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "jurisdiction": jurisdiction,
        "organizations": [
            _organization(row, jurisdiction_ocdid, identity_resolver)
            for row in snapshot.get("organizations", [])
        ],
        "roles": [_role(row) for row in snapshot.get("roles", [])],
        "posts": [_post(row, jurisdiction_ocdid) for row in snapshot.get("posts", [])],
        "people": [
            _person(row, jurisdiction_ocdid, identity_resolver)
            for row in snapshot.get("people", [])
        ],
        "memberships": [_membership(row) for row in snapshot.get("memberships", [])],
        "evidence": [_evidence(row, jurisdiction_ocdid) for row in snapshot.get("source_records", [])],
        "assertions": copy.deepcopy(snapshot.get("contract_assertions") or []),
        "certification": _certification(certification, generated_at=generated_at),
    }
    _validate_graph(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CivicPatch snapshot JSON")
    parser.add_argument("--output", type=Path, required=True, help="Representation Contract JSON")
    parser.add_argument("--generated-at", help="Deterministic ISO-8601 generation timestamp")
    parser.add_argument(
        "--identity-registry",
        type=Path,
        help="Optional reviewed shared identity registry JSON",
    )
    args = parser.parse_args(argv)

    snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    identity_registry = (
        json.loads(args.identity_registry.read_text(encoding="utf-8"))
        if args.identity_registry
        else None
    )
    payload = export_civicpatch_snapshot(
        snapshot,
        generated_at=args.generated_at,
        identity_registry=identity_registry,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
