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
        "instant_app_item_id": "332a7eba6a4641999d278cfa6ee149f4",
        "service_item_id": None,
        "layer_url": None,
        "number_field": "District",
        "name_field": "NAME",
        "division_template": "division-co-arvada-district-{number}",
        "output": "arvada_council_districts.geojson",
        "expected_numbers": [1, 2, 3, 4],
        "expected_bbox": [-105.3, 39.6, -104.8, 40.0],
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


def _walk_item_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for child in value.values():
            found.update(_walk_item_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_walk_item_ids(child))
    elif isinstance(value, str):
        stripped = value.strip()
        if (
            len(stripped) == 32
            and all(char in "0123456789abcdefABCDEF" for char in stripped)
        ):
            found.add(stripped.lower())
    return found


def _walk_layer_candidates(value: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        url = value.get("url")
        title = value.get("title") or value.get("name")
        item_id = value.get("itemId") or value.get("item_id")
        if isinstance(url, str) and "FeatureServer" in url:
            candidates.append(
                {
                    "url": url.rstrip("/"),
                    "title": str(title or ""),
                    "item_id": str(item_id or ""),
                }
            )
        for child in value.values():
            candidates.extend(_walk_layer_candidates(child))
    elif isinstance(value, list):
        for child in value:
            candidates.extend(_walk_layer_candidates(child))
    return candidates


def _layer_bbox(collection: Mapping[str, Any]) -> list[float]:
    points: list[list[float]] = []

    def collect(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and all(isinstance(item, (int, float)) for item in value[:2])
        ):
            points.append([float(value[0]), float(value[1])])
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for feature in collection.get("features", []):
        if isinstance(feature, Mapping):
            collect((feature.get("geometry") or {}).get("coordinates"))
    if not points:
        raise GeometryFetchError("LAYER_BBOX_EMPTY")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _bbox_within(actual: list[float], expected: list[float]) -> bool:
    return (
        actual[0] >= expected[0]
        and actual[1] >= expected[1]
        and actual[2] <= expected[2]
        and actual[3] <= expected[3]
    )


def discover_arvada_layer() -> tuple[str, str]:
    app_id = LAYERS["arvada"]["instant_app_item_id"]
    base = "https://www.arcgis.com/sharing/rest/content/items"
    app_data = _get_json(f"{base}/{app_id}/data?f=json")
    item_ids = _walk_item_ids(app_data)

    webmaps: list[tuple[str, Mapping[str, Any]]] = []
    for item_id in sorted(item_ids):
        metadata = _get_json(f"{base}/{item_id}?f=json")
        if metadata.get("type") == "Web Map":
            webmaps.append(
                (
                    item_id,
                    _get_json(f"{base}/{item_id}/data?f=json"),
                )
            )

    if not webmaps:
        raise GeometryFetchError("ARVADA_WEBMAP_NOT_FOUND")

    layer_candidates: list[dict[str, Any]] = []
    for _, webmap_data in webmaps:
        layer_candidates.extend(_walk_layer_candidates(webmap_data))

    # Operational layers can also be referenced by itemId only.
    for item_id in sorted(
        {
            candidate["item_id"]
            for candidate in layer_candidates
            if candidate.get("item_id")
        }
        | set().union(*(_walk_item_ids(data) for _, data in webmaps))
    ):
        metadata = _get_json(f"{base}/{item_id}?f=json")
        url = metadata.get("url")
        if isinstance(url, str) and "FeatureServer" in url:
            layer_candidates.append(
                {
                    "url": url.rstrip("/"),
                    "title": str(metadata.get("title") or ""),
                    "item_id": item_id,
                }
            )

    seen: set[str] = set()
    for candidate in layer_candidates:
        title = candidate.get("title", "").lower()
        if "district" not in title and "council" not in title:
            continue
        url = candidate["url"]
        if url in seen:
            continue
        seen.add(url)
        layer_url = url if url.rsplit("/", 1)[-1].isdigit() else url + "/0"
        try:
            query = urlencode(
                {
                    "where": "1=1",
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "f": "geojson",
                }
            )
            collection = _get_json(f"{layer_url}/query?{query}")
            if collection.get("type") != "FeatureCollection":
                continue
            bbox = _layer_bbox(collection)
            if not _bbox_within(bbox, LAYERS["arvada"]["expected_bbox"]):
                continue
            properties = [
                feature.get("properties") or {}
                for feature in collection.get("features", [])
                if isinstance(feature, Mapping)
            ]
            numbers = sorted(
                {
                    int(props["District"])
                    for props in properties
                    if props.get("District") not in (None, "")
                }
            )
            if numbers != [1, 2, 3, 4]:
                continue
            metadata = _get_json(
                f"{url.rsplit('/FeatureServer', 1)[0]}/FeatureServer?f=json"
            )
            return layer_url, str(
                candidate.get("item_id")
                or metadata.get("serviceItemId")
                or ""
            )
        except (GeometryFetchError, KeyError, TypeError, ValueError):
            continue

    raise GeometryFetchError("ARVADA_DISTRICT_LAYER_NOT_FOUND")


def fetch_layer(key: str) -> dict[str, Any]:
    spec = dict(LAYERS[key])
    if key == "arvada":
        layer_url, service_item_id = discover_arvada_layer()
        spec["layer_url"] = layer_url
        spec["service_item_id"] = service_item_id
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
            "instant_app_item_id": spec.get("instant_app_item_id"),
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


def _geometry_rings(geometry: Mapping[str, Any]) -> list[list[list[float]]]:
    if geometry.get("type") == "Polygon":
        return list(geometry["coordinates"])
    if geometry.get("type") == "MultiPolygon":
        return [
            ring
            for polygon in geometry["coordinates"]
            for ring in polygon
        ]
    return []


def geometry_contains(geometry: Mapping[str, Any], x: float, y: float) -> bool:
    # ArcGIS can encode multipart Esri rings as separate GeoJSON polygon parts,
    # including hole rings. Even/odd parity across every ring in the feature is
    # stable regardless of ring ordering or Polygon/MultiPolygon grouping.
    rings = _geometry_rings(geometry)
    return sum(_ring_contains(ring, x, y) for ring in rings) % 2 == 1


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
