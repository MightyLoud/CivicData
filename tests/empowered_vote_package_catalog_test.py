#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import live_civic_gps, package_catalog


def gps(jurisdiction_id: str, adapter_id: str | None = None, district_key: str | None = None) -> dict:
    assignments = []
    if adapter_id is not None:
        assignments.append({"adapter_id": adapter_id, "district_key": district_key})
    return {
        "payload": {
            "input": {"matched_address": "Matched Address"},
            "jurisdictions": [{"jurisdiction_id": jurisdiction_id}],
            "district_assignments": assignments,
            # Poison values must never become package-authoritative civic facts.
            "applicable_offices": [{"office_id": "office:poison"}],
            "action_links": [{"label": "poison"}],
        }
    }


def synthetic_package() -> dict:
    return {
        "schema_version": "0.2",
        "jurisdiction": {
            "jurisdiction_id": "jurisdiction:us/zz/test-city",
            "name": "Test City",
            "state_abbr": "ZZ",
            "geoid": "9999999",
            "division_id": "division:us/zz/test-city",
        },
        "records": {
            "divisions": [
                {"division_id": "division:us/zz/test-city", "name": "Test City"},
                {"division_id": "division:us/zz/test-city/council_district_7", "name": "District 7"},
            ],
            "bodies": [{"body_id": "body:test", "name": "Council"}],
            "offices": [
                {"office_id": "office:test/mayor", "name": "Mayor", "geography_id": "division:us/zz/test-city", "source_id": "src"},
                {"office_id": "office:test/d7", "name": "District 7", "geography_id": "division:us/zz/test-city/council_district_7", "source_id": "src"},
                {"office_id": "office:test/d8", "name": "District 8", "geography_id": "division:us/zz/test-city/council_district_8", "source_id": "src"},
            ],
            "people": [
                {"person_id": "person:test/mayor", "name": "Mayor Person"},
                {"person_id": "person:test/d7", "name": "District Person"},
            ],
            "role_terms": [
                {"role_term_id": "term:mayor", "office_id": "office:test/mayor", "person_id": "person:test/mayor", "source_id": "src", "currentness_status": "CURRENT_VERIFIED"},
                {"role_term_id": "term:d7", "office_id": "office:test/d7", "person_id": "person:test/d7", "source_id": "src", "currentness_status": "CURRENT_VERIFIED"},
            ],
            "leadership_roles": [],
            "identifier_crosswalk": [],
            "elections": [{"election_id": "e:test", "election_date": "2026-01-01", "source_ids": ["src"]}],
            "contests": [{"contest_id": "c:test", "election_id": "e:test", "office_id": "office:test/mayor", "contest_name": "Mayor", "source_ids": ["src"]}],
            "candidacies": [{"candidacy_id": "cand:test", "contest_id": "c:test", "candidate_kind": "PERSON", "source_candidate_id": "source:test", "person_id": "person:test/mayor", "candidate_name": "Mayor Person", "source_id": "src", "outcome": "WINNER"}],
        },
        "provenance": {"source_evidence": [{"source_id": "src", "Title": "Official source"}], "source_assertions": []},
        "qa": {"parity_ok": True, "qa_fail_count": 0, "blocking_gap_count": 0, "address_tests": [{"input": "x", "result": True}, {"input": "y", "result": True}], "checks": [], "election_scope_complete": True, "unexplained_loss": 0},
        "warnings": [],
    }


def run() -> None:
    catalog = package_catalog.load_catalog()
    assert len(catalog["entries"]) == 1
    tacoma_entry = catalog["entries"][0]
    assert tacoma_entry["civic_gps_jurisdiction_id"] == "jur-us-wa-tacoma"

    live = gps("jur-us-wa-tacoma", "DIST-WA-TACOMA-COUNCIL", "2")
    selected = package_catalog.select_entry(catalog, live)
    assert selected["entry_id"] == "wa-tacoma-municipal-essentials-v0.2"
    package = package_catalog.reconstruct_package(selected, ROOT)
    assert package["jurisdiction"]["jurisdiction_id"] == "jurisdiction:us/wa/tacoma"
    model = package_catalog.build_essentials_from_catalog("747 Market Street, Tacoma, WA 98402", live, repo_root=ROOT)
    assert model["status"] == "PASS"
    assert model["consumer_gate"] == "EV-IMP-004"
    assert model["package_catalog_entry_id"] == selected["entry_id"]
    assert len(model["applicable_offices"]) == 6
    assert len(model["recent_certified_contests"]) == 5
    assert sum(len(c["candidates"]) for c in model["recent_certified_contests"]) == 15
    assert all(x["office_id"] != "office:poison" for x in model["applicable_offices"])
    assert model["canonical_writes"] == 0

    unsupported = package_catalog.build_essentials_from_catalog("Denver", gps("jur-us-co-denver"), repo_root=ROOT)
    assert unsupported["status"] == "FAIL-CLOSED"
    assert unsupported["error"] == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"

    duplicate = copy.deepcopy(catalog)
    duplicate["entries"].append({**copy.deepcopy(tacoma_entry), "entry_id": "duplicate"})
    try:
        package_catalog.select_entry(duplicate, live)
    except package_catalog.PackageCatalogError as exc:
        assert exc.code == "PACKAGE_SELECTION_AMBIGUOUS"
    else:
        raise AssertionError("ambiguous catalog selection must fail closed")

    synthetic_entry = {
        "entry_id": "synthetic-test-city",
        "profile": "municipal_essentials",
        "civic_gps_jurisdiction_id": "jur-test-city",
        "package_jurisdiction_id": "jurisdiction:us/zz/test-city",
        "package_schema_version": "0.2",
        "artifact": tacoma_entry["artifact"],
        "district_binding": {
            "adapter_id": "DIST-TEST-CITY",
            "division_template": "division:us/zz/test-city/council_district_{district_key}",
        },
    }
    synthetic_binding = package_catalog.binding_from_entry(synthetic_entry)
    synthetic = live_civic_gps.build_essentials_from_civic_gps_result(
        synthetic_package(), "1 Test Plaza", gps("jur-test-city", "DIST-TEST-CITY", "7"), binding=synthetic_binding
    )
    assert synthetic["status"] == "PASS"
    assert {x["office_id"] for x in synthetic["applicable_offices"]} == {"office:test/mayor", "office:test/d7"}
    assert len(synthetic["recent_certified_contests"]) == 1

    print(json.dumps({
        "status": "PASS",
        "catalog_version": "0.1",
        "real_tacoma_package": "PASS",
        "dynamic_selection": "PASS",
        "synthetic_second_jurisdiction": "PASS",
        "unsupported": "FAIL-CLOSED",
        "ambiguous": "FAIL-CLOSED",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
