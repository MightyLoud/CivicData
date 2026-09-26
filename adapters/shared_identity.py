#!/usr/bin/env python3
"""Read-only bridge from product-native IDs to the shared identity registry.

Adapters may resolve reviewed Organization/Person crosswalks through this helper.
They never mint, merge, split, rename, or infer shared identities.
"""
from __future__ import annotations

from typing import Any, Mapping

from tools.shared_identity_registry import validate_registry


class SharedIdentityResolutionError(ValueError):
    """Fail-closed registry or crosswalk violation."""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


class SharedIdentityResolver:
    """Resolve active reviewed external-ID mappings without name matching."""

    def __init__(self, registry: Mapping[str, Any] | None):
        self._enabled = registry is not None
        self._entities: dict[str, Mapping[str, Any]] = {}
        self._active: dict[tuple[str, str, str], str] = {}
        if registry is None:
            return
        if not isinstance(registry, Mapping):
            raise SharedIdentityResolutionError("IDENTITY_REGISTRY_INVALID")
        registry_dict = dict(registry)
        errors = validate_registry(registry_dict)
        if errors:
            raise SharedIdentityResolutionError(
                "IDENTITY_REGISTRY_INVALID:" + ",".join(errors)
            )

        for row in registry_dict.get("entities", []):
            if not isinstance(row, Mapping):
                continue
            canonical_id = _clean(row.get("canonical_id")).lower()
            if canonical_id:
                self._entities[canonical_id] = row

        for row in registry_dict.get("crosswalks", []):
            if not isinstance(row, Mapping):
                continue
            if _clean(row.get("status")).upper() != "ACTIVE":
                continue
            key = (
                _clean(row.get("entity_type")).lower(),
                _clean(row.get("system")).lower(),
                _clean(row.get("external_id")),
            )
            canonical_id = _clean(row.get("canonical_id")).lower()
            if key[0] and key[1] and key[2] and canonical_id:
                self._active[key] = canonical_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    def resolve(
        self,
        *,
        entity_type: str,
        system: str,
        external_id: str,
    ) -> str | None:
        if not self._enabled:
            return None
        key = (
            _clean(entity_type).lower(),
            _clean(system).lower(),
            _clean(external_id),
        )
        if not all(key):
            raise SharedIdentityResolutionError("IDENTITY_LOOKUP_KEY_INVALID")
        canonical_id = self._active.get(key)
        if canonical_id is None:
            return None
        entity = self._entities.get(canonical_id)
        if entity is None:
            raise SharedIdentityResolutionError(
                "IDENTITY_CROSSWALK_CANONICAL_ID_MISSING"
            )
        if _clean(entity.get("status")).upper() != "ACTIVE":
            raise SharedIdentityResolutionError(
                "IDENTITY_CROSSWALK_CANONICAL_ID_NOT_ACTIVE"
            )
        if _clean(entity.get("entity_type")).lower() != key[0]:
            raise SharedIdentityResolutionError(
                "IDENTITY_CROSSWALK_ENTITY_TYPE_MISMATCH"
            )
        return canonical_id
