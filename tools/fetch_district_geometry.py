#!/usr/bin/env python3
"""Fetch and verify machine-readable district geometry for Alamosa and Arvada.

Designed for network-enabled GitHub Actions. The committed verification path can
later run entirely offline against the pinned artifacts produced here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

LAYERS = {
    "alamosa": {
        "jurisdiction": "Alamosa",
        "layer_url": "https://services2.arcgis.com/kQ9CrbL3URg6t3jo/ArcGIS/rest/services/Wards/FeatureServer/0",
        "district_field": "WARD",
        "expected": ["1", "2", "3", "4"],
        "package": "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
        "test_prefix": "addrtest-co-alamosa-ward-",
        "output": "alamosa_wards.geojson",
    },
    "arvada": {
        "jurisdiction": "Arvada",
        "layer_url": "https://services1.arcgis.com/eQyVgDz2cjhzbzN7/arcgis/rest/services/Council_Districts/FeatureServer/1",
        "district_field": "DISTRICT",
        "fallback_fields": [],
        "expected": ["1", "2", "3", "4"],
        "package": "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
        "test_prefix": "addrtest-co-arvada-district-",
        "output": "arvada_council_districts.geojson",
    },
}

GEOCODER = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"


class GeometryFetchError(RuntimeError):
    pass


def _get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MightyLoud-CivicData-geometry-ingest/0.1"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _district_value(properties: dict, config: dict) -> str:
    value = properties.get(config["district_field"])
    if value in (None, ""):
        for field in config.get("fallback_fields", []):
            value = properties.get(field)
            if value not in (None, ""):
                break
    if value in (None, ""):
        raise GeometryFetchError("DISTRICT_FIELD_MISSING")
    text = str(value).strip()
    if text.lower().startswith("district "):
        text = text.split()[-1]
    return text


def fetch_layer(config: dict) -> dict:
    params = urllib.parse.urlencode(
        {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
    )
    payload = _get_json(config["layer_url"] + "/query?" + params)
    if payload.get("type") != "FeatureCollection":
        raise GeometryFetchError("FEATURE_COLLECTION_REQUIRED")

    normalized = []
    seen = set()
    for feature in payload.get("features", []):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        district = _district_value(properties, config)
        if district not in config["expected"]:
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise GeometryFetchError(f"GEOMETRY_INVALID:{district}")
        if district in seen:
            raise GeometryFetchError(f"DISTRICT_DUPLICATE:{district}")
        seen.add(district)
        normalized.append(
            {
                "type": "Feature",
                "properties": {
                    "district": district,
                    "source_object_id": (
                        properties.get("OBJECTID")
                        or properties.get("FID")
                        or properties.get("objectid")
                        or properties.get("objectid_1")
                    ),
                },
                "geometry": geometry,
            }
        )

    if sorted(seen) != sorted(config["expected"]):
        raise GeometryFetchError(
            "DISTRICT_SET_MISMATCH:"
            + ",".join(sorted(seen))
        )

    normalized.sort(key=lambda row: row["properties"]["district"])
    return {
        "type": "FeatureCollection",
        "name": config["jurisdiction"] + " electoral districts",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": normalized,
    }


def geocode(address: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "SingleLine": address,
            "f": "json",
            "outFields": "Match_addr,Addr_type",
            "maxLocations": 1,
            "forStorage": "false",
        }
    )
    payload = _get_json(GEOCODER + "?" + params)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeometryFetchError("GEOCODE_NO_MATCH:" + address)
    candidate = candidates[0]
    location = candidate.get("location") or {}
    x = location.get("x")
    y = location.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise GeometryFetchError("GEOCODE_LOCATION_INVALID:" + address)
    return {
        "address": address,
        "matched_address": candidate.get("address"),
        "score": candidate.get("score"),
        "longitude": float(x),
        "latitude": float(y),
    }


def _point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_geometry(x: float, y: float, geometry: dict) -> bool:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        polygons = [coords]
    elif gtype == "MultiPolygon":
        polygons = coords
    else:
        return False

    for polygon in polygons or []:
        if not polygon:
            continue
        if not _point_in_ring(x, y, polygon[0]):
            continue
        if any(_point_in_ring(x, y, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def district_for_point(collection: dict, longitude: float, latitude: float) -> str:
    matches = [
        feature["properties"]["district"]
        for feature in collection["features"]
        if point_in_geometry(longitude, latitude, feature["geometry"])
    ]
    if len(matches) != 1:
        raise GeometryFetchError(
            "POINT_DISTRICT_CARDINALITY:" + ",".join(matches)
        )
    return matches[0]


def expected_district_from_control(control: dict, city: str) -> str:
    division = str(control.get("expected_division_id") or "")
    marker = "-ward-" if city == "alamosa" else "-district-"
    if marker not in division:
        raise GeometryFetchError("CONTROL_NOT_LOCAL_DISTRICT:" + division)
    return division.rsplit(marker, 1)[1]


def load_controls(config: dict, city: str) -> list[dict]:
    package = json.loads((ROOT / config["package"]).read_text(encoding="utf-8"))
    controls = [
        row
        for row in package.get("qa", {}).get("address_tests", [])
        if isinstance(row, dict)
        and str(row.get("test_id") or "").startswith(config["test_prefix"])
    ]
    if len(controls) != 4:
        raise GeometryFetchError(f"CONTROL_COUNT_INVALID:{city}:{len(controls)}")
    return sorted(controls, key=lambda row: row["test_id"])


def build(output_dir: Path, *, fail_on_mismatch: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    manifest = {
        "version": "0.1",
        "retrieved_at": retrieved_at,
        "sources": {},
    }
    all_points = []
    verification = {
        "version": "0.1",
        "retrieved_at": retrieved_at,
        "results": [],
    }

    for city, config in LAYERS.items():
        collection = fetch_layer(config)
        geometry_bytes = _canonical_bytes(collection)
        (output_dir / config["output"]).write_bytes(geometry_bytes)

        manifest["sources"][city] = {
            "jurisdiction": config["jurisdiction"],
            "layer_url": config["layer_url"],
            "query": {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": True,
                "outSR": 4326,
                "f": "geojson",
            },
            "district_field": config["district_field"],
            "expected_districts": config["expected"],
            "geojson_sha256": sha256(geometry_bytes).hexdigest(),
            "feature_count": len(collection["features"]),
        }

        for control in load_controls(config, city):
            point = geocode(control["address_input"])
            expected = expected_district_from_control(control, city)
            try:
                actual = district_for_point(
                    collection,
                    point["longitude"],
                    point["latitude"],
                )
                point_error = None
            except GeometryFetchError as exc:
                actual = None
                point_error = str(exc)
            result = {
                "city": city,
                "test_id": control["test_id"],
                "address": control["address_input"],
                "expected_district": expected,
                "actual_district": actual,
                "point_in_polygon_error": point_error,
                "longitude": point["longitude"],
                "latitude": point["latitude"],
                "geocode_match": point["matched_address"],
                "geocode_score": point["score"],
                "result": expected == actual,
            }
            all_points.append(
                {
                    "city": city,
                    "test_id": control["test_id"],
                    **point,
                }
            )
            verification["results"].append(result)
            if not result["result"] and fail_on_mismatch:
                # Persisted below in diagnostic mode; normal mode remains fail-closed.
                raise GeometryFetchError(
                    f"CONTROL_DISTRICT_MISMATCH:{control['test_id']}:{expected}:{actual}:"
                    f"{point['longitude']}:{point['latitude']}:{point['matched_address']}"
                )

    verification["results"].sort(key=lambda row: (row["city"], row["test_id"]))
    all_points.sort(key=lambda row: (row["city"], row["test_id"]))
    verification["passed"] = all(row["result"] for row in verification["results"])
    verification["count"] = len(verification["results"])

    (output_dir / "control_points.json").write_bytes(_canonical_bytes(all_points))
    (output_dir / "verification.json").write_bytes(_canonical_bytes(verification))
    (output_dir / "source_manifest.json").write_bytes(_canonical_bytes(manifest))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Write all artifacts even when one or more controls mismatch",
    )
    args = parser.parse_args()
    build(args.output_dir, fail_on_mismatch=not args.diagnostic)
    print("PASS")
