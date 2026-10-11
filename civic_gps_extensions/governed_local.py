#!/usr/bin/env python3
"""Governed local district overlays for the reconstructed Civic GPS runtime.

These overlays consume committed CivicData geometry snapshots only. They add
geography (district assignments, matched divisions, evidence, coverage) and
never add offices, officeholders, actions, or other civic facts.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.geometry_governance import (
    GeometryGovernanceError,
    assert_registry_snapshot_ready,
    load_source_registry,
    resolve_point,
    validate_geometry_snapshot,
)

DEFAULT_SOURCE_REGISTRY = Path("data/reference/co/district_geometry_sources_v0.1.json")


class GovernedLocalDistrictError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def validate_governed_local_overlay_config(rows: Any) -> list[str]:
    errors: set[str] = set()
    if rows is None:
        return []
    if not isinstance(rows, list):
        return ["GOVERNED_LOCAL_OVERLAYS_INVALID"]

    overlay_ids: set[str] = set()
    jurisdiction_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            errors.add("GOVERNED_LOCAL_OVERLAY_INVALID")
            continue
        required = (
            "overlay_id",
            "jurisdiction_id",
            "source_registry_jurisdiction_id",
            "snapshot_path",
            "parent_division_id",
            "jurisdiction_name",
            "division_type",
            "districts",
        )
        if any(not row.get(key) for key in required):
            errors.add("GOVERNED_LOCAL_OVERLAY_FIELDS_REQUIRED")
            continue

        overlay_id = _clean(row["overlay_id"])
        jurisdiction_id = _clean(row["jurisdiction_id"])
        if overlay_id in overlay_ids:
            errors.add("GOVERNED_LOCAL_OVERLAY_ID_DUPLICATE")
        overlay_ids.add(overlay_id)
        if jurisdiction_id in jurisdiction_ids:
            errors.add("GOVERNED_LOCAL_JURISDICTION_DUPLICATE")
        jurisdiction_ids.add(jurisdiction_id)

        districts = row.get("districts")
        if not isinstance(districts, Mapping) or not districts:
            errors.add("GOVERNED_LOCAL_DISTRICTS_INVALID")
            continue
        keys: set[str] = set()
        division_ids: set[str] = set()
        for division_ocdid, config in districts.items():
            if (
                not isinstance(division_ocdid, str)
                or not division_ocdid.startswith("ocd-division/")
                or not isinstance(config, Mapping)
            ):
                errors.add("GOVERNED_LOCAL_DISTRICT_CONFIG_INVALID")
                continue
            district_key = _clean(config.get("district_key"))
            division_id = _clean(config.get("division_id"))
            name = _clean(config.get("name"))
            if not district_key or not division_id or not name:
                errors.add("GOVERNED_LOCAL_DISTRICT_FIELDS_REQUIRED")
                continue
            if district_key in keys:
                errors.add("GOVERNED_LOCAL_DISTRICT_KEY_DUPLICATE")
            keys.add(district_key)
            if division_id in division_ids:
                errors.add("GOVERNED_LOCAL_DIVISION_ID_DUPLICATE")
            division_ids.add(division_id)
    return sorted(errors)


def prepare_governed_local_overlays(
    repo_root: str | Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_registry_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    errors = validate_governed_local_overlay_config(rows)
    if errors:
        raise GovernedLocalDistrictError(
            "GOVERNED_LOCAL_CONFIG_INVALID:" + ",".join(errors)
        )
    if not rows:
        return []

    root = Path(repo_root)
    registry_path = (
        Path(source_registry_path)
        if source_registry_path is not None
        else root / DEFAULT_SOURCE_REGISTRY
    )
    registry = load_source_registry(registry_path)
    prepared: list[dict[str, Any]] = []

    for source_row in rows:
        row = copy.deepcopy(dict(source_row))
        registry_id = _clean(row["source_registry_jurisdiction_id"])
        try:
            registry_row = assert_registry_snapshot_ready(registry, registry_id)
        except GeometryGovernanceError as exc:
            raise GovernedLocalDistrictError(str(exc)) from exc

        expected_path = _clean(registry_row.get("governed_snapshot_path"))
        if expected_path != _clean(row["snapshot_path"]):
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_SNAPSHOT_REGISTRY_MISMATCH"
            )

        snapshot_path = root / expected_path
        if not snapshot_path.is_file():
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_SNAPSHOT_MISSING"
            )
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_errors = validate_geometry_snapshot(snapshot)
        if snapshot_errors:
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_SNAPSHOT_INVALID:"
                + ",".join(snapshot_errors)
            )

        configured = set(row["districts"])
        expected = set(snapshot["expected_division_ids"])
        if configured != expected:
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_DIVISION_COVERAGE_MISMATCH"
            )
        if snapshot["jurisdiction_ocdid"] != registry_row["jurisdiction_ocdid"]:
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_JURISDICTION_MISMATCH"
            )

        row["_snapshot"] = snapshot
        row["_source_url"] = registry_row["machine_source_url"]
        row["_source_snapshot_id"] = snapshot["source"]["source_snapshot_id"]
        prepared.append(row)

    return prepared


def apply_governed_local_overlays(
    result: Mapping[str, Any],
    geocode: Mapping[str, Any],
    overlays: Sequence[Mapping[str, Any]],
    *,
    observed_on: str | None,
) -> dict[str, Any]:
    out = copy.deepcopy(dict(result))
    if "error" in out or not overlays:
        return out

    payload = out.get("payload")
    if not isinstance(payload, dict):
        raise GovernedLocalDistrictError(
            "GOVERNED_LOCAL_CIVIC_GPS_PAYLOAD_INVALID"
        )
    active = {
        _clean(row.get("jurisdiction_id"))
        for row in payload.get("jurisdictions", [])
        if isinstance(row, Mapping) and _clean(row.get("jurisdiction_id"))
    }

    try:
        longitude = float(geocode["longitude"])
        latitude = float(geocode["latitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GovernedLocalDistrictError(
            "GOVERNED_LOCAL_GEOCODE_INVALID"
        ) from exc

    assignment_by_adapter = {
        _clean(row.get("adapter_id")): _clean(row.get("district_key"))
        for row in payload.get("district_assignments", [])
        if isinstance(row, Mapping) and _clean(row.get("adapter_id"))
    }

    for overlay in overlays:
        jurisdiction_id = _clean(overlay["jurisdiction_id"])
        if jurisdiction_id not in active:
            continue

        try:
            division_ocdid = resolve_point(
                overlay["_snapshot"],
                x=longitude,
                y=latitude,
            )
        except GeometryGovernanceError as exc:
            code = str(exc)
            if code == "POINT_OUTSIDE_GOVERNED_GEOMETRY":
                raise GovernedLocalDistrictError(
                    "GOVERNED_LOCAL_DISTRICT_NOT_RESOLVED"
                ) from exc
            if code == "POINT_GEOMETRY_AMBIGUOUS":
                raise GovernedLocalDistrictError(
                    "GOVERNED_LOCAL_DISTRICT_AMBIGUOUS"
                ) from exc
            raise GovernedLocalDistrictError(code) from exc

        district = overlay["districts"].get(division_ocdid)
        if not isinstance(district, Mapping):
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_DISTRICT_UNMAPPED"
            )
        adapter_id = _clean(overlay["overlay_id"])
        district_key = _clean(district["district_key"])
        existing = assignment_by_adapter.get(adapter_id)
        if existing is not None and existing != district_key:
            raise GovernedLocalDistrictError(
                "GOVERNED_LOCAL_DISTRICT_CONFLICT"
            )
        assignment_by_adapter[adapter_id] = district_key

        payload.setdefault("district_assignments", []).append(
            {
                "adapter_id": adapter_id,
                "district_key": district_key,
            }
        )
        payload.setdefault("matched_divisions", []).append(
            {
                "division_id": _clean(district["division_id"]),
                "name": _clean(district["name"]),
                "parent_id": _clean(overlay["parent_division_id"]),
                "type": _clean(overlay["division_type"]),
            }
        )
        evidence_id = "EVID-LOCAL-" + adapter_id
        payload.setdefault("evidence", []).append(
            {
                "evidence_id": evidence_id,
                "supports": [
                    f"district_assignments.{adapter_id}",
                    f"matched_divisions.{_clean(district['division_id'])}",
                ],
                "url": _clean(overlay["_source_url"]),
                "verified_on": observed_on,
            }
        )
        payload.setdefault("coverage", []).append(
            {
                "layer": "governed_local_district",
                "status": "GEOGRAPHY_ONLY",
                "reason": (
                    f"{adapter_id} resolved from committed governed geometry "
                    f"snapshot {_clean(overlay['snapshot_path'])}; civic facts "
                    "remain package/contract governed."
                ),
            }
        )

    for key, id_key in (
        ("district_assignments", "adapter_id"),
        ("matched_divisions", "division_id"),
        ("evidence", "evidence_id"),
        ("known_gaps", "gap_id"),
    ):
        dedup: dict[str, Any] = {}
        for row in payload.get(key, []):
            if isinstance(row, Mapping) and row.get(id_key) is not None:
                dedup[str(row[id_key])] = row
        payload[key] = [dedup[k] for k in sorted(dedup)]
    payload["coverage"] = sorted(
        payload.get("coverage", []),
        key=lambda row: (
            _clean(row.get("layer")),
            _clean(row.get("status")),
            _clean(row.get("reason")),
        ),
    )
    return out
