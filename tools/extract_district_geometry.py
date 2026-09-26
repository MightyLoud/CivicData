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
ARVADA_APP_ID = "332a7eba6a4641999d278cfa6ee149f4"


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


def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_dicts(value)


def expand_feature_urls(webmap: dict) -> list[tuple[str, str | None, str | None]]:
    """Return (layer_url, title, source_item_id) from nested Web Map content."""
    found: list[tuple[str, str | None, str | None]] = []
    seen: set[str] = set()

    def add_url(url: str, title: str | None, item_id: str | None):
        clean = url.rstrip("/")
        if clean in seen:
            return
        if clean.endswith("FeatureServer") or clean.endswith("MapServer"):
            try:
                service = get_json(clean + "?f=json")
            except Exception:
                return
            for layer in service.get("layers", []):
                layer_id = layer.get("id")
                if layer_id is not None:
                    layer_url = clean + "/" + str(layer_id)
                    if layer_url not in seen:
                        seen.add(layer_url)
                        found.append(
                            (
                                layer_url,
                                str(layer.get("name") or title or ""),
                                item_id,
                            )
                        )
        elif "FeatureServer/" in clean or "MapServer/" in clean:
            seen.add(clean)
            found.append((clean, title, item_id))

    for node in iter_dicts(webmap):
        url = node.get("url")
        title = str(node.get("title") or node.get("name") or "") or None
        if isinstance(url, str) and (
            "FeatureServer" in url or "MapServer" in url
        ):
            add_url(url, title, None)

        item_id = node.get("itemId") or node.get("itemid")
        if isinstance(item_id, str) and re.fullmatch(r"[0-9a-fA-F]{32}", item_id):
            try:
                meta = sharing_item(item_id)
            except Exception:
                continue
            item_url = meta.get("url")
            if isinstance(item_url, str) and (
                "FeatureServer" in item_url or "MapServer" in item_url
            ):
                add_url(
                    item_url,
                    str(meta.get("title") or title or "") or None,
                    item_id.lower(),
                )
    return found


def resolve_app_layer(
    app_id: str,
    *,
    title_terms: tuple[str, ...],
    field_terms: tuple[str, ...],
) -> tuple[str, dict]:
    app = sharing_data(app_id)
    candidates = list(find_hex_ids(app))
    checked = []
    webmaps = []
    for item_id in candidates:
        try:
            meta = sharing_item(item_id)
        except Exception:
            continue
        checked.append({"id":item_id,"type":meta.get("type"),"title":meta.get("title")})
        if meta.get("type") == "Web Map":
            webmaps.append((item_id, meta, sharing_data(item_id)))

    for item_id, meta, webmap in webmaps:
        expanded = expand_feature_urls(webmap)

        for url, title, source_item_id in expanded:
            if title and any(term in title.lower() for term in title_terms):
                try:
                    lm = get_json(url + "?f=json")
                except Exception:
                    continue
                if lm.get("geometryType") == "esriGeometryPolygon":
                    return url.rstrip("/"), {
                        "app_id": app_id,
                        "webmap_id": item_id,
                        "webmap_title": meta.get("title"),
                        "layer_title": title,
                        "feature_item_id": source_item_id,
                        "checked_items": checked,
                        "expanded_layers": [
                            {"url": u, "title": t, "item_id": i}
                            for u, t, i in expanded
                        ],
                    }

        for url, title, source_item_id in expanded:
            try:
                lm = get_json(url + "?f=json")
            except Exception:
                continue
            fields = [str(field.get("name","")).lower() for field in (lm.get("fields") or [])]
            if (
                lm.get("geometryType") == "esriGeometryPolygon"
                and any(any(term in field for term in field_terms) for field in fields)
            ):
                return url.rstrip("/"), {
                    "app_id": app_id,
                    "webmap_id": item_id,
                    "webmap_title": meta.get("title"),
                    "layer_title": title,
                    "feature_item_id": source_item_id,
                    "checked_items": checked,
                    "expanded_layers": [
                        {"url": u, "title": t, "item_id": i}
                        for u, t, i in expanded
                    ],
                }

    raise RuntimeError(
        "No matching polygon layer found for app "
        + app_id
        + ". Checked: "
        + json.dumps(checked)
        + "; webmaps="
        + json.dumps(
            [
                {
                    "id": item_id,
                    "title": meta.get("title"),
                    "expanded_layers": [
                        {"url": u, "title": t, "item_id": i}
                        for u, t, i in expand_feature_urls(webmap)
                    ],
                }
                for item_id, meta, webmap in webmaps
            ]
        )
    )

def resolve_alamosa_layer() -> tuple[str, dict]:
    return resolve_app_layer(
        ALAMOSA_APP_ID,
        title_terms=("ward",),
        field_terms=("ward",),
    )


def dump_debug_item(item_id: str, name: str) -> None:
    try:
        payload = sharing_data(item_id)
    except Exception as exc:
        payload = {"error": str(exc)}
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def resolve_arvada_layer() -> tuple[str, dict]:
    webmap_id = "7aaa9ec0a1994708991b4506214cf13e"
    dump_debug_item(webmap_id, "arvada_webmap_debug.json")
    dump_debug_item(ARVADA_APP_ID, "arvada_app_debug.json")

    app = sharing_data(ARVADA_APP_ID)
    if webmap_id not in find_hex_ids(app):
        raise RuntimeError(
            "Official Arvada app no longer references expected City Council Districts Web Map"
        )

    meta = sharing_item(webmap_id)
    if meta.get("type") != "Web Map" or meta.get("title") != "City Council Districts":
        raise RuntimeError(
            "Arvada Web Map identity changed: " + json.dumps(meta, sort_keys=True)
        )

    webmap = sharing_data(webmap_id)
    candidates = []
    for node in iter_dicts(webmap.get("operationalLayers", [])):
        title = str(node.get("title") or "").strip()
        url = node.get("url")
        if (
            title == "City Council Districts"
            and isinstance(url, str)
            and ("MapServer/" in url or "FeatureServer/" in url)
        ):
            candidates.append(url.rstrip("/"))

    if len(set(candidates)) != 1:
        raise RuntimeError(
            "Expected exactly one official Arvada City Council Districts layer: "
            + json.dumps(sorted(set(candidates)))
        )

    url = candidates[0]
    layer_meta = get_json(url + "?f=json")
    fields = {
        str(row.get("name") or "")
        for row in (layer_meta.get("fields") or [])
    }
    if (
        layer_meta.get("geometryType") != "esriGeometryPolygon"
        or "DISTRICT" not in fields
    ):
        raise RuntimeError(
            "Official Arvada district layer no longer has expected polygon/DISTRICT schema: "
            + json.dumps(layer_meta, sort_keys=True)
        )

    return url, {
        "app_id": ARVADA_APP_ID,
        "webmap_id": webmap_id,
        "webmap_title": meta.get("title"),
        "layer_title": "City Council Districts",
        "checked_layer_schema": {
            "geometryType": layer_meta.get("geometryType"),
            "fields": sorted(fields),
        },
    }


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
arvada_url, arvada_prov = resolve_arvada_layer()
alamosa = query_geojson(alamosa_url)
arvada = query_geojson(arvada_url)

(OUT/"alamosa_raw.geojson").write_text(json.dumps(alamosa, separators=(",",":"), sort_keys=True)+"\n")
(OUT/"arvada_raw.geojson").write_text(json.dumps(arvada, separators=(",",":"), sort_keys=True)+"\n")
report = {
    "alamosa": {
        "layer_url": alamosa_url,
        "provenance": alamosa_prov,
        "summary": summarize(alamosa),
    },
    "arvada": {
        "layer_url": arvada_url,
        "provenance": arvada_prov,
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
        "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?"
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
            raw_district = str(
                props.get("DISTRICT")
                or props.get("COUNCIL_DISTRICT")
                or ""
            ).strip()
            match = re.search(r"(\\d+)$", raw_district)
            if match is None:
                raise RuntimeError(
                    "Arvada district key missing from feature: "
                    + json.dumps(props, sort_keys=True)
                )
            key = int(match.group(1))
            division_id = f"division-co-arvada-district-{key}"
            kept = {
                "DISTRICT": props.get("DISTRICT"),
                "COUNCIL_MEMBER": props.get("COUNCIL_MEMBER"),
                "WEBSITE": props.get("WEBSITE"),
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
arvada_norm = normalize_features("arvada", arvada, arvada_url)

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
