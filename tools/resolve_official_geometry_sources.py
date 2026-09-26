#!/usr/bin/env python3
"""One-off authoritative ArcGIS source resolver for issue #100.

Queries public ArcGIS REST APIs only. It does not write canonical geometry.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

ARVADA_ITEM = "a6bfdc31a8dd4e128d388032fe5a0bf6"
ARVADA_SERVICE = "https://services1.arcgis.com/eQyVgDz2cjhzbzN7/arcgis/rest/services/Council_Districts/FeatureServer"
ALAMOSA_ITEM = "ef74f0c6ea8f45328b894c30b3120dda"
ALAMOSA_SERVICE = "https://services2.arcgis.com/kQ9CrbL3URg6t3jo/arcgis/rest/services/Wards/FeatureServer"

DISTRICT_ADDRESSES = [
    ("alamosa", "ward:1", "500 Cottonwood Dr, Alamosa, CO 81101"),
    ("alamosa", "ward:2", "860 Craft Dr, Alamosa, CO 81101"),
    ("alamosa", "ward:3", "1555 W Sixth St, Alamosa, CO 81101"),
    ("alamosa", "ward:4", "1000 Twentieth St, Alamosa, CO 81101"),
    ("arvada", "council_district:1", "8600 Wadsworth Boulevard, Arvada, CO 80003"),
    ("arvada", "council_district:2", "7770 Pierce St, Arvada, CO 80003"),
    ("arvada", "council_district:3", "12140 W 57th Ave, Arvada, CO 80002"),
    ("arvada", "council_district:4", "6655 Quaker Street, Arvada, CO 80007"),
]


def get_json(url: str, *, allow_empty: bool = False) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        text = response.read().decode("utf-8")
    if not text.strip():
        if allow_empty:
            return {}
        raise ValueError(f"empty response from {url}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if allow_empty:
            return {"_non_json_prefix": text[:500]}
        raise


def arcgis_item(item_id: str) -> dict:
    base = "https://www.arcgis.com/sharing/rest/content/items/"
    meta = get_json(base + item_id + "?f=json")
    data = get_json(base + item_id + "/data?f=json", allow_empty=True)
    return {"meta": meta, "data": data}


def arcgis_search(query: str, num: int = 100) -> dict:
    params = urllib.parse.urlencode({"q": query, "num": num, "f": "json"})
    return get_json("https://www.arcgis.com/sharing/rest/search?" + params)


def summarize_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "owner": row.get("owner"),
        "type": row.get("type"),
        "url": row.get("url"),
        "access": row.get("access"),
        "snippet": row.get("snippet"),
        "description": row.get("description"),
        "tags": row.get("tags"),
        "modified": row.get("modified"),
        "extent": row.get("extent"),
    }


def collect_urls(value, prefix=""):
    out = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(child, str) and (
                "FeatureServer" in child
                or "MapServer" in child
                or "arcgis/rest/services" in child
            ):
                out.append({"path": path, "url": child})
            out.extend(collect_urls(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            out.extend(collect_urls(child, f"{prefix}[{index}]"))
    return out



def feature_service_summary(name: str, service_url: str) -> None:
    print(f"=== FEATURE SERVICE {name} ===")
    service = get_json(service_url + "?f=json")
    print(json.dumps({
        "serviceDescription": service.get("serviceDescription"),
        "layers": service.get("layers"),
        "tables": service.get("tables"),
        "fullExtent": service.get("fullExtent"),
        "initialExtent": service.get("initialExtent"),
    }, sort_keys=True))
    for layer in service.get("layers", []):
        layer_id = layer.get("id")
        layer_url = f"{service_url}/{layer_id}"
        meta = get_json(layer_url + "?f=json")
        print("LAYER_META=" + json.dumps({
            "service": name,
            "id": layer_id,
            "name": meta.get("name"),
            "geometryType": meta.get("geometryType"),
            "objectIdField": meta.get("objectIdField"),
            "displayField": meta.get("displayField"),
            "fields": [
                {
                    "name": field.get("name"),
                    "alias": field.get("alias"),
                    "type": field.get("type"),
                }
                for field in meta.get("fields", [])
            ],
            "drawingInfo": meta.get("drawingInfo"),
            "extent": meta.get("extent"),
            "editingInfo": meta.get("editingInfo"),
        }, sort_keys=True))
        params = urllib.parse.urlencode({
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
        })
        attrs = get_json(layer_url + "/query?" + params)
        print("LAYER_ATTRIBUTES=" + json.dumps({
            "service": name,
            "id": layer_id,
            "features": [row.get("attributes") for row in attrs.get("features", [])],
        }, sort_keys=True))


def geocode_address(label: str, address: str) -> None:
    params = urllib.parse.urlencode({
        "SingleLine": address,
        "f": "json",
        "outFields": "Match_addr,Addr_type",
        "maxLocations": 3,
    })
    url = (
        "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/"
        "findAddressCandidates?" + params
    )
    payload = get_json(url)
    print("GEOCODE=" + json.dumps({
        "label": label,
        "address": address,
        "candidates": [
            {
                "address": row.get("address"),
                "score": row.get("score"),
                "location": row.get("location"),
                "attributes": row.get("attributes"),
            }
            for row in payload.get("candidates", [])
        ],
    }, sort_keys=True))

def main() -> int:
    print("=== ARVADA OFFICIAL HUB ITEM ===")
    item = arcgis_item(ARVADA_ITEM)
    print(json.dumps(summarize_item(item["meta"]), sort_keys=True))
    print("ARVADA_EMBEDDED_SERVICE_URLS=" + json.dumps(collect_urls(item["data"]), sort_keys=True))

    alamosa = arcgis_item(ALAMOSA_ITEM)
    print("=== ALAMOSA OFFICIAL FEATURE ITEM ===")
    print(json.dumps(summarize_item(alamosa["meta"]), sort_keys=True))

    feature_service_summary("ARVADA", ARVADA_SERVICE)
    feature_service_summary("ALAMOSA", ALAMOSA_SERVICE)

    for city, division, address in DISTRICT_ADDRESSES:
        geocode_address(f"{city}:{division}", address)

    queries = [
        'title:"Council Districts" Arvada',
        'title:"City Council Districts" Arvada',
        '"City of Arvada" "Council Districts"',
        'Arvada Council Districts',
        'Alamosa Wards',
        '"City of Alamosa" Wards',
        'Alamosa "Election Wards"',
    ]
    for query in queries:
        print(f"=== SEARCH {query} ===")
        payload = arcgis_search(query)
        rows = [summarize_item(row) for row in payload.get("results", [])]
        print(json.dumps(rows, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
