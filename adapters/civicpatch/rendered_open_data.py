#!/usr/bin/env python3
"""Project CivicPatch rendered open-data rosters into Representation Contract v1.

This adapter exists only for migration/reconciliation against the public YAML
render. The current CivicPatch database snapshot is richer and should be used for
production exchange. Rendered output is always uncertified.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

SCHEMA_VERSION = "1.0.0-draft"
CONTRACT_NAMESPACE = uuid5(
    NAMESPACE_URL, "https://civicdata.tech/representation-contract/v1/civicpatch-rendered"
)


class RenderedExportError(ValueError):
    pass


def _uuid5(kind: str, value: str) -> str:
    return str(uuid5(CONTRACT_NAMESPACE, f"{kind}:{value}"))


def _clean_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise RenderedExportError("role id is empty")
    return slug


def _jurisdiction_name(ocdid: str) -> str:
    match = re.search(r"/(?:place|county|district):([^/]+)", ocdid)
    if not match:
        return ocdid
    return match.group(1).replace("_", " ").title()


def export_rendered_roster(
    source: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    if isinstance(source, Mapping):
        rows = source.get("records")
        source_url = source.get("source_url")
        source_revision = source.get("source_revision")
        explicit_name = source.get("jurisdiction_name")
    else:
        rows = source
        source_url = None
        source_revision = None
        explicit_name = None
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise RenderedExportError("rendered roster records are required")

    role_rows: dict[str, dict[str, Any]] = {}
    post_counts: dict[tuple[str, str], int] = {}
    role_instances: list[tuple[Mapping[str, Any], Mapping[str, Any], str, str]] = []
    jurisdiction_ocdids: set[str] = set()
    for person in rows:
        if not isinstance(person, Mapping):
            raise RenderedExportError("every rendered person must be an object")
        roles = person.get("roles")
        if not isinstance(roles, list) or not roles:
            raise RenderedExportError("rendered person must have at least one role")
        for role in roles:
            if not isinstance(role, Mapping):
                raise RenderedExportError("role must be an object")
            jurisdiction_ocdid = str(role.get("jurisdiction_ocdid") or "")
            division_ocdid = str(role.get("division_ocdid") or "")
            role_id = str(role.get("role_id") or _clean_slug(str(role.get("name") or "")))
            if not jurisdiction_ocdid.startswith("ocd-jurisdiction/"):
                raise RenderedExportError("rendered role jurisdiction_ocdid is required")
            if not division_ocdid.startswith("ocd-division/"):
                raise RenderedExportError("rendered role division_ocdid is required")
            jurisdiction_ocdids.add(jurisdiction_ocdid)
            role_rows.setdefault(
                role_id,
                {
                    "id": role_id,
                    "label": str(role.get("name") or role_id.replace("-", " ").title()),
                    "status": "active",
                    "is_unique": False,
                    "aliases": [],
                    "identifiers": [],
                },
            )
            key = (role_id, division_ocdid)
            post_counts[key] = post_counts.get(key, 0) + 1
            role_instances.append((person, role, role_id, division_ocdid))

    if len(jurisdiction_ocdids) != 1:
        raise RenderedExportError("rendered roster must contain exactly one jurisdiction")
    jurisdiction_ocdid = next(iter(jurisdiction_ocdids))
    organization_id = _uuid5("organization", jurisdiction_ocdid)

    posts: list[dict[str, Any]] = []
    post_ids: dict[tuple[str, str], str] = {}
    for key, count in sorted(post_counts.items()):
        role_id, division_ocdid = key
        post_id = _uuid5("post", f"{jurisdiction_ocdid}|{role_id}|{division_ocdid}")
        post_ids[key] = post_id
        role_rows[role_id]["is_unique"] = count == 1
        posts.append(
            {
                "id": post_id,
                "jurisdiction_ocdid": jurisdiction_ocdid,
                "organization_id": organization_id,
                "role_id": role_id,
                "label": role_rows[role_id]["label"],
                "division_ocdid": division_ocdid,
                "electorate_division_ocdid": None,
                "meta_headcount": count,
                "meta_is_tracked": True,
                "selection_method": "unknown",
                "identifiers": [],
            }
        )

    people: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    memberships: list[dict[str, Any]] = []
    for person, role, role_id, division_ocdid in role_instances:
        person_id = str(person.get("id") or "")
        try:
            UUID(person_id)
        except (ValueError, TypeError) as exc:
            raise RenderedExportError(f"rendered person id must be UUID: {person_id!r}") from exc
        name = str(person.get("name") or "").strip()
        if not name:
            raise RenderedExportError("rendered person name is required")
        urls = [str(v) for v in (person.get("urls") or []) if v]
        source_urls = [str(v) for v in (person.get("source_urls") or []) if v]
        people.setdefault(
            person_id,
            {
                "id": person_id,
                "name": name,
                "other_names": copy.deepcopy(person.get("other_names") or []),
                "phones": copy.deepcopy(person.get("phones") or []),
                "emails": copy.deepcopy(person.get("emails") or []),
                "urls": urls,
                "image": person.get("image") or None,
                "identifiers": [{"scheme": "civicpatch_person", "id": person_id, "url": None}],
            },
        )
        member_sources: list[dict[str, Any]] = []
        for url in source_urls:
            evidence_id = _uuid5("evidence", url)
            evidence.setdefault(
                evidence_id,
                {
                    "id": evidence_id,
                    "source_system": "civicpatch_rendered_open_data",
                    "source_type": "official_web",
                    "url": url,
                    "title": None,
                    "captured_at": str(person.get("updated_at") or generated_at),
                    "content_hash": None,
                    "raw_record": {
                        "person_id": person_id,
                        "person_name": name,
                        "role": copy.deepcopy(dict(role)),
                        "rendered_source_url": source_url,
                        "rendered_source_revision": source_revision,
                    },
                },
            )
            member_sources.append({"url": url, "note": str(role.get("name") or role_id)})
        if not member_sources:
            raise RenderedExportError(f"rendered person has no source URL: {name}")
        post_id = post_ids[(role_id, division_ocdid)]
        membership_id = _uuid5("membership", f"{person_id}|{post_id}")
        memberships.append(
            {
                "id": membership_id,
                "post_id": post_id,
                "organization_id": organization_id,
                "person_id": person_id,
                "designations": [],
                "label": None,
                "start_date": role.get("start_date") or None,
                "end_date": role.get("end_date") or None,
                "opened_at": str(person.get("updated_at") or generated_at),
                "closed_at": None,
                "sources": member_sources,
                "identifiers": [],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "jurisdiction": {
            "jurisdiction_ocdid": jurisdiction_ocdid,
            "name": str(explicit_name or _jurisdiction_name(jurisdiction_ocdid)),
            "classification": "government",
            "url": None,
            "identifiers": [],
        },
        "organizations": [
            {
                "id": organization_id,
                "jurisdiction_ocdid": jurisdiction_ocdid,
                "name": "Government",
                "classification": "government",
                "parent_organization_id": None,
                "url": None,
                "is_default": True,
                "identifiers": [],
            }
        ],
        "roles": sorted(role_rows.values(), key=lambda row: row["id"]),
        "posts": posts,
        "people": sorted(people.values(), key=lambda row: (row["name"].casefold(), row["id"])),
        "memberships": memberships,
        "evidence": sorted(evidence.values(), key=lambda row: row["id"]),
        "assertions": [],
        "certification": {
            "status": "uncertified",
            "raw_complete": bool(evidence),
            "normalized_complete": True,
            "qa_passed": False,
            "parity_ok": False,
            "verified_at": generated_at,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON form of a CivicPatch rendered roster")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    args = parser.parse_args(argv)
    source = json.loads(args.input.read_text(encoding="utf-8"))
    payload = export_rendered_roster(source, generated_at=args.generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
