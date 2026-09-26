#!/usr/bin/env python3
"""Governed geometry snapshot validation and point-in-polygon helpers.

Only archived Polygon/MultiPolygon GeoJSON snapshots with explicit authority
metadata are eligible. Map-only sources and unresolved endpoints fail closed.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


class GeometryGovernanceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _valid_timestamp(value: Any) -> bool:
    text = _clean(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def load_source_registry(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_source_registry(data)
    if errors:
        raise GeometryGovernanceError(
            "SOURCE_REGISTRY_INVALID:" + ",".join(errors)
        )
    return data


def validate_source_registry(registry: Mapping[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not isinstance(registry, Mapping):
        return ["SOURCE_REGISTRY_INVALID"]
    if registry.get("registry_version") != "0.1":
        errors.add("SOURCE_REGISTRY_VERSION_INVALID")
    if not _valid_timestamp(registry.get("reviewed_at")):
        errors.add("SOURCE_REGISTRY_REVIEWED_AT_INVALID")
    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.add("SOURCE_REGISTRY_ENTRIES_REQUIRED")
        return sorted(errors)

    seen: set[str] = set()
    allowed_states = {
        "RESOLVED_MACHINE_READABLE",
        "UNRESOLVED_ENDPOINT",
        "MAP_ONLY",
    }
    for row in entries:
        if not isinstance(row, Mapping):
            errors.add("SOURCE_REGISTRY_ENTRY_INVALID")
            continue
        jurisdiction_id = _clean(row.get("jurisdiction_id"))
        if not jurisdiction_id or jurisdiction_id in seen:
            errors.add("SOURCE_REGISTRY_JURISDICTION_ID_INVALID")
        seen.add(jurisdiction_id)
        if not _clean(row.get("jurisdiction_ocdid")).startswith(
            "ocd-jurisdiction/"
        ):
            errors.add("SOURCE_REGISTRY_JURISDICTION_OCDID_INVALID")
        divisions = row.get("expected_division_ids")
        if (
            not isinstance(divisions, list)
            or not divisions
            or len(divisions) != len(set(divisions))
            or any(
                not isinstance(value, str)
                or not value.startswith("ocd-division/")
                for value in divisions
            )
        ):
            errors.add("SOURCE_REGISTRY_DIVISIONS_INVALID")
        sources = row.get("authority_sources")
        if not isinstance(sources, list) or not sources:
            errors.add("SOURCE_REGISTRY_AUTHORITY_REQUIRED")
        else:
            for source in sources:
                if (
                    not isinstance(source, Mapping)
                    or source.get("authority")
                    not in {"PRIMARY_OFFICIAL", "SECONDARY_OFFICIAL"}
                    or not _clean(source.get("url"))
                ):
                    errors.add("SOURCE_REGISTRY_AUTHORITY_INVALID")
        status = row.get("machine_source_status")
        if status not in allowed_states:
            errors.add("SOURCE_REGISTRY_STATUS_INVALID")
        machine_url = row.get("machine_source_url")
        snapshot_path = row.get("governed_snapshot_path")
        blocker = _clean(row.get("blocker_code"))
        if status == "RESOLVED_MACHINE_READABLE":
            if not _clean(machine_url) or not _clean(snapshot_path):
                errors.add("RESOLVED_MACHINE_SOURCE_FIELDS_REQUIRED")
            if blocker:
                errors.add("RESOLVED_MACHINE_SOURCE_BLOCKER_FORBIDDEN")
        else:
            if machine_url not in (None, ""):
                errors.add("UNRESOLVED_MACHINE_SOURCE_URL_FORBIDDEN")
            if snapshot_path not in (None, ""):
                errors.add("UNRESOLVED_SNAPSHOT_PATH_FORBIDDEN")
            if not blocker:
                errors.add("UNRESOLVED_BLOCKER_REQUIRED")
    return sorted(errors)


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _ring_valid(ring: Any) -> bool:
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    for point in ring:
        if (
            not isinstance(point, list)
            or len(point) < 2
            or not _number(point[0])
            or not _number(point[1])
        ):
            return False
    return ring[0][0] == ring[-1][0] and ring[0][1] == ring[-1][1]


def _polygon_valid(coords: Any) -> bool:
    return (
        isinstance(coords, list)
        and bool(coords)
        and all(_ring_valid(ring) for ring in coords)
    )


def _multipolygon_valid(coords: Any) -> bool:
    return (
        isinstance(coords, list)
        and bool(coords)
        and all(_polygon_valid(polygon) for polygon in coords)
    )


def validate_geometry_snapshot(snapshot: Mapping[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not isinstance(snapshot, Mapping):
        return ["GEOMETRY_SNAPSHOT_INVALID"]
    required = {
        "snapshot_version",
        "snapshot_id",
        "generated_at",
        "jurisdiction_ocdid",
        "source",
        "division_property",
        "expected_division_ids",
        "feature_collection",
    }
    if set(snapshot) != required:
        errors.add("GEOMETRY_SNAPSHOT_FIELDS_INVALID")
    if snapshot.get("snapshot_version") != "0.1":
        errors.add("GEOMETRY_SNAPSHOT_VERSION_INVALID")
    if not _clean(snapshot.get("snapshot_id")):
        errors.add("GEOMETRY_SNAPSHOT_ID_REQUIRED")
    if not _valid_timestamp(snapshot.get("generated_at")):
        errors.add("GEOMETRY_SNAPSHOT_GENERATED_AT_INVALID")
    if not _clean(snapshot.get("jurisdiction_ocdid")).startswith(
        "ocd-jurisdiction/"
    ):
        errors.add("GEOMETRY_SNAPSHOT_JURISDICTION_INVALID")

    source = snapshot.get("source")
    if not isinstance(source, Mapping):
        errors.add("GEOMETRY_SNAPSHOT_SOURCE_INVALID")
    else:
        if source.get("authority") not in {
            "PRIMARY_OFFICIAL",
            "SECONDARY_OFFICIAL",
        }:
            errors.add("GEOMETRY_SNAPSHOT_SOURCE_AUTHORITY_INVALID")
        if source.get("derivation") not in {
            "DIRECT_MACHINE_SOURCE",
            "OFFICIAL_EXPORT",
        }:
            errors.add("GEOMETRY_SNAPSHOT_DERIVATION_INVALID")
        if not _clean(source.get("locator")):
            errors.add("GEOMETRY_SNAPSHOT_SOURCE_LOCATOR_REQUIRED")
        if not _valid_timestamp(source.get("retrieved_at")):
            errors.add("GEOMETRY_SNAPSHOT_SOURCE_RETRIEVED_AT_INVALID")
        if not _clean(source.get("source_snapshot_id")):
            errors.add("GEOMETRY_SNAPSHOT_SOURCE_ID_REQUIRED")

    division_property = _clean(snapshot.get("division_property"))
    if not division_property:
        errors.add("GEOMETRY_SNAPSHOT_DIVISION_PROPERTY_REQUIRED")
    expected = snapshot.get("expected_division_ids")
    if (
        not isinstance(expected, list)
        or not expected
        or len(expected) != len(set(expected))
    ):
        errors.add("GEOMETRY_SNAPSHOT_EXPECTED_DIVISIONS_INVALID")
        expected_set: set[str] = set()
    else:
        expected_set = set(expected)
        if any(
            not isinstance(value, str)
            or not value.startswith("ocd-division/")
            for value in expected
        ):
            errors.add("GEOMETRY_SNAPSHOT_EXPECTED_DIVISIONS_INVALID")

    fc = snapshot.get("feature_collection")
    if (
        not isinstance(fc, Mapping)
        or fc.get("type") != "FeatureCollection"
        or not isinstance(fc.get("features"), list)
        or not fc.get("features")
    ):
        errors.add("GEOMETRY_FEATURE_COLLECTION_INVALID")
        return sorted(errors)

    seen: set[str] = set()
    for feature in fc["features"]:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            errors.add("GEOMETRY_FEATURE_INVALID")
            continue
        props = feature.get("properties")
        if not isinstance(props, Mapping):
            errors.add("GEOMETRY_FEATURE_PROPERTIES_INVALID")
            continue
        division_id = props.get(division_property)
        if not isinstance(division_id, str) or division_id not in expected_set:
            errors.add("GEOMETRY_FEATURE_DIVISION_INVALID")
        elif division_id in seen:
            errors.add("GEOMETRY_FEATURE_DIVISION_DUPLICATE")
        else:
            seen.add(division_id)

        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping):
            errors.add("GEOMETRY_FEATURE_GEOMETRY_INVALID")
            continue
        kind = geometry.get("type")
        coords = geometry.get("coordinates")
        if kind == "Polygon":
            if not _polygon_valid(coords):
                errors.add("GEOMETRY_POLYGON_INVALID")
        elif kind == "MultiPolygon":
            if not _multipolygon_valid(coords):
                errors.add("GEOMETRY_MULTIPOLYGON_INVALID")
        else:
            errors.add("GEOMETRY_TYPE_INVALID")

    if seen != expected_set:
        errors.add("GEOMETRY_DIVISION_COVERAGE_INCOMPLETE")
    return sorted(errors)


def _point_on_segment(
    point: tuple[float, float],
    a: Sequence[float],
    b: Sequence[float],
    eps: float = 1e-12,
) -> bool:
    x, y = point
    x1, y1 = float(a[0]), float(a[1])
    x2, y2 = float(b[0]), float(b[1])
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > eps:
        return False
    dot = (x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)
    if dot < -eps:
        return False
    squared = (x2 - x1) ** 2 + (y2 - y1) ** 2
    return dot <= squared + eps


def _ring_contains(
    point: tuple[float, float],
    ring: Sequence[Sequence[float]],
) -> tuple[bool, bool]:
    inside = False
    x, y = point
    for i in range(len(ring) - 1):
        a = ring[i]
        b = ring[i + 1]
        if _point_on_segment(point, a, b):
            return True, True
        x1, y1 = float(a[0]), float(a[1])
        x2, y2 = float(b[0]), float(b[1])
        if ((y1 > y) != (y2 > y)):
            intersect_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersect_x:
                inside = not inside
    return inside, False


def _polygon_contains(
    point: tuple[float, float],
    polygon: Sequence[Sequence[Sequence[float]]],
) -> bool:
    outer, boundary = _ring_contains(point, polygon[0])
    if boundary:
        return True
    if not outer:
        return False
    for hole in polygon[1:]:
        inside_hole, hole_boundary = _ring_contains(point, hole)
        if hole_boundary:
            return True
        if inside_hole:
            return False
    return True


def geometry_contains(
    geometry: Mapping[str, Any],
    point: tuple[float, float],
) -> bool:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon":
        return _polygon_contains(point, coords)
    if kind == "MultiPolygon":
        return any(_polygon_contains(point, polygon) for polygon in coords)
    raise GeometryGovernanceError("GEOMETRY_TYPE_INVALID")


def resolve_point(
    snapshot: Mapping[str, Any],
    *,
    x: float,
    y: float,
) -> str:
    errors = validate_geometry_snapshot(snapshot)
    if errors:
        raise GeometryGovernanceError(
            "GEOMETRY_SNAPSHOT_INVALID:" + ",".join(errors)
        )
    division_property = snapshot["division_property"]
    matches: list[str] = []
    for feature in snapshot["feature_collection"]["features"]:
        if geometry_contains(feature["geometry"], (float(x), float(y))):
            matches.append(feature["properties"][division_property])
    if not matches:
        raise GeometryGovernanceError("POINT_OUTSIDE_GOVERNED_GEOMETRY")
    if len(matches) != 1:
        raise GeometryGovernanceError("POINT_GEOMETRY_AMBIGUOUS")
    return matches[0]


def assert_registry_snapshot_ready(
    registry: Mapping[str, Any],
    jurisdiction_id: str,
) -> Mapping[str, Any]:
    errors = validate_source_registry(registry)
    if errors:
        raise GeometryGovernanceError(
            "SOURCE_REGISTRY_INVALID:" + ",".join(errors)
        )
    matches = [
        row
        for row in registry["entries"]
        if row["jurisdiction_id"] == jurisdiction_id
    ]
    if len(matches) != 1:
        raise GeometryGovernanceError("SOURCE_REGISTRY_JURISDICTION_NOT_UNIQUE")
    row = matches[0]
    if row["machine_source_status"] != "RESOLVED_MACHINE_READABLE":
        raise GeometryGovernanceError(str(row["blocker_code"]))
    return row
