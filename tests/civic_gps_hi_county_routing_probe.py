#!/usr/bin/env python3
"""EV-IMP-019 live Census county-GEOID routing proof for four Hawaiʻi packages."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import load_resolver_with_extensions

CASES = [
    ("Hawaii County", "25 Aupuni Street, Hilo, HI 96720", "jur-us-hi-hawaii-county", "div-us-hi-hawaii-county"),
    ("Honolulu County", "530 South King Street, Honolulu, HI 96813", "jur-us-hi-honolulu-county", "div-us-hi-honolulu-county"),
    ("Kauai County", "4444 Rice Street, Lihue, HI 96766", "jur-us-hi-kauai-county", "div-us-hi-kauai-county"),
    ("Maui County", "200 South High Street, Wailuku, HI 96793", "jur-us-hi-maui-county", "div-us-hi-maui-county"),
]
HI_IDS = {row[2] for row in CASES}


def run() -> None:
    extension = json.loads(
        (ROOT / "civic_gps_extensions" / "registry_bundles.v0.1.json").read_text(encoding="utf-8")
    )
    hi_bundles = [
        row
        for row in extension.get("bundles", [])
        if str(row.get("adapter_id", "")).startswith("BASE-HI-")
    ]
    assert len(hi_bundles) == 4, [row.get("adapter_id") for row in hi_bundles]
    assert all(row.get("ev_onboarding_status") == "ROUTING_ONLY" for row in hi_bundles)
    assert all(isinstance((row.get("scope_match") or {}).get("all"), list) for row in hi_bundles)
    assert not any(row.get("adapter_id") == "BASE-HI-KALAWAO-COUNTY" for row in hi_bundles)
    assert not (ROOT / "civic_gps_extensions" / "hi_kalawao_county_release_v0.1.json").exists()

    resolver = load_resolver_with_extensions(ROOT, timeout_seconds=30.0)
    results = []
    for name, address, expected_jurisdiction, expected_division in CASES:
        result = resolver.resolve(address, observed_on=None)
        if "error" in result:
            raise AssertionError(f"{name}: Civic GPS error: {result['error']}")
        payload = result["payload"]
        jurisdictions = {
            str(row.get("jurisdiction_id")) for row in payload.get("jurisdictions", [])
        }
        divisions = {
            str(row.get("division_id")) for row in payload.get("matched_divisions", [])
        }
        assert expected_jurisdiction in jurisdictions, (name, sorted(jurisdictions))
        assert expected_division in divisions, (name, sorted(divisions))
        assert not ((HI_IDS - {expected_jurisdiction}) & jurisdictions), (
            name,
            sorted(jurisdictions),
        )
        results.append(
            {
                "county": name,
                "address": address,
                "matched_address": payload.get("input", {}).get("matched_address"),
                "jurisdiction": expected_jurisdiction,
                "division": expected_division,
            }
        )

    for _, _, jurisdiction_id, _ in CASES:
        file_slug = (
            jurisdiction_id.removeprefix("jur-us-hi-")
            .replace("-county", "_county")
            .replace("-", "_")
        )
        release = json.loads(
            (
                ROOT
                / "civic_gps_extensions"
                / f"hi_{file_slug}_release_v0.1.json"
            ).read_text(encoding="utf-8")
        )
        assert release["payload"]["offices"] == []
        assert release["payload"]["officeholders"] == []

    print(
        json.dumps(
            {
                "gate": "EV-IMP-019",
                "status": "PASS",
                "county_routes": 4,
                "live_address_controls": len(results),
                "kalawao_touched": False,
                "routing_release_offices": 0,
                "routing_release_officeholders": 0,
                "canonical_writes": 0,
                "results": results,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    run()
