#!/usr/bin/env python3
"""Generic governed coordinate -> canonical division resolver.

Consumes only committed governed geometry snapshots referenced by the source
registry. Emits geography-only payloads compatible with the Empowered Vote
Civic GPS bridge; it never emits civic facts or writes canonical data.
"""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "reference" / "co" / "district_geometry_sources_v0.1.json"
SOURCE = "GOVERNED_GEOMETRY_PIP"


class GovernedGeographyError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GovernedCoordinateResolver:
    def __init__(self, *, root: Path = ROOT, registry_path: Path = DEFAULT_REGISTRY):
        self.root = root
        self.registry_path = registry_path
        self.registry = load_source_registry(registry_path)
        self.by_id = {
            row["jurisdiction_id"]: row for row in self.registry["entries"]
        }
        self.by_ocdid = {
            row["jurisdiction_ocdid"]: row for row in self.registry["entries"]
        }
        self._snapshots: dict[str, Mapping[str, Any]] = {}

    def _entry(
        self,
        *,
        jurisdiction_id: str | None = None,
        jurisdiction_ocdid: str | None = None,
    ) -> Mapping[str, Any]:
        if bool(jurisdiction_id) == bool(jurisdiction_ocdid):
            raise GovernedGeographyError("JURISDICTION_SELECTOR_INVALID")
        row = (
            self.by_id.get(str(jurisdiction_id))
            if jurisdiction_id
            else self.by_ocdid.get(str(jurisdiction_ocdid))
        )
        if row is None:
            raise GovernedGeographyError("GOVERNED_GEOMETRY_JURISDICTION_UNKNOWN")
        try:
            return assert_registry_snapshot_ready(
                self.registry,
                str(row["jurisdiction_id"]),
            )
        except GeometryGovernanceError as exc:
            raise GovernedGeographyError(str(exc)) from exc

    def _snapshot(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        jurisdiction_id = str(row["jurisdiction_id"])
        if jurisdiction_id in self._snapshots:
            return self._snapshots[jurisdiction_id]
        path = self.root / str(row["governed_snapshot_path"])
        if not path.is_file():
            raise GovernedGeographyError("GOVERNED_GEOMETRY_SNAPSHOT_MISSING")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_geometry_snapshot(snapshot)
        if errors:
            raise GovernedGeographyError(
                "GOVERNED_GEOMETRY_SNAPSHOT_INVALID:" + ",".join(errors)
            )
        if snapshot["jurisdiction_ocdid"] != row["jurisdiction_ocdid"]:
            raise GovernedGeographyError("GOVERNED_GEOMETRY_JURISDICTION_MISMATCH")
        self._snapshots[jurisdiction_id] = snapshot
        return snapshot

    def resolve(
        self,
        *,
        longitude: float,
        latitude: float,
        jurisdiction_id: str | None = None,
        jurisdiction_ocdid: str | None = None,
    ) -> dict[str, Any]:
        row = self._entry(
            jurisdiction_id=jurisdiction_id,
            jurisdiction_ocdid=jurisdiction_ocdid,
        )
        snapshot = self._snapshot(row)
        try:
            division_ocdid = resolve_point(
                snapshot,
                x=float(longitude),
                y=float(latitude),
            )
        except GeometryGovernanceError as exc:
            raise GovernedGeographyError(str(exc)) from exc
        if division_ocdid not in row["expected_division_ids"]:
            raise GovernedGeographyError("GOVERNED_GEOMETRY_DIVISION_UNEXPECTED")
        return {
            "status": "PASS",
            "resolution_source": SOURCE,
            "jurisdiction_id": row["jurisdiction_id"],
            "jurisdiction_ocdid": row["jurisdiction_ocdid"],
            "division_ocdid": division_ocdid,
            "longitude": float(longitude),
            "latitude": float(latitude),
            "snapshot_path": row["governed_snapshot_path"],
            "source_url": row["machine_source_url"],
            "source_snapshot_id": snapshot["source"]["source_snapshot_id"],
            "canonical_writes": 0,
        }

    def civic_gps_payload(
        self,
        *,
        address: str,
        matched_address: str | None,
        longitude: float,
        latitude: float,
        jurisdiction_id: str | None = None,
        jurisdiction_ocdid: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        resolved = self.resolve(
            longitude=longitude,
            latitude=latitude,
            jurisdiction_id=jurisdiction_id,
            jurisdiction_ocdid=jurisdiction_ocdid,
        )
        adapter_id = "governed-geometry:" + resolved["jurisdiction_id"]
        payload = {
            "payload": {
                "input": {
                    "matched_address": matched_address or address,
                    "longitude": float(longitude),
                    "latitude": float(latitude),
                },
                "jurisdictions": [
                    {"jurisdiction_id": resolved["jurisdiction_id"]}
                ],
                "district_assignments": [
                    {
                        "adapter_id": adapter_id,
                        "district_key": resolved["division_ocdid"],
                    }
                ],
            }
        }
        binding = {
            "contract_jurisdiction_ocdid": resolved["jurisdiction_ocdid"],
            "civic_gps_jurisdiction_id": resolved["jurisdiction_id"],
            "district_adapter_id": adapter_id,
            "district_division_map": {
                resolved["division_ocdid"]: resolved["division_ocdid"]
            },
        }
        return payload, binding
