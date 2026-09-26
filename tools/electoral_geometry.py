#!/usr/bin/env python3
"""Offline validation helpers for governed local electoral geometry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "acceptance" / "representation" / "electoral_geometry_v0.1.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if (yi > y) != (yj > y):
            denominator = yj - yi
            if denominator != 0:
                crossing_x = (xj - xi) * (y - yi) / denominator + xi
                if x < crossing_x:
                    inside = not inside
        j = i
    return inside


def point_in_geometry(x: float, y: float, geometry: Mapping[str, Any]) -> bool:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        polygons = [coordinates]
    elif kind == "MultiPolygon":
        polygons = coordinates
    else:
        return False

    for polygon in polygons or []:
        if not polygon:
            continue
        if point_in_ring(x, y, polygon[0]) and not any(
            point_in_ring(x, y, hole) for hole in polygon[1:]
        ):
            return True
    return False


def validate() -> list[str]:
    errors: set[str] = set()
    fixture = load_json(FIXTURE)
    if fixture.get("contract_version") != "0.1":
        errors.add("FIXTURE_VERSION_INVALID")
    if fixture.get("result") is not True:
        errors.add("FIXTURE_RESULT_NOT_PASS")

    geometry_by_city: dict[str, dict[str, Any]] = {}
    for city, source in fixture.get("sources", {}).items():
        path = ROOT / source["artifact_path"]
        if not path.is_file():
            errors.add(f"GEOMETRY_MISSING:{city}")
            continue
        if sha256(path) != source.get("sha256"):
            errors.add(f"GEOMETRY_HASH_MISMATCH:{city}")
        geojson = load_json(path)
        if geojson.get("type") != "FeatureCollection":
            errors.add(f"GEOMETRY_TYPE_INVALID:{city}")
            continue
        features = geojson.get("features")
        if not isinstance(features, list) or len(features) != 4:
            errors.add(f"GEOMETRY_FEATURE_COUNT:{city}")
            continue
        division_ids = [
            row.get("properties", {}).get("division_id")
            for row in features
        ]
        if division_ids != source.get("division_ids"):
            errors.add(f"GEOMETRY_DIVISION_IDS:{city}")
        if len(set(division_ids)) != 4:
            errors.add(f"GEOMETRY_DIVISION_DUPLICATE:{city}")
        geometry_by_city[city] = geojson

    controls = fixture.get("pip_controls")
    if not isinstance(controls, list) or len(controls) != 8:
        errors.add("PIP_CONTROL_COUNT")
    else:
        for row in controls:
            city = row.get("city")
            geojson = geometry_by_city.get(city)
            if geojson is None:
                continue
            matches = [
                feature["properties"]["division_id"]
                for feature in geojson["features"]
                if point_in_geometry(
                    float(row["longitude"]),
                    float(row["latitude"]),
                    feature["geometry"],
                )
            ]
            if matches != [row.get("expected_division_id")]:
                errors.add(f"PIP_MISMATCH:{row.get('test_id')}")
            if row.get("result") is not True:
                errors.add(f"PIP_FIXTURE_NOT_PASS:{row.get('test_id')}")
            if row.get("geocode_score") != 100:
                errors.add(f"GEOCODE_SCORE_NOT_100:{row.get('test_id')}")

    for city, package_name in (
        ("alamosa", "jurisdiction-co-alamosa"),
        ("arvada", "jurisdiction-co-arvada"),
    ):
        package_path = (
            ROOT / "data" / "normalized" / "co" / package_name / "jurisdiction.json"
        )
        package = load_json(package_path)
        source_id = fixture["sources"][city]["source_id"]
        sources = {
            row.get("source_id"): row
            for row in package["provenance"]["source_evidence"]
        }
        if source_id not in sources:
            errors.add(f"PACKAGE_GEOMETRY_SOURCE_MISSING:{city}")
        elif sources[source_id].get("url") != fixture["sources"][city]["layer_url"]:
            errors.add(f"PACKAGE_GEOMETRY_SOURCE_URL:{city}")

        local_prefix = (
            "addrtest-co-alamosa-ward-"
            if city == "alamosa"
            else "addrtest-co-arvada-district-"
        )
        local_controls = [
            row
            for row in package["qa"]["address_tests"]
            if str(row.get("test_id") or "").startswith(local_prefix)
        ]
        if len(local_controls) != 4:
            errors.add(f"PACKAGE_LOCAL_CONTROL_COUNT:{city}")
        for row in local_controls:
            if row.get("boundary_source_id") != source_id:
                errors.add(f"PACKAGE_CONTROL_GEOMETRY_SOURCE:{row.get('test_id')}")
            artifact = fixture["sources"][city]["artifact_path"]
            if row.get("geometry_artifact") != artifact:
                errors.add(f"PACKAGE_CONTROL_GEOMETRY_ARTIFACT:{row.get('test_id')}")

        open_geometry = [
            row
            for row in package.get("warnings", [])
            if row.get("gap_type") == "MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED"
            and row.get("status") == "OPEN"
        ]
        if open_geometry:
            errors.add(f"PACKAGE_GEOMETRY_WARNING_OPEN:{city}")
        resolved = [
            row
            for row in package.get("warnings", [])
            if row.get("gap_type") == "MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED"
            and row.get("status") == "RESOLVED"
        ]
        if len(resolved) != 1:
            errors.add(f"PACKAGE_GEOMETRY_WARNING_RESOLUTION:{city}")

    return sorted(errors)


def main() -> int:
    errors = validate()
    if errors:
        raise SystemExit("validation failed: " + ", ".join(errors))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
