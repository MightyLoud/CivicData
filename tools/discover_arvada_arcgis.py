#!/usr/bin/env python3
"""Resolve ArcGIS item references behind Arvada's official Council District map app."""
from __future__ import annotations

import json
import re
import urllib.request

APP_ID = "332a7eba6a4641999d278cfa6ee149f4"
BASE = "https://www.arcgis.com/sharing/rest/content/items"
HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MightyLoud-CivicData-arcgis-discovery/0.1"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def item(item_id: str) -> dict:
    return get_json(f"{BASE}/{item_id}?f=json")


def data(item_id: str) -> dict:
    return get_json(f"{BASE}/{item_id}/data?f=json")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def main() -> None:
    queue = [(APP_ID, 0)]
    seen = set()
    records = []
    while queue:
        item_id, depth = queue.pop(0)
        if item_id in seen or depth > 3:
            continue
        seen.add(item_id)
        meta = item(item_id)
        payload = data(item_id)
        values = list(strings(payload))
        urls = sorted(
            {
                s
                for s in values
                if "arcgis" in s.lower()
                and ("FeatureServer" in s or "MapServer" in s)
            }
        )
        refs = sorted(
            {
                s
                for s in values
                if HEX32.fullmatch(s)
            }
        )
        records.append(
            {
                "item_id": item_id,
                "depth": depth,
                "title": meta.get("title"),
                "type": meta.get("type"),
                "owner": meta.get("owner"),
                "url": meta.get("url"),
                "service_urls": urls,
                "referenced_item_ids": refs,
            }
        )
        for ref in refs:
            if ref not in seen:
                queue.append((ref, depth + 1))
    print(json.dumps(records, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
