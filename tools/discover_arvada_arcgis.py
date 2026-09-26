#!/usr/bin/env python3
"""Resolve the backing ArcGIS feature layer for Arvada's official district map."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

APP_ID = "332a7eba6a4641999d278cfa6ee149f4"
BASE = "https://www.arcgis.com/sharing/rest"


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MightyLoud-CivicData-arcgis-discovery/0.2"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_non_json": raw[:500]}


def main() -> None:
    meta = get_json(f"{BASE}/content/items/{APP_ID}?f=json")
    owner = str(meta.get("owner") or "").strip()
    queries = [
        f'owner:{owner} "Council District"',
        f'owner:{owner} district',
        '"Arvada" "Council District"',
    ]
    searches = []
    for query in queries:
        params = urllib.parse.urlencode({"q": query, "num": 100, "f": "json"})
        payload = get_json(f"{BASE}/search?{params}")
        rows = []
        for item in payload.get("results", []) if isinstance(payload, dict) else []:
            rows.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "type": item.get("type"),
                    "owner": item.get("owner"),
                    "url": item.get("url"),
                    "extent": item.get("extent"),
                    "modified": item.get("modified"),
                    "typeKeywords": item.get("typeKeywords"),
                }
            )
        searches.append({"query": query, "results": rows})

    app_data = get_json(f"{BASE}/content/items/{APP_ID}/data?f=pjson")
    print(
        json.dumps(
            {
                "app": {
                    "id": APP_ID,
                    "title": meta.get("title"),
                    "type": meta.get("type"),
                    "owner": owner,
                    "url": meta.get("url"),
                    "extent": meta.get("extent"),
                    "typeKeywords": meta.get("typeKeywords"),
                },
                "app_data": app_data,
                "searches": searches,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
