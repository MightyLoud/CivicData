#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

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
