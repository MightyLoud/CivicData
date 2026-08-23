#!/usr/bin/env python3
"""EV-IMP-007 real-network Fircrest geography -> governed Full Essentials proof."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import load_resolver_with_extensions
from consumers.empowered_vote import full_essentials_catalog

CASES = [
    "115 Ramsdell Street, Fircrest, WA 98466",
    "555 Contra Costa Ave, Fircrest, WA 98466",
]


def run() -> None:
    resolver = load_resolver_with_extensions(ROOT, timeout_seconds=30.0)
    results = []
    for address in CASES:
        gps = resolver.resolve(address, observed_on=None)
        if "error" in gps:
            raise AssertionError(f"Civic GPS error for {address}: {gps['error']}")
        payload = gps["payload"]
        jurisdictions = {row["jurisdiction_id"] for row in payload["jurisdictions"]}
        assert "jur-us-wa-fircrest" in jurisdictions, (address, sorted(jurisdictions))
        assert payload["applicable_offices"] == []
        assert payload["officeholders"] == []
        assert payload["action_links"] == []

        model = full_essentials_catalog.build_full_essentials_from_catalog(address, gps, repo_root=ROOT)
        assert model["status"] == "PASS", model
        assert model["package_catalog_entry_id"] == "wa-fircrest-municipal-essentials-v0.2"
        assert model["package_schema_version"] == "0.2"
        assert len(model["applicable_offices"]) == 7
        assert len(model["recent_certified_contests"]) == 7
        candidates = [c for contest in model["recent_certified_contests"] for c in contest["candidates"]]
        assert len(candidates) == 19
        assert sum(c["outcome"] == "WINNER" for c in candidates) == 7
        assert sum(bool(c["is_write_in_bucket"]) for c in candidates) == 7
        assert model["canonical_writes"] == 0
        results.append({
            "address": address,
            "matched_address": payload["input"].get("matched_address"),
            "jurisdictions": sorted(jurisdictions),
            "office_rows": len(model["applicable_offices"]),
            "contests": len(model["recent_certified_contests"]),
            "candidacies": len(candidates),
        })

    print(json.dumps({
        "status": "PASS", "gate": "EV-IMP-007", "third_real_jurisdiction": "Fircrest, WA",
        "live_address_controls": len(results), "results": results,
        "civic_gps_civic_fact_rows": 0, "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
