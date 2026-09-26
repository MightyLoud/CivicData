#!/usr/bin/env python3
"""Reconcile two Representation Contract v1 snapshots without writing either side."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

STATUSES = {
    "SAME",
    "FACTORY_ONLY",
    "CIVICPATCH_ONLY",
    "FIELD_CONFLICT",
    "IDENTITY_CONFLICT",
    "BLOCKED",
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _role_equiv(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    slug = slug.replace("pro-tempore", "pro-tem")
    slug = slug.replace("protempore", "pro-tem")
    return slug


def _identifier_set(row: Mapping[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for identifier in row.get("identifiers") or []:
        if isinstance(identifier, Mapping) and identifier.get("scheme") and identifier.get("id"):
            out.add((str(identifier["scheme"]), str(identifier["id"])))
    return out


def _identity_shared(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_shared = left.get("shared_identity_id")
    right_shared = right.get("shared_identity_id")
    if left_shared and right_shared:
        return str(left_shared) == str(right_shared)
    if left.get("id") and left.get("id") == right.get("id"):
        return True
    return bool(_identifier_set(left) & _identifier_set(right))


def _organizations(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["id"]): row
        for row in snapshot.get("organizations", [])
        if isinstance(row, Mapping) and row.get("id")
    }


def _people(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["id"]): row
        for row in snapshot.get("people", [])
        if isinstance(row, Mapping) and row.get("id")
    }


def _posts(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["id"]): row
        for row in snapshot.get("posts", [])
        if isinstance(row, Mapping) and row.get("id")
    }


def _post_semantic_key(snapshot: Mapping[str, Any], post: Mapping[str, Any]) -> tuple[str, str, str]:
    organizations = _organizations(snapshot)
    organization = organizations.get(str(post.get("organization_id")), {})
    shared_organization_id = organization.get("shared_identity_id")
    if shared_organization_id:
        org_key = "@shared:" + str(shared_organization_id)
    else:
        org_key = "@default" if organization.get("is_default") else _norm(organization.get("name"))
    return (_role_equiv(post.get("role_id")), str(post.get("division_ocdid") or ""), org_key)


def _membership_context(snapshot: Mapping[str, Any], membership: Mapping[str, Any]) -> dict[str, Any]:
    people = _people(snapshot)
    posts = _posts(snapshot)
    person = people.get(str(membership.get("person_id")), {})
    post = posts.get(str(membership.get("post_id")), {})
    return {
        "person_name": person.get("name"),
        "person_key": _norm(person.get("name")),
        "role_id": post.get("role_id"),
        "role_key": _role_equiv(post.get("role_id")),
        "division_ocdid": post.get("division_ocdid"),
        "label": membership.get("label"),
        "label_role_key": _role_equiv(membership.get("label")),
        "post_id": post.get("id"),
    }


def _observed_max(snapshot: Mapping[str, Any]) -> str | None:
    values = [
        str(row.get("opened_at"))
        for row in snapshot.get("memberships", [])
        if isinstance(row, Mapping) and row.get("opened_at")
    ]
    if not values:
        return None
    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    try:
        return max(values, key=parse)
    except ValueError:
        return max(values)


def _difference(
    entity_type: str,
    status: str,
    key: Any,
    reason: str,
    *,
    factory: Any = None,
    civicpatch: Any = None,
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(status)
    row = {
        "entity_type": entity_type,
        "status": status,
        "key": key,
        "reason": reason,
        "factory": factory,
        "civicpatch": civicpatch,
    }
    if fields:
        row["fields"] = dict(fields)
    return row


def reconcile(factory: Mapping[str, Any], civicpatch: Mapping[str, Any]) -> dict[str, Any]:
    """Compare semantic representation while preserving unresolved identity as unresolved."""
    differences: list[dict[str, Any]] = []
    crosswalks: list[dict[str, Any]] = []

    factory_j = factory.get("jurisdiction") or {}
    civicpatch_j = civicpatch.get("jurisdiction") or {}
    f_ocdid = factory_j.get("jurisdiction_ocdid")
    c_ocdid = civicpatch_j.get("jurisdiction_ocdid")
    if not f_ocdid or f_ocdid != c_ocdid:
        differences.append(
            _difference(
                "jurisdiction",
                "IDENTITY_CONFLICT",
                {"factory": f_ocdid, "civicpatch": c_ocdid},
                "JURISDICTION_OCDID_MISMATCH",
                factory=factory_j,
                civicpatch=civicpatch_j,
            )
        )
        return _finish(factory, civicpatch, differences, crosswalks)
    if _norm(factory_j.get("name")) == _norm(civicpatch_j.get("name")):
        differences.append(
            _difference("jurisdiction", "SAME", f_ocdid, "OCDID_AND_NAME_MATCH")
        )
    else:
        differences.append(
            _difference(
                "jurisdiction",
                "FIELD_CONFLICT",
                f_ocdid,
                "JURISDICTION_NAME_MISMATCH",
                factory=factory_j.get("name"),
                civicpatch=civicpatch_j.get("name"),
            )
        )

    # People: exact unique normalized-name matches are crosswalk candidates, never silent links.
    f_people_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    c_people_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in factory.get("people", []):
        f_people_groups[_norm(row.get("name"))].append(row)
    for row in civicpatch.get("people", []):
        c_people_groups[_norm(row.get("name"))].append(row)
    for key in sorted(set(f_people_groups) | set(c_people_groups)):
        left, right = f_people_groups.get(key, []), c_people_groups.get(key, [])
        if len(left) > 1 or len(right) > 1:
            differences.append(
                _difference(
                    "person", "BLOCKED", key, "AMBIGUOUS_NORMALIZED_NAME", factory=left, civicpatch=right
                )
            )
            continue
        if left and right:
            if _identity_shared(left[0], right[0]):
                differences.append(_difference("person", "SAME", key, "SHARED_IDENTITY"))
            else:
                differences.append(
                    _difference(
                        "person",
                        "IDENTITY_CONFLICT",
                        key,
                        (
                            "REVIEWED_SHARED_IDENTITY_MISMATCH"
                            if left[0].get("shared_identity_id")
                            and right[0].get("shared_identity_id")
                            else "EXACT_NAME_WITHOUT_SHARED_IDENTIFIER"
                        ),
                        factory={"id": left[0].get("id"), "name": left[0].get("name")},
                        civicpatch={"id": right[0].get("id"), "name": right[0].get("name")},
                    )
                )
                if not (
                    left[0].get("shared_identity_id")
                    and right[0].get("shared_identity_id")
                ):
                    crosswalks.append(
                        {
                            "entity_type": "person",
                            "status": "PROPOSED",
                            "factory_id": left[0].get("id"),
                            "civicpatch_id": right[0].get("id"),
                            "match_basis": "EXACT_NORMALIZED_NAME",
                            "normalized_name": key,
                        }
                    )
        elif left:
            differences.append(
                _difference(
                    "person", "FACTORY_ONLY", key, "PERSON_ONLY_IN_FACTORY",
                    factory={"id": left[0].get("id"), "name": left[0].get("name")}
                )
            )
        else:
            differences.append(
                _difference(
                    "person", "CIVICPATCH_ONLY", key, "PERSON_ONLY_IN_CIVICPATCH",
                    civicpatch={"id": right[0].get("id"), "name": right[0].get("name")}
                )
            )

    # Posts: semantic identity is role + division + default/body scope.
    f_posts_by_key: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    c_posts_by_key: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in factory.get("posts", []):
        f_posts_by_key[_post_semantic_key(factory, row)].append(row)
    for row in civicpatch.get("posts", []):
        c_posts_by_key[_post_semantic_key(civicpatch, row)].append(row)

    consumed_f_posts: set[str] = set()
    consumed_c_posts: set[str] = set()
    for key in sorted(set(f_posts_by_key) & set(c_posts_by_key)):
        left, right = f_posts_by_key[key], c_posts_by_key[key]
        if len(left) != 1 or len(right) != 1:
            differences.append(
                _difference("post", "BLOCKED", key, "AMBIGUOUS_POST_SEMANTIC_KEY", factory=left, civicpatch=right)
            )
            continue
        f_post, c_post = left[0], right[0]
        consumed_f_posts.add(str(f_post.get("id")))
        consumed_c_posts.add(str(c_post.get("id")))
        conflicts: dict[str, Any] = {}
        if f_post.get("meta_headcount") != c_post.get("meta_headcount"):
            conflicts["meta_headcount"] = {
                "factory": f_post.get("meta_headcount"),
                "civicpatch": c_post.get("meta_headcount"),
            }
        f_method, c_method = f_post.get("selection_method"), c_post.get("selection_method")
        if f_method not in (None, "unknown") and c_method not in (None, "unknown") and f_method != c_method:
            conflicts["selection_method"] = {"factory": f_method, "civicpatch": c_method}
        if conflicts:
            differences.append(
                _difference(
                    "post", "FIELD_CONFLICT", key, "POST_FIELDS_DIFFER", factory=f_post.get("id"),
                    civicpatch=c_post.get("id"), fields=conflicts
                )
            )
        else:
            differences.append(
                _difference(
                    "post", "SAME", key, "SEMANTIC_POST_MATCH",
                    factory=f_post.get("id"), civicpatch=c_post.get("id")
                )
            )
        if not _identity_shared(f_post, c_post):
            crosswalks.append(
                {
                    "entity_type": "post",
                    "status": "PROPOSED",
                    "factory_id": f_post.get("id"),
                    "civicpatch_id": c_post.get("id"),
                    "match_basis": "ROLE_DIVISION_ORGANIZATION_SCOPE",
                    "semantic_key": list(key),
                }
            )

    # Leadership title expressed as a CivicPatch post versus a Factory membership label.
    f_memberships = [row for row in factory.get("memberships", []) if isinstance(row, Mapping)]
    c_memberships = [row for row in civicpatch.get("memberships", []) if isinstance(row, Mapping)]
    factory_leadership = {
        (
            _membership_context(factory, row)["person_key"],
            _membership_context(factory, row)["label_role_key"],
            _membership_context(factory, row)["division_ocdid"],
        ): row
        for row in f_memberships
        if row.get("label")
    }
    leadership_c_membership_ids: set[str] = set()
    leadership_f_membership_ids: set[str] = set()
    for c_post in civicpatch.get("posts", []):
        c_post_id = str(c_post.get("id"))
        if c_post_id in consumed_c_posts:
            continue
        c_role_key = _role_equiv(c_post.get("role_id"))
        c_division = c_post.get("division_ocdid")
        occupants = [
            row for row in c_memberships if str(row.get("post_id")) == c_post_id and row.get("closed_at") is None
        ]
        matches: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for occupant in occupants:
            context = _membership_context(civicpatch, occupant)
            factory_member = factory_leadership.get(
                (context["person_key"], c_role_key, c_division)
            )
            if factory_member:
                matches.append((occupant, factory_member))
        if occupants and len(matches) == len(occupants):
            differences.append(
                _difference(
                    "post",
                    "FIELD_CONFLICT",
                    ("leadership", c_role_key, c_division),
                    "LEADERSHIP_TITLE_AS_POST",
                    factory=[pair[1].get("id") for pair in matches],
                    civicpatch=c_post_id,
                )
            )
            consumed_c_posts.add(c_post_id)
            leadership_c_membership_ids.update(str(pair[0].get("id")) for pair in matches)
            leadership_f_membership_ids.update(str(pair[1].get("id")) for pair in matches)

    for key, rows in f_posts_by_key.items():
        for row in rows:
            if str(row.get("id")) not in consumed_f_posts:
                differences.append(
                    _difference("post", "FACTORY_ONLY", key, "POST_ONLY_IN_FACTORY", factory=row.get("id"))
                )
    for key, rows in c_posts_by_key.items():
        for row in rows:
            if str(row.get("id")) not in consumed_c_posts:
                differences.append(
                    _difference("post", "CIVICPATCH_ONLY", key, "POST_ONLY_IN_CIVICPATCH", civicpatch=row.get("id"))
                )

    # Memberships: compare by person name + role + division, then flag leadership semantics.
    f_members_by_key: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    c_members_by_key: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in f_memberships:
        if str(row.get("id")) in leadership_f_membership_ids:
            continue
        context = _membership_context(factory, row)
        f_members_by_key[(context["person_key"], context["role_key"], str(context["division_ocdid"]))].append(row)
    for row in c_memberships:
        if str(row.get("id")) in leadership_c_membership_ids:
            continue
        context = _membership_context(civicpatch, row)
        c_members_by_key[(context["person_key"], context["role_key"], str(context["division_ocdid"]))].append(row)

    for key in sorted(set(f_members_by_key) | set(c_members_by_key)):
        left, right = f_members_by_key.get(key, []), c_members_by_key.get(key, [])
        if len(left) > 1 or len(right) > 1:
            differences.append(
                _difference(
                    "membership", "BLOCKED", key, "AMBIGUOUS_MEMBERSHIP_SEMANTIC_KEY",
                    factory=[row.get("id") for row in left], civicpatch=[row.get("id") for row in right]
                )
            )
            continue
        if left and right:
            conflicts: dict[str, Any] = {}
            for field in ("start_date", "end_date"):
                if left[0].get(field) != right[0].get(field):
                    conflicts[field] = {
                        "factory": left[0].get(field),
                        "civicpatch": right[0].get(field),
                    }
            if conflicts:
                differences.append(
                    _difference(
                        "membership", "FIELD_CONFLICT", key, "MEMBERSHIP_FIELDS_DIFFER",
                        factory=left[0].get("id"), civicpatch=right[0].get("id"), fields=conflicts
                    )
                )
            else:
                differences.append(
                    _difference(
                        "membership", "SAME", key, "SEMANTIC_MEMBERSHIP_MATCH",
                        factory=left[0].get("id"), civicpatch=right[0].get("id")
                    )
                )
        elif left:
            differences.append(
                _difference(
                    "membership", "FACTORY_ONLY", key, "MEMBERSHIP_ONLY_IN_FACTORY",
                    factory=left[0].get("id")
                )
            )
        else:
            differences.append(
                _difference(
                    "membership", "CIVICPATCH_ONLY", key, "MEMBERSHIP_ONLY_IN_CIVICPATCH",
                    civicpatch=right[0].get("id")
                )
            )

    # Add explicit membership-level leadership conflict once rather than left/right duplicates.
    for c_id in sorted(leadership_c_membership_ids):
        c_member = next(row for row in c_memberships if str(row.get("id")) == c_id)
        c_context = _membership_context(civicpatch, c_member)
        f_member = factory_leadership.get(
            (c_context["person_key"], c_context["role_key"], c_context["division_ocdid"])
        )
        differences.append(
            _difference(
                "membership",
                "FIELD_CONFLICT",
                (c_context["person_key"], c_context["role_key"], c_context["division_ocdid"]),
                "LEADERSHIP_TITLE_AS_POST",
                factory=f_member.get("id") if f_member else None,
                civicpatch=c_id,
            )
        )

    return _finish(factory, civicpatch, differences, crosswalks)


def _finish(
    factory: Mapping[str, Any],
    civicpatch: Mapping[str, Any],
    differences: list[dict[str, Any]],
    crosswalks: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = Counter(row["status"] for row in differences)
    f_observed, c_observed = _observed_max(factory), _observed_max(civicpatch)
    older_side = None
    if f_observed and c_observed:
        try:
            f_dt = datetime.fromisoformat(f_observed.replace("Z", "+00:00"))
            c_dt = datetime.fromisoformat(c_observed.replace("Z", "+00:00"))
            if f_dt < c_dt:
                older_side = "factory"
            elif c_dt < f_dt:
                older_side = "civicpatch"
        except ValueError:
            older_side = None
    return {
        "schema": "representation-reconciliation/1.0.0-draft",
        "jurisdiction_ocdid": (factory.get("jurisdiction") or {}).get("jurisdiction_ocdid"),
        "allowed_statuses": sorted(STATUSES),
        "counts": {status: counts.get(status, 0) for status in sorted(STATUSES)},
        "freshness": {
            "factory_generated_at": factory.get("generated_at"),
            "civicpatch_generated_at": civicpatch.get("generated_at"),
            "factory_observed_max": f_observed,
            "civicpatch_observed_max": c_observed,
            "older_observed_side": older_side,
        },
        "certification": {
            "factory": copy_json(factory.get("certification")),
            "civicpatch": copy_json(civicpatch.get("certification")),
        },
        "crosswalk_candidates": crosswalks,
        "differences": differences,
        "canonical_writes": 0,
    }


def copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("factory", type=Path)
    parser.add_argument("civicpatch", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    factory = json.loads(args.factory.read_text(encoding="utf-8"))
    civicpatch = json.loads(args.civicpatch.read_text(encoding="utf-8"))
    report = reconcile(factory, civicpatch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
