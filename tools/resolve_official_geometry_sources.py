#!/usr/bin/env python3
"""One-off authoritative ArcGIS source resolver for issue #100.

Queries public ArcGIS REST APIs only. It does not write canonical geometry.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

ARVADA_ITEM = "a6bfdc31a8dd4e128d388032fe5a0bf6"


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


def main() -> int:
    print("=== ARVADA OFFICIAL HUB ITEM ===")
    item = arcgis_item(ARVADA_ITEM)
    print(json.dumps(summarize_item(item["meta"]), sort_keys=True))
    print("ARVADA_EMBEDDED_SERVICE_URLS=" + json.dumps(collect_urls(item["data"]), sort_keys=True))

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
