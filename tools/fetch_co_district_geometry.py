#!/usr/bin/env python3
"""Fetch and normalize governed Colorado local-district geometry snapshots.

Network access is used only by the explicit fetch command. Runtime/CI geometry
validation consumes committed snapshots offline.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SNAPSHOT_VERSION = "0.1"
USER_AGENT = "MightyLoud-CivicData-Geometry-Ingest/0.1"

LAYERS = {
    "alamosa": {
        "jurisdiction_id": "jurisdiction-co-alamosa",
        "source_system": "City of Alamosa ArcGIS",
        "service_item_id": "ef74f0c6ea8f45328b894c30b3120dda",
        "layer_url": (
            "https://services2.arcgis.com/kQ9CrbL3URg6t3jo/ArcGIS/rest/services/"
            "Wards/FeatureServer/0"
        ),
        "number_field": "WARD",
        "name_field": "Label",
        "division_template": "division-co-alamosa-ward-{number}",
        "output": "alamosa_wards.geojson",
        "expected_numbers": [1, 2, 3, 4],
    },
    "arvada": {
        "jurisdiction_id": "jurisdiction-co-arvada",
        "source_system": "City of Arvada ArcGIS",
        "service_item_id": "99eeb87a31af46c49e7ea34e5a8c2e46",
        "layer_url": (
            "https://services.arcgis.com/j3zNT485kmwrBtMJ/ArcGIS/rest/services/"
            "City_Council_Districts/FeatureServer/0"
        ),
        "number_field": "District",
        "name_field": "NAME",
        "division_template": "division-co-arvada-district-{number}",
        "output": "arvada_council_districts.geojson",
        "expected_numbers": [1, 2, 3, 4],
    },
}

CONTROLS = [
    {
        "test_id": "addrtest-co-alamosa-ward-1-cattails",
        "jurisdiction": "alamosa",
        "division_id": "division-co-alamosa-ward-1",
        "address": "500 Cottonwood Dr, Alamosa, CO 81101",
    },
    {
        "test_id": "addrtest-co-alamosa-ward-2-carroll-park",
        "jurisdiction": "alamosa",
        "division_id": "division-co-alamosa-ward-2",
        "address": "860 Craft Dr, Alamosa, CO 81101",
    },
    {
        "test_id": "addrtest-co-alamosa-ward-3-jardin-hermosa",
        "jurisdiction": "alamosa",
        "division_id": "division-co-alamosa-ward-3",
        "address": "1555 W Sixth St, Alamosa, CO 81101",
    },
    {
        "test_id": "addrtest-co-alamosa-ward-4-lee-fields",
        "jurisdiction": "alamosa",
        "division_id": "division-co-alamosa-ward-4",
        "address": "1000 Twentieth St, Alamosa, CO 81101",
    },
    {
        "test_id": "addrtest-co-arvada-district-1-lake-arbor-golf",
        "jurisdiction": "arvada",
        "division_id": "division-co-arvada-district-1",
        "address": "8600 Wadsworth Boulevard, Arvada, CO 80003",
    },
    {
        "test_id": "addrtest-co-arvada-district-2-little-dry-creek",
        "jurisdiction": "arvada",
        "division_id": "division-co-arvada-district-2",
        "address": "7770 Pierce St, Arvada, CO 80003",
    },
    {
        "test_id": "addrtest-co-arvada-district-3-little-raven",
        "jurisdiction": "arvada",
        "division_id": "division-co-arvada-district-3",
        "address": "12140 W 57th Ave, Arvada, CO 80002",
    },
    {
        "test_id": "addrtest-co-arvada-district-4-west-woods",
        "jurisdiction": "arvada",
        "division_id": "division-co-arvada-district-4",
        "address": "6655 Quaker Street, Arvada, CO 80007",
    },
]


class GeometryFetchError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _get_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise GeometryFetchError(f"HTTP_{response.status}:{url}")
        return json.loads(response.read().decode("utf-8"))


def _round_coordinates(value: Any, places: int = 7) -> Any:
    if isinstance(value, list):
        if value and all(isinstance(item, (int, float)) for item in value):
            return [round(float(item), places) for item in value]
        return [_round_coordinates(item, places) for item in value]
    return value


def _normalize_geometry(geometry: Mapping[str, Any]) -> dict[str, Any]:
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise GeometryFetchError(f"UNSUPPORTED_GEOMETRY:{geometry_type}")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise GeometryFetchError("GEOMETRY_COORDINATES_INVALID")
    return {
        "type": geometry_type,
        "coordinates": _round_coordinates(coordinates),
    }


def fetch_layer(key: str) -> dict[str, Any]:
    spec = LAYERS[key]
    params = urlencode(
        {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
    )
    query_url = f"{spec['layer_url']}/query?{params}"
    raw = _get_json(query_url)
    if raw.get("type") != "FeatureCollection":
        raise GeometryFetchError(f"{key}:NOT_FEATURE_COLLECTION")

    features = []
    observed_numbers = []
    for raw_feature in raw.get("features", []):
        if not isinstance(raw_feature, Mapping):
            continue
        props = raw_feature.get("properties") or {}
        try:
            number = int(props[spec["number_field"]])
        except (KeyError, TypeError, ValueError) as exc:
            raise GeometryFetchError(f"{key}:DISTRICT_NUMBER_INVALID") from exc
        if number not in spec["expected_numbers"]:
            continue
        observed_numbers.append(number)
        geometry = _normalize_geometry(raw_feature.get("geometry") or {})
        feature = {
            "type": "Feature",
            "id": f"{spec['jurisdiction_id']}:{number}",
            "properties": {
                "division_id": spec["division_template"].format(number=number),
                "district_number": number,
                "source_feature_id": props.get("FID")
                or props.get("OBJECTID")
                or props.get("OBJECTID_1"),
                "source_name": props.get(spec["name_field"]),
            },
            "geometry": geometry,
        }
        features.append(feature)

    if sorted(observed_numbers) != spec["expected_numbers"]:
        raise GeometryFetchError(
            f"{key}:FEATURE_SET_INVALID:{sorted(observed_numbers)}"
        )

    features.sort(key=lambda row: row["properties"]["district_number"])
    return {
        "type": "FeatureCollection",
        "name": key,
        "civicdata": {
            "snapshot_version": SNAPSHOT_VERSION,
            "jurisdiction_id": spec["jurisdiction_id"],
            "source_system": spec["source_system"],
            "service_item_id": spec["service_item_id"],
            "layer_url": spec["layer_url"],
            "query": {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": True,
                "outSR": 4326,
                "format": "geojson",
            },
        },
        "features": features,
    }


def _point_on_segment(
    x: float,
    y: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    epsilon: float = 1e-12,
) -> bool:
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > epsilon:
        return False
    dot = (x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)
    if dot < -epsilon:
        return False
    squared = (x2 - x1) ** 2 + (y2 - y1) ** 2
    return dot <= squared + epsilon


def _ring_contains(ring: list[list[float]], x: float, y: float) -> bool:
    inside = False
    if len(ring) < 4:
        return False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][:2]
        x2, y2 = ring[index + 1][:2]
        if _point_on_segment(x, y, x1, y1, x2, y2):
            return True
        if (y1 > y) != (y2 > y):
            intersect_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersect_x:
                inside = not inside
    return inside


def _polygon_contains(rings: list[list[list[float]]], x: float, y: float) -> bool:
    if not rings or not _ring_contains(rings[0], x, y):
        return False
    return not any(_ring_contains(hole, x, y) for hole in rings[1:])


def geometry_contains(geometry: Mapping[str, Any], x: float, y: float) -> bool:
    if geometry.get("type") == "Polygon":
        return _polygon_contains(geometry["coordinates"], x, y)
    if geometry.get("type") == "MultiPolygon":
        return any(
            _polygon_contains(polygon, x, y)
            for polygon in geometry["coordinates"]
        )
    return False


def geocode_address(address: str) -> dict[str, Any]:
    base = (
        "https://geocoding.geo.census.gov/geocoder/geographies/"
        "onelineaddress"
    )
    params = urlencode(
        {
            "address": address,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        }
    )
    raw = _get_json(f"{base}?{params}")
    matches = raw.get("result", {}).get("addressMatches", [])
    if len(matches) != 1:
        raise GeometryFetchError(
            f"GEOCODE_MATCH_COUNT:{address}:{len(matches)}"
        )
    match = matches[0]
    coordinates = match.get("coordinates") or {}
    try:
        longitude = round(float(coordinates["x"]), 7)
        latitude = round(float(coordinates["y"]), 7)
    except (KeyError, TypeError, ValueError) as exc:
        raise GeometryFetchError(f"GEOCODE_COORDINATES_INVALID:{address}") from exc
    return {
        "matched_address": match.get("matchedAddress"),
        "longitude": longitude,
        "latitude": latitude,
        "tiger_line_id": match.get("tigerLine", {}).get("tigerLineId"),
        "side": match.get("tigerLine", {}).get("side"),
    }


def build_control_points(
    layers: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    features_by_division = {
        feature["properties"]["division_id"]: feature
        for collection in layers.values()
        for feature in collection["features"]
    }
    rows = []
    for control in CONTROLS:
        point = geocode_address(control["address"])
        feature = features_by_division.get(control["division_id"])
        if feature is None:
            raise GeometryFetchError(
                f"CONTROL_DIVISION_MISSING:{control['test_id']}"
            )
        if not geometry_contains(
            feature["geometry"],
            point["longitude"],
            point["latitude"],
        ):
            raise GeometryFetchError(
                f"POINT_OUTSIDE_EXPECTED_DIVISION:{control['test_id']}"
            )
        containing = sorted(
            division_id
            for division_id, candidate in features_by_division.items()
            if division_id.startswith(
                "division-co-" + control["jurisdiction"] + "-"
            )
            and geometry_contains(
                candidate["geometry"],
                point["longitude"],
                point["latitude"],
            )
        )
        if containing != [control["division_id"]]:
            raise GeometryFetchError(
                f"POINT_AMBIGUOUS:{control['test_id']}:{containing}"
            )
        rows.append(
            {
                **control,
                **point,
                "coordinate_source": "US_CENSUS_GEOCODER",
                "pip_result": True,
            }
        )
    rows.sort(key=lambda row: row["test_id"])
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "coordinate_source": {
            "system": "U.S. Census Geocoder",
            "endpoint": (
                "https://geocoding.geo.census.gov/geocoder/geographies/"
                "onelineaddress"
            ),
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
        },
        "controls": rows,
    }


def write_snapshot(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    layers = {key: fetch_layer(key) for key in sorted(LAYERS)}
    for key, collection in layers.items():
        output = output_root / LAYERS[key]["output"]
        output.write_bytes(canonical_json_bytes(collection))

    points = build_control_points(layers)
    points_path = output_root / "district_control_points.json"
    points_path.write_bytes(canonical_json_bytes(points))

    files = [
        output_root / LAYERS[key]["output"]
        for key in sorted(LAYERS)
    ] + [points_path]
    manifest = {
        "snapshot_version": SNAPSHOT_VERSION,
        "layers": {
            key: {
                "jurisdiction_id": LAYERS[key]["jurisdiction_id"],
                "service_item_id": LAYERS[key]["service_item_id"],
                "layer_url": LAYERS[key]["layer_url"],
                "feature_count": len(layers[key]["features"]),
                "output": LAYERS[key]["output"],
            }
            for key in sorted(LAYERS)
        },
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(files)
        ],
        "control_count": len(points["controls"]),
        "all_point_in_polygon_pass": all(
            row["pip_result"] is True for row in points["controls"]
        ),
    }
    (output_root / "manifest.json").write_bytes(canonical_json_bytes(manifest))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    write_snapshot(args.output_root)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
