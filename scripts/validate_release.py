#!/usr/bin/env python3
"""Validate a Civic Reality canonical JSON release."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

COLLECTION_IDS = {
    "jurisdictions": "jurisdiction_id",
    "divisions": "division_id",
    "bodies": "body_id",
    "offices": "office_id",
    "people": "person_id",
    "role_terms": "role_term_id",
    "leadership_roles": "leadership_id",
    "elections": "election_id",
    "contests": "contest_id",
    "candidacies": "candidacy_id",
    "source_evidence": "source_id",
    "source_assertions": "assertion_id",
    "identifier_crosswalks": "crosswalk_id",
    "known_gaps": "gap_id",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_json", type=Path)
    args = parser.parse_args()
    data = json.loads(args.release_json.read_text(encoding="utf-8"))
    errors: list[str] = []

    try:
        import jsonschema
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schema" / "civic_reality_package_v0_1.schema.json")
            .read_text(encoding="utf-8")
        )
        jsonschema.validate(data, schema)
    except ImportError:
        print("WARN  jsonschema unavailable; relationship checks still run")
    except Exception as exc:
        errors.append(f"schema: {exc}")

    ids: dict[str, set[str]] = {}
    for collection, id_field in COLLECTION_IDS.items():
        values = [str(row.get(id_field)) for row in data.get(collection, [])]
        if len(values) != len(set(values)):
            errors.append(f"{collection}: duplicate {id_field}")
        ids[collection] = set(values)

    current = Counter(
        row["office_id"] for row in data.get("role_terms", [])
        if row.get("status") == "current"
    )
    for office_id in ids["offices"]:
        if current[office_id] != 1:
            errors.append(f"{office_id}: expected one current RoleTerm, found {current[office_id]}")

    for row in data.get("role_terms", []):
        if row["office_id"] not in ids["offices"]:
            errors.append(f"{row['role_term_id']}: unknown office")
        if row["person_id"] not in ids["people"]:
            errors.append(f"{row['role_term_id']}: unknown person")
        if row["body_id"] not in ids["bodies"]:
            errors.append(f"{row['role_term_id']}: unknown body")

    if data.get("known_gap_ids") != [row["gap_id"] for row in data.get("known_gaps", [])]:
        errors.append("known_gap_ids does not match known_gaps")

    if errors:
        for error in errors:
            print(f"FAIL  {error}")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
