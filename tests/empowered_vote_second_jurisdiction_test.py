#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import package_catalog, package_source, representation_catalog


def gps(jurisdiction_id: str) -> dict:
    return {
        "payload": {
            "input": {"matched_address": "250 MAIN AVE, AKRON, CO, 80720"},
            "jurisdictions": [{"jurisdiction_id": jurisdiction_id}],
            "district_assignments": [],
            # Poison civic facts prove only geography is consumed from Civic GPS.
            "applicable_offices": [{"office_id": "office:poison"}],
            "officeholders": [{"person_id": "person:poison"}],
            "action_links": [{"label": "poison"}],
        }
    }


def run() -> None:
    catalog = package_catalog.load_catalog()
    akron = package_catalog.select_entry(catalog, gps("jur-us-co-akron"), profile="municipal_representation")
    assert akron["entry_id"] == "co-akron-municipal-representation-v0.1"
    assert "district_binding" not in akron

    package = package_catalog.reconstruct_package(akron, ROOT)
    assert package["schema_version"] == "0.1"
    assert package["jurisdiction"]["jurisdiction_id"] == "jurisdiction-co-akron"
    assert package_source.package_capabilities(package) == {
        "representation": True,
        "elections": False,
        "full_essentials": False,
        "read_only": True,
    }
    try:
        package_source.require_full_essentials(package)
    except package_source.PackageContractError as exc:
        assert exc.code == "FULL_ESSENTIALS_UNSUPPORTED_BY_PACKAGE_V0_1"
    else:
        raise AssertionError("Akron must remain fail-closed for Full Essentials")

    model = representation_catalog.build_representation_from_catalog(
        "250 Main Avenue, Akron, CO 80720",
        gps("jur-us-co-akron"),
        repo_root=ROOT,
    )
    assert model["status"] == "PASS"
    assert model["consumer_gate"] == "EV-IMP-005"
    assert model["representation_only"] is True
    assert model["full_essentials_supported"] is False
    assert model["package_schema_version"] == "0.1"
    assert model["package_catalog_entry_id"] == akron["entry_id"]
    assert len(model["applicable_offices"]) == 2
    assert model["current_holder_count"] == 7
    assert len(model["source_evidence"]) == 11
    assert len(model["source_assertions"]) == 23
    assert len(model["warnings"]) == 2
    assert model["canonical_writes"] == 0

    by_id = {row["office_id"]: row for row in model["applicable_offices"]}
    assert len(by_id["office-co-akron-mayor"]["holders"]) == 1
    assert len(by_id["office-co-akron-trustee"]["holders"]) == 6
    assert by_id["office-co-akron-trustee"]["seat_capacity"] == "6"
    assert all(row["office_id"] != "office:poison" for row in model["applicable_offices"])
    assert all(holder["person_id"] != "person:poison" for row in model["applicable_offices"] for holder in row["holders"])

    trustees = by_id["office-co-akron-trustee"]["holders"]
    jared = next(row for row in trustees if row["person_id"] == "person-co-akron-jared-jefferson")
    assert jared["leadership_roles"] == ["Mayor Pro Tem"]

    again = representation_catalog.build_representation_from_catalog(
        "250 Main Avenue, Akron, CO 80720", gps("jur-us-co-akron"), repo_root=ROOT
    )
    assert model["deterministic_sha256"] == again["deterministic_sha256"]

    unsupported = representation_catalog.build_representation_from_catalog(
        "Denver", gps("jur-us-co-denver"), repo_root=ROOT
    )
    assert unsupported["status"] == "FAIL-CLOSED"
    assert unsupported["error"] == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"

    print(json.dumps({
        "status": "PASS",
        "second_real_jurisdiction": "Akron, CO",
        "package_schema_version": "0.1",
        "representation": "PASS",
        "office_rows": 2,
        "current_holders": 7,
        "trustee_aggregate_holders": 6,
        "full_essentials": "FAIL-CLOSED",
        "source_evidence": 11,
        "source_assertions": 23,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
