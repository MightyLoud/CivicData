#!/usr/bin/env python3
"""Governed local-district overlays for the reconstructed Civic GPS runtime.

These overlays are geography-only. They reuse the engine's already validated
geocode, resolve the point against a committed governed geometry snapshot, and
emit only matched divisions, district assignments, evidence, and coverage.
They never emit offices, officeholders, actions, or other civic facts.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from tools.geometry_governance import (
    GeometryGovernanceError,
    assert_registry_snapshot_ready,
    load_source_registry,
    resolve_point,
    validate_geometry_snapshot,
)


class GovernedLocalDistrictError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}: {detail}")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()


def _relative_path(value: Any, field: str) -> str:
    text = _clean(value)
    if not text:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_OVERLAY_PATH_REQUIRED",
            field,
        )
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_OVERLAY_PATH_INVALID",
            f"{field}:{text}",
        )
    return text


def validate_governed_local_district_overlays(
    overlays: Any,
) -> None:
    if overlays is None:
        return
    if not isinstance(overlays, list):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_OVERLAYS_INVALID",
            "expected list",
        )

    overlay_ids: set[str] = set()
    adapter_ids: set[str] = set()
    for row in overlays:
        if not isinstance(row, Mapping):
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_OVERLAY_INVALID",
                "expected object",
            )
        required = (
            "overlay_id",
            "parent_jurisdiction_id",
            "adapter_id",
            "source_registry_path",
            "source_registry_jurisdiction_id",
            "division_type",
            "districts",
        )
        for key in required:
            if row.get(key) in (None, "", {}):
                raise GovernedLocalDistrictError(
                    "LOCAL_DISTRICT_OVERLAY_FIELD_MISSING",
                    f"{row.get('overlay_id')}:{key}",
                )

        overlay_id = _clean(row["overlay_id"])
        adapter_id = _clean(row["adapter_id"])
        if overlay_id in overlay_ids:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_OVERLAY_ID_DUPLICATE",
                overlay_id,
            )
        if adapter_id in adapter_ids:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_ADAPTER_ID_DUPLICATE",
                adapter_id,
            )
        overlay_ids.add(overlay_id)
        adapter_ids.add(adapter_id)

        _relative_path(row["source_registry_path"], "source_registry_path")

        districts = row["districts"]
        if not isinstance(districts, Mapping) or not districts:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_MAP_INVALID",
                overlay_id,
            )

        district_keys: set[str] = set()
        division_ids: set[str] = set()
        for ocdid, spec in districts.items():
            if (
                not isinstance(ocdid, str)
                or not ocdid.startswith("ocd-division/")
                or not isinstance(spec, Mapping)
            ):
                raise GovernedLocalDistrictError(
                    "LOCAL_DISTRICT_ENTRY_INVALID",
                    overlay_id,
                )
            for key in ("district_key", "division_id", "name"):
                if not _clean(spec.get(key)):
                    raise GovernedLocalDistrictError(
                        "LOCAL_DISTRICT_ENTRY_FIELD_MISSING",
                        f"{overlay_id}:{ocdid}:{key}",
                    )
            district_key = _clean(spec["district_key"])
            division_id = _clean(spec["division_id"])
            if district_key in district_keys:
                raise GovernedLocalDistrictError(
                    "LOCAL_DISTRICT_KEY_DUPLICATE",
                    f"{overlay_id}:{district_key}",
                )
            if division_id in division_ids:
                raise GovernedLocalDistrictError(
                    "LOCAL_DISTRICT_DIVISION_ID_DUPLICATE",
                    f"{overlay_id}:{division_id}",
                )
            district_keys.add(district_key)
            division_ids.add(division_id)


def _load_governed_snapshot(
    root: Path,
    overlay: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    registry_path = root / _relative_path(
        overlay["source_registry_path"],
        "source_registry_path",
    )
    try:
        registry = load_source_registry(registry_path)
        registry_row = assert_registry_snapshot_ready(
            registry,
            _clean(overlay["source_registry_jurisdiction_id"]),
        )
    except (OSError, json.JSONDecodeError, GeometryGovernanceError) as exc:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOMETRY_SOURCE_NOT_READY",
            str(exc),
        ) from exc

    snapshot_path = root / _relative_path(
        registry_row.get("governed_snapshot_path"),
        "governed_snapshot_path",
    )
    if not snapshot_path.is_file():
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOMETRY_SNAPSHOT_MISSING",
            str(snapshot_path),
        )
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOMETRY_SNAPSHOT_INVALID",
            str(exc),
        ) from exc

    errors = validate_geometry_snapshot(snapshot)
    if errors:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOMETRY_SNAPSHOT_INVALID",
            ",".join(errors),
        )

    expected = set(str(x) for x in registry_row["expected_division_ids"])
    configured = set(str(x) for x in overlay["districts"])
    if expected != configured:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOMETRY_BINDING_DRIFT",
            f"registry={sorted(expected)} configured={sorted(configured)}",
        )
    if set(snapshot["expected_division_ids"]) != configured:
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOMETRY_SNAPSHOT_COVERAGE_DRIFT",
            _clean(overlay["overlay_id"]),
        )

    return registry_row, snapshot


def apply_governed_local_district_overlays(
    result: Mapping[str, Any],
    geocode: Mapping[str, Any],
    overlays: list[dict[str, Any]],
    *,
    repo_root: str | Path,
    observed_on: str | None,
) -> dict[str, Any]:
    validate_governed_local_district_overlays(overlays)
    output = copy.deepcopy(dict(result))
    payload = output.get("payload")
    if not isinstance(payload, dict):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_CIVIC_GPS_PAYLOAD_INVALID"
        )

    jurisdictions = payload.get("jurisdictions")
    if not isinstance(jurisdictions, list):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_CIVIC_GPS_JURISDICTIONS_INVALID"
        )
    active = {
        _clean(row.get("jurisdiction_id"))
        for row in jurisdictions
        if isinstance(row, Mapping) and _clean(row.get("jurisdiction_id"))
    }
    candidates = [
        row
        for row in overlays
        if _clean(row["parent_jurisdiction_id"]) in active
    ]
    if not candidates:
        return output

    longitude = geocode.get("longitude")
    latitude = geocode.get("latitude")
    if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOCODE_COORDINATES_INVALID"
        )
    if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOCODE_COORDINATES_INVALID"
        )

    root = Path(repo_root)
    assignments = payload.setdefault("district_assignments", [])
    divisions = payload.setdefault("matched_divisions", [])
    evidence = payload.setdefault("evidence", [])
    coverage = payload.setdefault("coverage", [])

    if not all(isinstance(x, list) for x in (assignments, divisions, evidence, coverage)):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_CIVIC_GPS_COLLECTION_INVALID"
        )

    assignment_index = {
        _clean(row.get("adapter_id")): _clean(row.get("district_key"))
        for row in assignments
        if isinstance(row, Mapping) and _clean(row.get("adapter_id"))
    }

    for overlay in candidates:
        registry_row, snapshot = _load_governed_snapshot(root, overlay)
        try:
            resolved_ocdid = resolve_point(
                snapshot,
                x=float(longitude),
                y=float(latitude),
            )
        except GeometryGovernanceError as exc:
            code = str(exc)
            if code == "POINT_OUTSIDE_GOVERNED_GEOMETRY":
                raise GovernedLocalDistrictError(
                    "LOCAL_DISTRICT_NOT_RESOLVED",
                    _clean(overlay["overlay_id"]),
                ) from exc
            if code == "POINT_GEOMETRY_AMBIGUOUS":
                raise GovernedLocalDistrictError(
                    "LOCAL_DISTRICT_AMBIGUOUS",
                    _clean(overlay["overlay_id"]),
                ) from exc
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_GEOMETRY_RESOLUTION_FAILED",
                code,
            ) from exc

        spec = overlay["districts"].get(resolved_ocdid)
        if not isinstance(spec, Mapping):
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_RESULT_UNMAPPED",
                resolved_ocdid,
            )

        adapter_id = _clean(overlay["adapter_id"])
        district_key = _clean(spec["district_key"])
        prior = assignment_index.get(adapter_id)
        if prior is not None and prior != district_key:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_ASSIGNMENT_CONFLICT",
                f"{adapter_id}:{prior}!={district_key}",
            )
        if prior is None:
            assignments.append(
                {
                    "adapter_id": adapter_id,
                    "district_key": district_key,
                }
            )
            assignment_index[adapter_id] = district_key

        divisions.append(
            {
                "division_id": _clean(spec["division_id"]),
                "name": _clean(spec["name"]),
                "parent_id": spec.get("parent_division_id"),
                "type": _clean(overlay["division_type"]),
            }
        )

        evidence_id = "EVID-LOCAL-" + _slug(_clean(overlay["overlay_id"]))
        evidence.append(
            {
                "evidence_id": evidence_id,
                "supports": [
                    f"district_assignments.{adapter_id}",
                    f"matched_divisions.{_clean(spec['division_id'])}",
                ],
                "url": snapshot["source"]["locator"],
                "verified_on": observed_on,
                "source_snapshot_id": snapshot["source"]["source_snapshot_id"],
            }
        )
        coverage.append(
            {
                "layer": "governed_local_district",
                "status": "GEOGRAPHY_ONLY",
                "reason": (
                    f"{_clean(overlay['overlay_id'])} resolved from committed "
                    "governed Polygon/MultiPolygon geometry; civic facts remain "
                    "package-governed."
                ),
                "source_url": registry_row["machine_source_url"],
            }
        )

    # Stable de-duplication. This intentionally does not touch applicable
    # offices, officeholders, or actions.
    for key, id_key in (
        ("district_assignments", "adapter_id"),
        ("matched_divisions", "division_id"),
        ("evidence", "evidence_id"),
    ):
        dedup: dict[str, Any] = {}
        for row in payload.get(key, []):
            if isinstance(row, Mapping) and row.get(id_key) is not None:
                dedup[str(row[id_key])] = row
        payload[key] = [dedup[k] for k in sorted(dedup)]

    payload["coverage"] = sorted(
        payload.get("coverage", []),
        key=lambda row: (
            str(row.get("layer", "")),
            str(row.get("status", "")),
            str(row.get("reason", "")),
        ),
    )
    return output
