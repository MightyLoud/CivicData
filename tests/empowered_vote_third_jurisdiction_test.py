#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import full_essentials_catalog, package_catalog, package_source


def gps(jurisdiction_id: str) -> dict:
    return {
        "payload": {
            "input": {"matched_address": "Matched Fircrest Address"},
            "jurisdictions": [{"jurisdiction_id": jurisdiction_id}],
            "district_assignments": [],
            "applicable_offices": [{"office_id": "office:poison"}],
            "action_links": [{"label": "poison"}],
        }
    }


def run() -> None:
    catalog = package_catalog.load_catalog()
    entry = next(row for row in catalog["entries"] if row["entry_id"] == "wa-fircrest-municipal-essentials-v0.2")
    assert entry["profile"] == "municipal_essentials"
    assert entry["civic_gps_jurisdiction_id"] == "jur-us-wa-fircrest"

    package = package_catalog.reconstruct_package(entry, ROOT)
    assert package["schema_version"] == "0.2"
    assert package_source.package_capabilities(package)["full_essentials"] is True
    assert package["jurisdiction"]["jurisdiction_id"] == "jurisdiction-wa-fircrest"
    assert package["jurisdiction"]["geoid"] == "5323970"
    assert len(package["records"]["offices"]) == 7
    assert len(package["records"]["role_terms"]) == 7
    assert len(package["records"]["elections"]) == 2
    assert len(package["records"]["contests"]) == 7
    assert len(package["records"]["candidacies"]) == 19
    assert len(package["qa"]["address_tests"]) == 2
    assert package["qa"]["election_scope_complete"] is True
    assert package["qa"]["unexplained_loss"] == 0

    candidacies = package["records"]["candidacies"]
    named = [row for row in candidacies if row["candidate_kind"] == "PERSON"]
    write_ins = [row for row in candidacies if row["candidate_kind"] == "WRITE_IN_BUCKET"]
    assert len(named) == 12
    assert len(write_ins) == 7
    assert all(row.get("person_id") for row in named)
    assert all(row.get("person_id") is None for row in write_ins)
    assert not any(str(row["candidacy_id"]).startswith("ev-local:") for row in candidacies)

    live = gps("jur-us-wa-fircrest")
    first = full_essentials_catalog.build_full_essentials_from_catalog(
        "115 Ramsdell Street, Fircrest, WA 98466", live, repo_root=ROOT
    )
    second = full_essentials_catalog.build_full_essentials_from_catalog(
        "115 Ramsdell Street, Fircrest, WA 98466", live, repo_root=ROOT
    )
    assert first == second
    assert first["status"] == "PASS"
    assert first["consumer_gate"] == "EV-IMP-007"
    assert first["package_catalog_entry_id"] == entry["entry_id"]
    assert len(first["applicable_offices"]) == 7
    assert len(first["recent_certified_contests"]) == 7
    assert sum(len(row["candidates"]) for row in first["recent_certified_contests"]) == 19
    assert all(row["office_id"] != "office:poison" for row in first["applicable_offices"])
    assert first["canonical_writes"] == 0

    winners = {
        candidate["candidate_name"]
        for contest in first["recent_certified_contests"]
        for candidate in contest["candidates"]
        if candidate["outcome"] == "WINNER"
    }
    assert winners == {
        "David M. Viafore", "Shannon Reynolds", "Brett L. Wittner",
        "Karen Mauer-Smith", "Hunter T. George", "Nikki Bufford", "Joe Barrentine",
    }

    community = full_essentials_catalog.build_full_essentials_from_catalog(
        "555 Contra Costa Ave, Fircrest, WA 98466", live, repo_root=ROOT
    )
    assert community["status"] == "PASS"
    assert len(community["applicable_offices"]) == 7
    assert len(community["recent_certified_contests"]) == 7

    wrong_profile = full_essentials_catalog.build_full_essentials_from_catalog(
        "250 Main Avenue, Akron, CO 80720", gps("jur-us-co-akron"), repo_root=ROOT
    )
    assert wrong_profile["status"] == "FAIL-CLOSED"
    assert wrong_profile["error"] == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"

    print(json.dumps({
        "status": "PASS", "gate": "EV-IMP-007", "third_real_jurisdiction": "Fircrest, WA",
        "package_v0_2": "PASS", "full_essentials": "PASS", "offices": 7,
        "current_holders": 7, "elections": 2, "contests": 7, "candidacies": 19,
        "write_in_buckets": 7, "determinism": "PASS", "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
