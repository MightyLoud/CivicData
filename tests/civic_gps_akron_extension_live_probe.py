#!/usr/bin/env python3
"""EV-IMP-005 real-network Akron geography → governed representation proof."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import load_resolver_with_extensions
from consumers.empowered_vote import representation_catalog

CASES = [
    "250 Main Avenue, Akron, CO 80720",
    "302 Main Avenue, Akron, CO 80720",
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
        assert "jur-us-co-akron" in jurisdictions, (address, sorted(jurisdictions))
        # The Akron extension is routing-only. Civic GPS must not become the civic-fact source.
        assert payload["applicable_offices"] == []
        assert payload["officeholders"] == []
        assert payload["action_links"] == []

        model = representation_catalog.build_representation_from_catalog(
            address,
            gps,
            repo_root=ROOT,
        )
        assert model["status"] == "PASS", model
        assert model["package_catalog_entry_id"] == "co-akron-municipal-representation-v0.1"
        assert model["package_schema_version"] == "0.1"
        assert model["representation_only"] is True
        assert model["full_essentials_supported"] is False
        assert len(model["applicable_offices"]) == 2
        assert model["current_holder_count"] == 7
        assert model["canonical_writes"] == 0
        results.append({
            "address": address,
            "matched_address": payload["input"].get("matched_address"),
            "jurisdictions": sorted(jurisdictions),
            "office_rows": len(model["applicable_offices"]),
            "current_holders": model["current_holder_count"],
        })

    print(json.dumps({
        "status": "PASS",
        "gate": "EV-IMP-005",
        "second_real_jurisdiction": "Akron, CO",
        "live_address_controls": len(results),
        "results": results,
        "civic_gps_civic_fact_rows": 0,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
