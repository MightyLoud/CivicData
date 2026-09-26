#!/usr/bin/env python3
"""Fail-closed OpenStates/OCDID validation for partner representation records."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

_STATE_RE = re.compile(r"(?:^|/)state:([a-z]{2})(?:/|$)")


class OCDIDRegistryError(ValueError):
    """Registry validation error carrying a stable machine-readable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def state_from_ocdid(value: str) -> str:
    match = _STATE_RE.search(value)
    if not match:
        raise OCDIDRegistryError("OCDID_FORMAT_INVALID")
    return match.group(1)


def jurisdiction_to_base_division(jurisdiction_ocdid: str) -> str:
    value = _clean(jurisdiction_ocdid)
    prefix = "ocd-jurisdiction/"
    suffix = "/government"
    if not value.startswith(prefix) or not value.endswith(suffix):
        raise OCDIDRegistryError("OCDID_FORMAT_INVALID")
    body = value[len(prefix) : -len(suffix)]
    if not body:
        raise OCDIDRegistryError("OCDID_FORMAT_INVALID")
    division = "ocd-division/" + body
    state_from_ocdid(division)
    return division


@dataclass(frozen=True)
class RegistrySnapshot:
    source_repository: str
    source_commit: str
    manifest_generated_at: str
    master_divisions: frozenset[str]
    published_divisions: frozenset[str]
    published_states: frozenset[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RegistrySnapshot":
        if not isinstance(payload, dict):
            raise OCDIDRegistryError("REGISTRY_SNAPSHOT_INVALID")
        source_repository = _clean(payload.get("source_repository"))
        source_commit = _clean(payload.get("source_commit"))
        manifest_generated_at = _clean(payload.get("manifest_generated_at"))
        if not source_repository or not source_commit or not manifest_generated_at:
            raise OCDIDRegistryError("REGISTRY_SNAPSHOT_INVALID")

        master = frozenset(_clean(x) for x in payload.get("master_divisions", []) if _clean(x))
        published = frozenset(
            _clean(x) for x in payload.get("published_divisions", []) if _clean(x)
        )
        states = frozenset(_clean(x) for x in payload.get("published_states", []) if _clean(x))

        if not master or any(not x.startswith("ocd-division/") for x in master):
            raise OCDIDRegistryError("REGISTRY_SNAPSHOT_INVALID")
        if any(x not in master for x in published):
            raise OCDIDRegistryError("REGISTRY_SNAPSHOT_INVALID")
        return cls(
            source_repository=source_repository,
            source_commit=source_commit,
            manifest_generated_at=manifest_generated_at,
            master_divisions=master,
            published_divisions=published,
            published_states=states,
        )


def _accepted_mapping_index(
    mappings: Iterable[dict[str, Any]] | None,
    *,
    entity_type: str,
) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for row in mappings or []:
        if not isinstance(row, dict):
            raise OCDIDRegistryError("REVIEWED_MAPPING_INVALID")
        if _clean(row.get("entity_type")).lower() != entity_type:
            continue
        if _clean(row.get("review_status")).lower() != "accepted":
            continue
        source = _clean(row.get("source_id"))
        target = _clean(row.get("canonical_id"))
        reviewed_at = _clean(row.get("reviewed_at"))
        reviewer = _clean(row.get("reviewer"))
        evidence = _clean(row.get("evidence"))
        if not all((source, target, reviewed_at, reviewer, evidence)):
            raise OCDIDRegistryError("REVIEWED_MAPPING_INVALID")
        candidates.setdefault(source, set()).add(target)

    result: dict[str, str] = {}
    for source, targets in candidates.items():
        if len(targets) != 1:
            raise OCDIDRegistryError("REVIEWED_MAPPING_AMBIGUOUS")
        result[source] = next(iter(targets))
    return result


def _normalize_division(
    value: str,
    *,
    registry: RegistrySnapshot,
    mappings: Iterable[dict[str, Any]] | None,
) -> tuple[str, bool]:
    source = _clean(value)
    if not source.startswith("ocd-division/"):
        raise OCDIDRegistryError("OCDID_FORMAT_INVALID")
    state_from_ocdid(source)

    mapping = _accepted_mapping_index(mappings, entity_type="division")
    canonical = mapping.get(source, source)
    used_mapping = canonical != source

    if not canonical.startswith("ocd-division/"):
        raise OCDIDRegistryError("REVIEWED_MAPPING_TARGET_INVALID")
    try:
        state_from_ocdid(canonical)
    except OCDIDRegistryError as exc:
        raise OCDIDRegistryError("REVIEWED_MAPPING_TARGET_INVALID") from exc

    if canonical not in registry.master_divisions:
        if used_mapping:
            raise OCDIDRegistryError("REVIEWED_MAPPING_TARGET_INVALID")
        raise OCDIDRegistryError("DIVISION_NOT_IN_REGISTRY")
    return canonical, used_mapping


def _normalize_jurisdiction(
    value: str,
    *,
    registry: RegistrySnapshot,
    mappings: Iterable[dict[str, Any]] | None,
) -> tuple[str, str, bool]:
    source = _clean(value)
    mapping = _accepted_mapping_index(mappings, entity_type="jurisdiction")
    canonical = mapping.get(source, source)
    used_mapping = canonical != source

    try:
        base = jurisdiction_to_base_division(canonical)
    except OCDIDRegistryError as exc:
        if used_mapping:
            raise OCDIDRegistryError("REVIEWED_MAPPING_TARGET_INVALID") from exc
        raise

    if base not in registry.master_divisions:
        if used_mapping:
            raise OCDIDRegistryError("REVIEWED_MAPPING_TARGET_INVALID")
        raise OCDIDRegistryError("JURISDICTION_BASE_DIVISION_NOT_IN_REGISTRY")
    return canonical, base, used_mapping


def validate_civicpatch_identity(
    *,
    jurisdiction_ocdid: str,
    division_ocdid: str,
    registry: RegistrySnapshot,
    reviewed_mappings: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and normalize a CivicPatch jurisdiction/division pair.

    The function never derives a new registry entry or performs fuzzy matching.
    """
    jurisdiction, base_division, jurisdiction_mapped = _normalize_jurisdiction(
        jurisdiction_ocdid,
        registry=registry,
        mappings=reviewed_mappings,
    )
    division, division_mapped = _normalize_division(
        division_ocdid,
        registry=registry,
        mappings=reviewed_mappings,
    )

    jurisdiction_state = state_from_ocdid(base_division)
    division_state = state_from_ocdid(division)
    if jurisdiction_state != division_state:
        raise OCDIDRegistryError("STATE_MISMATCH")

    if division != base_division and not division.startswith(base_division + "/"):
        raise OCDIDRegistryError("DIVISION_OUTSIDE_JURISDICTION")

    mapping_applied = jurisdiction_mapped or division_mapped
    if mapping_applied:
        status = "REVIEWED_MAPPING"
    elif division in registry.published_divisions:
        status = "PUBLISHED_LOOKUP"
    else:
        status = "MASTER_REGISTRY_COMPATIBILITY"

    return {
        "jurisdiction_ocdid": jurisdiction,
        "jurisdiction_base_division_ocdid": base_division,
        "division_ocdid": division,
        "state": jurisdiction_state,
        "registry_status": status,
        "mapping_applied": mapping_applied,
        "source_repository": registry.source_repository,
        "source_commit": registry.source_commit,
        "registry_manifest_generated_at": registry.manifest_generated_at,
    }
