#!/usr/bin/env python3
"""Governed local district overlays for the reconstructed Civic GPS runtime.

The core engine owns geocoding and base geography. This extension resolves
local electoral districts from committed governed GeoJSON snapshots only.
"""
from __future__ import annotations

import copy
import json
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
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _safe_relative(root: Path, value: Any, code: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise GovernedLocalDistrictError(code)
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise GovernedLocalDistrictError(code)
    return root / relative


def validate_overlay_config(row: Mapping[str, Any]) -> list[str]:
    errors: set[str] = set()
    required = {
        "overlay_id",
        "jurisdiction_id",
        "source_registry_path",
        "source_registry_jurisdiction_id",
        "snapshot_path",
        "division_type",
        "parent_division_id",
        "districts",
    }
    if not isinstance(row, Mapping):
        return ["LOCAL_DISTRICT_OVERLAY_INVALID"]
    if not required.issubset(row):
        errors.add("LOCAL_DISTRICT_OVERLAY_FIELDS_REQUIRED")
    for key in (
        "overlay_id",
        "jurisdiction_id",
        "source_registry_path",
        "source_registry_jurisdiction_id",
        "snapshot_path",
        "division_type",
        "parent_division_id",
    ):
        if not str(row.get(key) or "").strip():
            errors.add(f"LOCAL_DISTRICT_OVERLAY_FIELD_INVALID:{key}")
    districts = row.get("districts")
    if not isinstance(districts, Mapping) or not districts:
        errors.add("LOCAL_DISTRICT_OVERLAY_DISTRICTS_REQUIRED")
    else:
        seen_divisions: set[str] = set()
        for key, meta in districts.items():
            if not str(key).strip() or not isinstance(meta, Mapping):
                errors.add("LOCAL_DISTRICT_OVERLAY_DISTRICT_INVALID")
                continue
            required_meta = {
                "division_ocdid",
                "division_id",
                "name",
            }
            if not required_meta.issubset(meta):
                errors.add("LOCAL_DISTRICT_OVERLAY_DISTRICT_FIELDS_REQUIRED")
                continue
            division_ocdid = str(meta.get("division_ocdid") or "")
            if not division_ocdid.startswith("ocd-division/"):
                errors.add("LOCAL_DISTRICT_OVERLAY_DIVISION_OCDID_INVALID")
            if division_ocdid in seen_divisions:
                errors.add("LOCAL_DISTRICT_OVERLAY_DIVISION_DUPLICATE")
            seen_divisions.add(division_ocdid)
            if not str(meta.get("division_id") or "").strip():
                errors.add("LOCAL_DISTRICT_OVERLAY_DIVISION_ID_INVALID")
            if not str(meta.get("name") or "").strip():
                errors.add("LOCAL_DISTRICT_OVERLAY_DIVISION_NAME_INVALID")
    failure_scope = str(row.get("failure_scope") or "ADAPTER").upper()
    if failure_scope != "ADAPTER":
        errors.add("LOCAL_DISTRICT_OVERLAY_FAILURE_SCOPE_UNSUPPORTED")
    if row.get("required", True) is not True:
        errors.add("LOCAL_DISTRICT_OVERLAY_REQUIRED_FALSE_UNSUPPORTED")
    return sorted(errors)


def prepare_governed_local_district_overlays(
    repo_root: str | Path,
    overlays: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    root = Path(repo_root)
    if not isinstance(overlays, list):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_OVERLAYS_INVALID"
        )

    prepared: list[dict[str, Any]] = []
    seen_overlay_ids: set[str] = set()
    for row in overlays:
        errors = validate_overlay_config(row)
        if errors:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_OVERLAY_INVALID:" + ",".join(errors)
            )
        overlay_id = str(row["overlay_id"])
        if overlay_id in seen_overlay_ids:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_OVERLAY_ID_DUPLICATE"
            )
        seen_overlay_ids.add(overlay_id)

        registry_path = _safe_relative(
            root,
            row["source_registry_path"],
            "LOCAL_DISTRICT_SOURCE_REGISTRY_PATH_INVALID",
        )
        snapshot_path = _safe_relative(
            root,
            row["snapshot_path"],
            "LOCAL_DISTRICT_SNAPSHOT_PATH_INVALID",
        )
        registry = load_source_registry(registry_path)
        registry_row = assert_registry_snapshot_ready(
            registry,
            str(row["source_registry_jurisdiction_id"]),
        )
        expected_registry_snapshot = str(
            registry_row["governed_snapshot_path"]
        )
        if expected_registry_snapshot != str(row["snapshot_path"]):
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_REGISTRY_SNAPSHOT_MISMATCH"
            )
        if not snapshot_path.is_file():
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_SNAPSHOT_MISSING"
            )
        snapshot = json.loads(
            snapshot_path.read_text(encoding="utf-8")
        )
        snapshot_errors = validate_geometry_snapshot(snapshot)
        if snapshot_errors:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_SNAPSHOT_INVALID:"
                + ",".join(snapshot_errors)
            )

        configured = {
            str(meta["division_ocdid"])
            for meta in row["districts"].values()
        }
        expected = set(snapshot["expected_division_ids"])
        if configured != expected:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_SNAPSHOT_COVERAGE_MISMATCH"
            )
        if snapshot["jurisdiction_ocdid"] != registry_row["jurisdiction_ocdid"]:
            raise GovernedLocalDistrictError(
                "LOCAL_DISTRICT_SNAPSHOT_JURISDICTION_MISMATCH"
            )

        out = copy.deepcopy(dict(row))
        out["_snapshot"] = snapshot
        out["_source_locator"] = registry_row["machine_source_url"]
        out["_source_snapshot_path"] = registry_row[
            "governed_snapshot_path"
        ]
        prepared.append(out)
    return prepared


def _dedup_sorted(payload: dict[str, Any]) -> None:
    specs = (
        ("district_assignments", "adapter_id"),
        ("matched_divisions", "division_id"),
        ("evidence", "evidence_id"),
        ("known_gaps", "gap_id"),
    )
    for key, identity in specs:
        dedup: dict[str, dict[str, Any]] = {}
        for row in payload.get(key, []):
            if (
                isinstance(row, dict)
                and row.get(identity) is not None
            ):
                dedup[str(row[identity])] = row
        payload[key] = [dedup[k] for k in sorted(dedup)]
    payload["coverage"] = sorted(
        payload.get("coverage", []),
        key=lambda row: (
            str(row.get("layer", "")),
            str(row.get("status", "")),
            str(row.get("reason", "")),
        ),
    )


def apply_governed_local_district_overlays(
    result: dict[str, Any],
    geocode: Mapping[str, Any],
    overlays: list[dict[str, Any]],
    *,
    observed_on: str | None = None,
) -> dict[str, Any]:
    if "error" in result or not overlays:
        return result
    payload = result.get("payload")
    if not isinstance(payload, dict):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_RESULT_PAYLOAD_INVALID"
        )
    active = {
        str(row.get("jurisdiction_id"))
        for row in payload.get("jurisdictions", [])
        if isinstance(row, Mapping) and row.get("jurisdiction_id")
    }
    lon = geocode.get("longitude")
    lat = geocode.get("latitude")
    if not isinstance(lon, (int, float)) or isinstance(lon, bool):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOCODE_INVALID"
        )
    if not isinstance(lat, (int, float)) or isinstance(lat, bool):
        raise GovernedLocalDistrictError(
            "LOCAL_DISTRICT_GEOCODE_INVALID"
        )

    for overlay in overlays:
        jurisdiction_id = str(overlay["jurisdiction_id"])
        if jurisdiction_id not in active:
            continue
        overlay_id = str(overlay["overlay_id"])
        try:
            division_ocdid = resolve_point(
                overlay["_snapshot"],
                x=float(lon),
                y=float(lat),
            )
        except GeometryGovernanceError as exc:
            payload.setdefault("coverage", []).append(
                {
                    "layer": "governed_local_district",
                    "status": "CONFLICT",
                    "reason": (
                        f"{overlay_id} could not resolve exactly one "
                        f"governed local district: {exc.code}"
                    ),
                }
            )
            payload.setdefault("known_gaps", []).append(
                {
                    "gap_id": f"GAP-{overlay_id}-GEOMETRY",
                    "status": "CONFLICT",
                    "summary": exc.code,
                    "reference_url": overlay["_source_locator"],
                }
            )
            continue

        reverse = {
            str(meta["division_ocdid"]): (str(key), meta)
            for key, meta in overlay["districts"].items()
        }
        resolved = reverse.get(division_ocdid)
        if resolved is None:
            payload.setdefault("known_gaps", []).append(
                {
                    "gap_id": f"GAP-{overlay_id}-IDENTITY",
                    "status": "CONFLICT",
                    "summary": (
                        "Governed snapshot returned a division not "
                        "configured in the Civic GPS overlay."
                    ),
                    "reference_url": overlay["_source_locator"],
                }
            )
            continue
        district_key, meta = resolved
        payload.setdefault("district_assignments", []).append(
            {
                "adapter_id": overlay_id,
                "district_key": district_key,
            }
        )
        payload.setdefault("matched_divisions", []).append(
            {
                "division_id": meta["division_id"],
                "name": meta["name"],
                "parent_id": overlay["parent_division_id"],
                "type": overlay["division_type"],
            }
        )
        evidence_id = f"EVID-LOCAL-{overlay_id}"
        payload.setdefault("evidence", []).append(
            {
                "evidence_id": evidence_id,
                "supports": [
                    f"district_assignments.{overlay_id}",
                    f"matched_divisions.{meta['division_id']}",
                ],
                "url": overlay["_source_locator"],
                "verified_on": observed_on,
                "snapshot_path": overlay["_source_snapshot_path"],
            }
        )
        payload.setdefault("coverage", []).append(
            {
                "layer": "governed_local_district",
                "status": "GEOGRAPHY_ONLY",
                "reason": (
                    f"{overlay_id} resolved from a governed local "
                    "GeoJSON snapshot; civic facts remain package-governed."
                ),
            }
        )

    _dedup_sorted(payload)
    return result
