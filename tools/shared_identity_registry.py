#!/usr/bin/env python3
"""Shared organization/person identity registry mechanics.

The registry is additive and review-driven. It never joins or merges identities
by display name.
"""
from __future__ import annotations

from copy import deepcopy
import re
import uuid
from typing import Any, Callable, Iterable

ID_PREFIX = {"organization": "org", "person": "per"}
ENTITY_STATUSES = {"ACTIVE", "MERGED", "RETIRED"}
CROSSWALK_STATUSES = {"ACTIVE", "RETIRED"}
EVENT_TYPES = {"RENAME", "MERGE", "ROLLBACK_MERGE", "SPLIT", "ROLLBACK_SPLIT"}
_UUID_RE = re.compile(
    r"^(?P<prefix>org|per)-"
    r"(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
    re.IGNORECASE,
)


class IdentityRegistryError(ValueError):
    """Fail-closed shared-identity registry violation."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _required_review(
    *, reviewed_at: str, reviewer: str, reason: str, evidence: str
) -> None:
    if not all(_clean(v) for v in (reviewed_at, reviewer, reason, evidence)):
        raise IdentityRegistryError("REVIEW_METADATA_REQUIRED")


def validate_identity_id(canonical_id: str, entity_type: str) -> str:
    entity_type = _clean(entity_type).lower()
    if entity_type not in ID_PREFIX:
        raise IdentityRegistryError("ENTITY_TYPE_INVALID")
    value = _clean(canonical_id).lower()
    match = _UUID_RE.fullmatch(value)
    if not match or match.group("prefix").lower() != ID_PREFIX[entity_type]:
        raise IdentityRegistryError("CANONICAL_ID_INVALID")
    return value


def mint_identity_id(
    entity_type: str,
    *,
    uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
) -> str:
    entity_type = _clean(entity_type).lower()
    if entity_type not in ID_PREFIX:
        raise IdentityRegistryError("ENTITY_TYPE_INVALID")
    value = uuid_factory()
    if not isinstance(value, uuid.UUID) or value.version != 4:
        raise IdentityRegistryError("UUID4_REQUIRED")
    return f"{ID_PREFIX[entity_type]}-{value}".lower()


def _entities(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = registry.get("entities")
    if not isinstance(rows, list):
        raise IdentityRegistryError("ENTITIES_INVALID")
    return rows


def _crosswalks(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = registry.get("crosswalks")
    if not isinstance(rows, list):
        raise IdentityRegistryError("CROSSWALKS_INVALID")
    return rows


def _events(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = registry.get("events")
    if not isinstance(rows, list):
        raise IdentityRegistryError("EVENTS_INVALID")
    return rows


def _entity_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["canonical_id"]: row for row in _entities(registry)}


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not isinstance(registry, dict):
        return ["REGISTRY_INVALID"]
    if registry.get("registry_version") != "0.1":
        errors.add("REGISTRY_VERSION_INVALID")
    if not _clean(registry.get("registry_owner")):
        errors.add("REGISTRY_OWNER_REQUIRED")
    strategy = registry.get("id_strategy")
    if strategy != {"organization": "org-<uuidv4>", "person": "per-<uuidv4>"}:
        errors.add("ID_STRATEGY_INVALID")

    try:
        entities = _entities(registry)
        crosswalks = _crosswalks(registry)
        events = _events(registry)
    except IdentityRegistryError as exc:
        return [exc.code]

    entity_ids: set[str] = set()
    entity_types: dict[str, str] = {}
    for row in entities:
        if not isinstance(row, dict):
            errors.add("ENTITY_INVALID")
            continue
        entity_type = _clean(row.get("entity_type")).lower()
        canonical_id = _clean(row.get("canonical_id")).lower()
        try:
            validate_identity_id(canonical_id, entity_type)
        except IdentityRegistryError as exc:
            errors.add(exc.code)
            continue
        if canonical_id in entity_ids:
            errors.add("DUPLICATE_CANONICAL_ID")
        entity_ids.add(canonical_id)
        entity_types[canonical_id] = entity_type
        if not _clean(row.get("display_name")) or not _clean(row.get("created_at")):
            errors.add("ENTITY_REQUIRED_FIELDS")
        status = _clean(row.get("status")).upper()
        if status not in ENTITY_STATUSES:
            errors.add("ENTITY_STATUS_INVALID")
        superseded = row.get("superseded_by")
        if status == "MERGED":
            if not isinstance(superseded, str) or not superseded:
                errors.add("MERGED_TARGET_REQUIRED")
        elif superseded not in (None, ""):
            errors.add("SUPERSEDED_BY_FORBIDDEN")

    for row in entities:
        if not isinstance(row, dict):
            continue
        if _clean(row.get("status")).upper() == "MERGED":
            source = _clean(row.get("canonical_id")).lower()
            target = _clean(row.get("superseded_by")).lower()
            if target not in entity_ids:
                errors.add("MERGED_TARGET_MISSING")
            elif entity_types.get(source) != entity_types.get(target):
                errors.add("MERGED_TARGET_TYPE_MISMATCH")

    crosswalk_ids: set[str] = set()
    active_external: dict[tuple[str, str, str], str] = {}
    for row in crosswalks:
        if not isinstance(row, dict):
            errors.add("CROSSWALK_INVALID")
            continue
        crosswalk_id = _clean(row.get("crosswalk_id"))
        if not crosswalk_id:
            errors.add("CROSSWALK_ID_REQUIRED")
        elif crosswalk_id in crosswalk_ids:
            errors.add("DUPLICATE_CROSSWALK_ID")
        crosswalk_ids.add(crosswalk_id)

        entity_type = _clean(row.get("entity_type")).lower()
        canonical_id = _clean(row.get("canonical_id")).lower()
        system = _clean(row.get("system")).lower()
        external_id = _clean(row.get("external_id"))
        status = _clean(row.get("status")).upper()
        if status not in CROSSWALK_STATUSES:
            errors.add("CROSSWALK_STATUS_INVALID")
        if canonical_id not in entity_ids:
            errors.add("CROSSWALK_CANONICAL_ID_MISSING")
        elif entity_types.get(canonical_id) != entity_type:
            errors.add("CROSSWALK_ENTITY_TYPE_MISMATCH")
        if not system or not external_id or not _clean(row.get("verified_at")) or not _clean(row.get("source")):
            errors.add("CROSSWALK_REQUIRED_FIELDS")
        if status == "ACTIVE":
            key = (entity_type, system, external_id)
            prior = active_external.get(key)
            if prior is not None and prior != canonical_id:
                errors.add("ACTIVE_EXTERNAL_ID_AMBIGUOUS")
            active_external[key] = canonical_id

    event_ids: set[str] = set()
    for row in events:
        if not isinstance(row, dict):
            errors.add("EVENT_INVALID")
            continue
        event_id = _clean(row.get("event_id"))
        if not event_id:
            errors.add("EVENT_ID_REQUIRED")
        elif event_id in event_ids:
            errors.add("DUPLICATE_EVENT_ID")
        event_ids.add(event_id)
        if _clean(row.get("event_type")).upper() not in EVENT_TYPES:
            errors.add("EVENT_TYPE_INVALID")
        if _clean(row.get("entity_type")).lower() not in ID_PREFIX:
            errors.add("EVENT_ENTITY_TYPE_INVALID")
        if not all(
            _clean(row.get(field))
            for field in ("reviewed_at", "reviewer", "reason", "evidence")
        ):
            errors.add("EVENT_REVIEW_METADATA_REQUIRED")
        if not isinstance(row.get("details"), dict):
            errors.add("EVENT_DETAILS_INVALID")

    return sorted(errors)


def _require_valid(registry: dict[str, Any]) -> None:
    errors = validate_registry(registry)
    if errors:
        raise IdentityRegistryError("REGISTRY_INVALID:" + ",".join(errors))


def resolve_external_id(
    registry: dict[str, Any],
    *,
    entity_type: str,
    system: str,
    external_id: str,
) -> str:
    _require_valid(registry)
    key = (
        _clean(entity_type).lower(),
        _clean(system).lower(),
        _clean(external_id),
    )
    matches = {
        row["canonical_id"]
        for row in _crosswalks(registry)
        if _clean(row.get("status")).upper() == "ACTIVE"
        and (
            _clean(row.get("entity_type")).lower(),
            _clean(row.get("system")).lower(),
            _clean(row.get("external_id")),
        )
        == key
    }
    if not matches:
        raise IdentityRegistryError("EXTERNAL_ID_NOT_FOUND")
    if len(matches) != 1:
        raise IdentityRegistryError("EXTERNAL_ID_AMBIGUOUS")
    return next(iter(matches))


def rename_entity(
    registry: dict[str, Any],
    *,
    canonical_id: str,
    new_display_name: str,
    event_id: str,
    reviewed_at: str,
    reviewer: str,
    reason: str,
    evidence: str,
) -> dict[str, Any]:
    _required_review(
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        reason=reason,
        evidence=evidence,
    )
    result = deepcopy(registry)
    _require_valid(result)
    entity = _entity_index(result).get(_clean(canonical_id).lower())
    if entity is None:
        raise IdentityRegistryError("CANONICAL_ID_NOT_FOUND")
    if _clean(entity.get("status")).upper() != "ACTIVE":
        raise IdentityRegistryError("ENTITY_NOT_ACTIVE")
    name = _clean(new_display_name)
    if not name:
        raise IdentityRegistryError("DISPLAY_NAME_REQUIRED")
    previous = entity["display_name"]
    entity["display_name"] = name
    _events(result).append(
        {
            "event_id": _clean(event_id),
            "event_type": "RENAME",
            "entity_type": entity["entity_type"],
            "reviewed_at": _clean(reviewed_at),
            "reviewer": _clean(reviewer),
            "reason": _clean(reason),
            "evidence": _clean(evidence),
            "details": {
                "canonical_id": entity["canonical_id"],
                "previous_display_name": previous,
                "new_display_name": name,
            },
        }
    )
    _require_valid(result)
    return result


def merge_entities(
    registry: dict[str, Any],
    *,
    target_id: str,
    source_ids: Iterable[str],
    event_id: str,
    reviewed_at: str,
    reviewer: str,
    reason: str,
    evidence: str,
) -> dict[str, Any]:
    _required_review(
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        reason=reason,
        evidence=evidence,
    )
    result = deepcopy(registry)
    _require_valid(result)
    index = _entity_index(result)
    target_id = _clean(target_id).lower()
    target = index.get(target_id)
    if target is None:
        raise IdentityRegistryError("MERGE_TARGET_NOT_FOUND")
    if _clean(target.get("status")).upper() != "ACTIVE":
        raise IdentityRegistryError("MERGE_TARGET_NOT_ACTIVE")
    sources = [_clean(x).lower() for x in source_ids]
    if not sources or len(set(sources)) != len(sources) or target_id in sources:
        raise IdentityRegistryError("MERGE_SOURCE_INVALID")
    moved: list[dict[str, str]] = []
    for source_id in sources:
        source = index.get(source_id)
        if source is None:
            raise IdentityRegistryError("MERGE_SOURCE_NOT_FOUND")
        if _clean(source.get("status")).upper() != "ACTIVE":
            raise IdentityRegistryError("MERGE_SOURCE_NOT_ACTIVE")
        if source["entity_type"] != target["entity_type"]:
            raise IdentityRegistryError("MERGE_ENTITY_TYPE_MISMATCH")
        source["status"] = "MERGED"
        source["superseded_by"] = target_id
        for row in _crosswalks(result):
            if row["canonical_id"] == source_id and row["status"] == "ACTIVE":
                moved.append(
                    {
                        "crosswalk_id": row["crosswalk_id"],
                        "from_canonical_id": source_id,
                        "to_canonical_id": target_id,
                    }
                )
                row["canonical_id"] = target_id

    _events(result).append(
        {
            "event_id": _clean(event_id),
            "event_type": "MERGE",
            "entity_type": target["entity_type"],
            "reviewed_at": _clean(reviewed_at),
            "reviewer": _clean(reviewer),
            "reason": _clean(reason),
            "evidence": _clean(evidence),
            "details": {
                "target_id": target_id,
                "source_ids": sources,
                "moved_crosswalks": moved,
            },
        }
    )
    _require_valid(result)
    return result


def rollback_merge(
    registry: dict[str, Any],
    *,
    merge_event_id: str,
    event_id: str,
    reviewed_at: str,
    reviewer: str,
    reason: str,
    evidence: str,
) -> dict[str, Any]:
    _required_review(
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        reason=reason,
        evidence=evidence,
    )
    result = deepcopy(registry)
    _require_valid(result)
    prior = next(
        (
            row
            for row in _events(result)
            if row.get("event_id") == _clean(merge_event_id)
            and row.get("event_type") == "MERGE"
        ),
        None,
    )
    if prior is None:
        raise IdentityRegistryError("MERGE_EVENT_NOT_FOUND")
    if any(
        row.get("event_type") == "ROLLBACK_MERGE"
        and row.get("details", {}).get("merge_event_id") == prior["event_id"]
        for row in _events(result)
    ):
        raise IdentityRegistryError("MERGE_ALREADY_ROLLED_BACK")

    details = prior["details"]
    target_id = details["target_id"]
    index = _entity_index(result)
    for source_id in details["source_ids"]:
        source = index.get(source_id)
        if (
            source is None
            or source.get("status") != "MERGED"
            or source.get("superseded_by") != target_id
        ):
            raise IdentityRegistryError("MERGE_ROLLBACK_STATE_CONFLICT")
        source["status"] = "ACTIVE"
        source["superseded_by"] = None

    by_id = {row["crosswalk_id"]: row for row in _crosswalks(result)}
    for move in details["moved_crosswalks"]:
        row = by_id.get(move["crosswalk_id"])
        if row is None or row.get("canonical_id") != move["to_canonical_id"]:
            raise IdentityRegistryError("MERGE_ROLLBACK_CROSSWALK_CONFLICT")
        row["canonical_id"] = move["from_canonical_id"]

    _events(result).append(
        {
            "event_id": _clean(event_id),
            "event_type": "ROLLBACK_MERGE",
            "entity_type": prior["entity_type"],
            "reviewed_at": _clean(reviewed_at),
            "reviewer": _clean(reviewer),
            "reason": _clean(reason),
            "evidence": _clean(evidence),
            "details": {"merge_event_id": prior["event_id"]},
        }
    )
    _require_valid(result)
    return result


def split_entity(
    registry: dict[str, Any],
    *,
    source_id: str,
    new_canonical_id: str,
    new_display_name: str,
    crosswalk_ids: Iterable[str],
    event_id: str,
    reviewed_at: str,
    reviewer: str,
    reason: str,
    evidence: str,
    created_at: str,
) -> dict[str, Any]:
    _required_review(
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        reason=reason,
        evidence=evidence,
    )
    result = deepcopy(registry)
    _require_valid(result)
    index = _entity_index(result)
    source_id = _clean(source_id).lower()
    source = index.get(source_id)
    if source is None or source.get("status") != "ACTIVE":
        raise IdentityRegistryError("SPLIT_SOURCE_NOT_ACTIVE")
    new_id = validate_identity_id(new_canonical_id, source["entity_type"])
    if new_id in index:
        raise IdentityRegistryError("SPLIT_TARGET_ALREADY_EXISTS")
    name = _clean(new_display_name)
    if not name or not _clean(created_at):
        raise IdentityRegistryError("SPLIT_TARGET_REQUIRED_FIELDS")

    requested = list(crosswalk_ids)
    if not requested or len(set(requested)) != len(requested):
        raise IdentityRegistryError("SPLIT_CROSSWALKS_REQUIRED")
    by_id = {row["crosswalk_id"]: row for row in _crosswalks(result)}
    moved: list[dict[str, str]] = []
    for crosswalk_id in requested:
        row = by_id.get(crosswalk_id)
        if row is None or row.get("status") != "ACTIVE":
            raise IdentityRegistryError("SPLIT_CROSSWALK_NOT_ACTIVE")
        if row.get("canonical_id") != source_id:
            raise IdentityRegistryError("SPLIT_CROSSWALK_SOURCE_MISMATCH")
        if row.get("entity_type") != source["entity_type"]:
            raise IdentityRegistryError("SPLIT_CROSSWALK_TYPE_MISMATCH")
        moved.append(
            {
                "crosswalk_id": crosswalk_id,
                "from_canonical_id": source_id,
                "to_canonical_id": new_id,
            }
        )
        row["canonical_id"] = new_id

    _entities(result).append(
        {
            "canonical_id": new_id,
            "entity_type": source["entity_type"],
            "display_name": name,
            "status": "ACTIVE",
            "created_at": _clean(created_at),
            "superseded_by": None,
        }
    )
    _events(result).append(
        {
            "event_id": _clean(event_id),
            "event_type": "SPLIT",
            "entity_type": source["entity_type"],
            "reviewed_at": _clean(reviewed_at),
            "reviewer": _clean(reviewer),
            "reason": _clean(reason),
            "evidence": _clean(evidence),
            "details": {
                "source_id": source_id,
                "new_canonical_id": new_id,
                "moved_crosswalks": moved,
            },
        }
    )
    _require_valid(result)
    return result


def rollback_split(
    registry: dict[str, Any],
    *,
    split_event_id: str,
    event_id: str,
    reviewed_at: str,
    reviewer: str,
    reason: str,
    evidence: str,
) -> dict[str, Any]:
    _required_review(
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        reason=reason,
        evidence=evidence,
    )
    result = deepcopy(registry)
    _require_valid(result)
    prior = next(
        (
            row
            for row in _events(result)
            if row.get("event_id") == _clean(split_event_id)
            and row.get("event_type") == "SPLIT"
        ),
        None,
    )
    if prior is None:
        raise IdentityRegistryError("SPLIT_EVENT_NOT_FOUND")
    if any(
        row.get("event_type") == "ROLLBACK_SPLIT"
        and row.get("details", {}).get("split_event_id") == prior["event_id"]
        for row in _events(result)
    ):
        raise IdentityRegistryError("SPLIT_ALREADY_ROLLED_BACK")

    details = prior["details"]
    source_id = details["source_id"]
    new_id = details["new_canonical_id"]
    new_entity = _entity_index(result).get(new_id)
    if new_entity is None or new_entity.get("status") != "ACTIVE":
        raise IdentityRegistryError("SPLIT_ROLLBACK_STATE_CONFLICT")

    moved_ids = {row["crosswalk_id"] for row in details["moved_crosswalks"]}
    extra_active = [
        row
        for row in _crosswalks(result)
        if row.get("canonical_id") == new_id
        and row.get("status") == "ACTIVE"
        and row.get("crosswalk_id") not in moved_ids
    ]
    if extra_active:
        raise IdentityRegistryError("SPLIT_ROLLBACK_NEW_CROSSWALK_CONFLICT")

    by_id = {row["crosswalk_id"]: row for row in _crosswalks(result)}
    for move in details["moved_crosswalks"]:
        row = by_id.get(move["crosswalk_id"])
        if row is None or row.get("canonical_id") != new_id:
            raise IdentityRegistryError("SPLIT_ROLLBACK_CROSSWALK_CONFLICT")
        row["canonical_id"] = source_id

    new_entity["status"] = "RETIRED"
    new_entity["superseded_by"] = None
    _events(result).append(
        {
            "event_id": _clean(event_id),
            "event_type": "ROLLBACK_SPLIT",
            "entity_type": prior["entity_type"],
            "reviewed_at": _clean(reviewed_at),
            "reviewer": _clean(reviewer),
            "reason": _clean(reason),
            "evidence": _clean(evidence),
            "details": {"split_event_id": prior["event_id"]},
        }
    )
    _require_valid(result)
    return result
