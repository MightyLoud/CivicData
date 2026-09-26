#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "district_geometry_extract"
OUT.mkdir(parents=True, exist_ok=True)

ALAMOSA_APP_ID = "debd2347c9b647878a46a98f58a712a4"
ARVADA_LAYER = "https://services1.arcgis.com/YdUP5V6WwzeG8T8r/arcgis/rest/services/CouncilDistricts/FeatureServer/0"


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent":"CivicData-Geometry-Extractor/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def sharing_item(item_id: str) -> dict:
    return get_json(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}?f=json")


def sharing_data(item_id: str) -> dict:
    return get_json(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}/data?f=json")


def find_hex_ids(obj) -> set[str]:
    ids = set()
    if isinstance(obj, dict):
        for v in obj.values():
            ids |= find_hex_ids(v)
    elif isinstance(obj, list):
        for v in obj:
            ids |= find_hex_ids(v)
    elif isinstance(obj, str):
        for m in re.findall(r"\b[0-9a-fA-F]{32}\b", obj):
            ids.add(m.lower())
    return ids


def resolve_alamosa_layer() -> tuple[str, dict]:
    app = sharing_data(ALAMOSA_APP_ID)
    candidates = list(find_hex_ids(app))
    checked = []
    for item_id in candidates:
        try:
            meta = sharing_item(item_id)
        except Exception:
            continue
        checked.append({"id":item_id,"type":meta.get("type"),"title":meta.get("title")})
        if meta.get("type") == "Web Map":
            webmap = sharing_data(item_id)
            for layer in webmap.get("operationalLayers", []):
                url = layer.get("url")
                title = str(layer.get("title") or "")
                if url and "FeatureServer" in url and "ward" in title.lower():
                    return url.rstrip("/"), {
                        "app_id":ALAMOSA_APP_ID,
                        "webmap_id":item_id,
                        "webmap_title":meta.get("title"),
                        "layer_title":title,
                        "checked_items":checked,
                    }
            for layer in webmap.get("operationalLayers", []):
                url = layer.get("url")
                if url and "FeatureServer" in url:
                    try:
                        lm = get_json(url + "?f=json")
                    except Exception:
                        continue
                    fields = [str(f.get("name","")).lower() for f in lm.get("fields",[])]
                    if any("ward" in f for f in fields) and lm.get("geometryType") == "esriGeometryPolygon":
                        return url.rstrip("/"), {
                            "app_id":ALAMOSA_APP_ID,
                            "webmap_id":item_id,
                            "webmap_title":meta.get("title"),
                            "layer_title":layer.get("title"),
                            "checked_items":checked,
                        }
    raise RuntimeError("No Alamosa ward polygon layer found. Checked: " + json.dumps(checked))


def query_geojson(layer_url: str) -> dict:
    params = urllib.parse.urlencode({
        "where":"1=1",
        "outFields":"*",
        "returnGeometry":"true",
        "outSR":"4326",
        "f":"geojson",
    })
    return get_json(layer_url + "/query?" + params)


def summarize(fc: dict) -> dict:
    return {
        "feature_count": len(fc.get("features", [])),
        "properties": [f.get("properties",{}) for f in fc.get("features",[])],
    }


alamosa_url, alamosa_prov = resolve_alamosa_layer()
alamosa = query_geojson(alamosa_url)
arvada = query_geojson(ARVADA_LAYER)

(OUT/"alamosa_raw.geojson").write_text(json.dumps(alamosa, separators=(",",":"), sort_keys=True)+"\n")
(OUT/"arvada_raw.geojson").write_text(json.dumps(arvada, separators=(",",":"), sort_keys=True)+"\n")
report = {
    "alamosa": {
        "layer_url": alamosa_url,
        "provenance": alamosa_prov,
        "summary": summarize(alamosa),
    },
    "arvada": {
        "layer_url": ARVADA_LAYER,
        "summary": summarize(arvada),
    },
}
(OUT/"report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
print("ALAMOSA_LAYER=" + alamosa_url)
print(json.dumps(report, indent=2, sort_keys=True))


CONTROLS = [
    ("alamosa", "division-co-alamosa-ward-1", "500 Cottonwood Dr, Alamosa, CO 81101"),
    ("alamosa", "division-co-alamosa-ward-2", "860 Craft Dr, Alamosa, CO 81101"),
    ("alamosa", "division-co-alamosa-ward-3", "1555 W Sixth St, Alamosa, CO 81101"),
    ("alamosa", "division-co-alamosa-ward-4", "1000 Twentieth St, Alamosa, CO 81101"),
    ("arvada", "division-co-arvada-district-1", "8600 Wadsworth Boulevard, Arvada, CO 80003"),
    ("arvada", "division-co-arvada-district-2", "7770 Pierce St, Arvada, CO 80003"),
    ("arvada", "division-co-arvada-district-3", "12140 W 57th Ave, Arvada, CO 80002"),
    ("arvada", "division-co-arvada-district-4", "6655 Quaker Street, Arvada, CO 80007"),
]


def geocode(address: str) -> tuple[float, float, dict[str, Any]]:
    params = urllib.parse.urlencode({
        "SingleLine": address,
        "f": "json",
        "outFields": "Match_addr,Addr_type",
        "maxLocations": "1",
        "outSR": "4326",
    })
    payload = get_json(
        "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?"
        + params
    )
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("No geocode candidate: " + address)
    top = candidates[0]
    loc = top["location"]
    return float(loc["x"]), float(loc["y"]), {
        "match_addr": top.get("address"),
        "score": top.get("score"),
        "attributes": top.get("attributes"),
    }


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if ((yi > y) != (yj > y)):
            denom = (yj - yi)
            if denom != 0:
                cross = (xj - xi) * (y - yi) / denom + xi
                if x < cross:
                    inside = not inside
        j = i
    return inside


def point_in_geometry(x: float, y: float, geometry: dict[str, Any]) -> bool:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    for polygon in polygons or []:
        if not polygon:
            continue
        if point_in_ring(x, y, polygon[0]):
            if not any(point_in_ring(x, y, hole) for hole in polygon[1:]):
                return True
    return False


def normalize_features(city: str, fc: dict[str, Any], layer_url: str) -> dict[str, Any]:
    features = []
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        if city == "alamosa":
            key = int(props["WARD"])
            division_id = f"division-co-alamosa-ward-{key}"
            kept = {
                "WARD": key,
                "Label": props.get("Label"),
                "RefName": props.get("RefName"),
                "OBJECTID_1": props.get("OBJECTID_1"),
            }
        else:
            key = int(props["COUNCIL_DISTRICT"])
            division_id = f"division-co-arvada-district-{key}"
            kept = {
                "COUNCIL_DISTRICT": key,
                "CNCL_ID": props.get("CNCL_ID"),
                "CNCL": props.get("CNCL"),
                "CDID": props.get("CDID"),
                "OBJECTID": props.get("OBJECTID"),
            }
        kept["division_id"] = division_id
        kept["source_layer_url"] = layer_url
        features.append({
            "type": "Feature",
            "properties": kept,
            "geometry": feature["geometry"],
        })
    features.sort(key=lambda row: row["properties"]["division_id"])
    return {
        "type": "FeatureCollection",
        "name": f"{city}_governed_electoral_divisions",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


alamosa_norm = normalize_features("alamosa", alamosa, alamosa_url)
arvada_norm = normalize_features("arvada", arvada, ARVADA_LAYER)

if len(alamosa_norm["features"]) != 4 or len(arvada_norm["features"]) != 4:
    raise RuntimeError("Expected exactly four local divisions per city")

(OUT/"alamosa_wards.geojson").write_text(
    json.dumps(alamosa_norm, separators=(",",":"), sort_keys=True)+"\n"
)
(OUT/"arvada_council_districts.geojson").write_text(
    json.dumps(arvada_norm, separators=(",",":"), sort_keys=True)+"\n"
)

by_city = {"alamosa": alamosa_norm, "arvada": arvada_norm}
pip_results = []
for city, expected, address in CONTROLS:
    x, y, geo = geocode(address)
    matches = [
        f["properties"]["division_id"]
        for f in by_city[city]["features"]
        if point_in_geometry(x, y, f["geometry"])
    ]
    pip_results.append({
        "city": city,
        "address": address,
        "longitude": x,
        "latitude": y,
        "geocoder": geo,
        "expected_division_id": expected,
        "matched_division_ids": matches,
        "result": matches == [expected],
    })

if not all(row["result"] for row in pip_results):
    raise RuntimeError("PIP control failure: " + json.dumps(pip_results, indent=2))

report["pip_controls"] = pip_results
report["governed_outputs"] = {
    "alamosa": {
        "path": "alamosa_wards.geojson",
        "feature_count": len(alamosa_norm["features"]),
        "division_ids": [f["properties"]["division_id"] for f in alamosa_norm["features"]],
    },
    "arvada": {
        "path": "arvada_council_districts.geojson",
        "feature_count": len(arvada_norm["features"]),
        "division_ids": [f["properties"]["division_id"] for f in arvada_norm["features"]],
    },
}
(OUT/"report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
print("PIP_CONTROLS=8/8")
