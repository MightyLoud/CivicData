#!/usr/bin/env python3
"""Jurisdiction-neutral consumer acceptance test."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical_json", type=Path)
    args = parser.parse_args()

    data = json.loads(args.canonical_json.read_text(encoding="utf-8"))
    jurisdiction = data["jurisdictions"][0]

    ids = {
        "division": {row["division_id"] for row in data["divisions"]},
        "body": {row["body_id"] for row in data["bodies"]},
        "office": {row["office_id"] for row in data["offices"]},
        "person": {row["person_id"] for row in data["people"]},
        "source": {row["source_id"] for row in data["source_evidence"]},
    }
    current = [row for row in data["role_terms"] if row["status"] == "current"]
    current_by_office = Counter(row["office_id"] for row in current)

    checks = {
        "one_jurisdiction": len(data["jurisdictions"]) == 1,
        "canonical_resolution": bool(jurisdiction["jurisdiction_id"]),
        "ocd_resolution": bool(jurisdiction.get("ocd_jurisdiction_id")),
        "all_offices_have_one_current_term": (
            set(current_by_office) == ids["office"]
            and all(count == 1 for count in current_by_office.values())
        ),
        "role_term_relationships": all(
            row["office_id"] in ids["office"]
            and row["person_id"] in ids["person"]
            and row["body_id"] in ids["body"]
            for row in data["role_terms"]
        ),
        "office_relationships": all(
            row["body_id"] in ids["body"]
            and row["represented_division_id"] in ids["division"]
            for row in data["offices"]
        ),
        "evidence_resolves": all(
            source_id in ids["source"]
            for collection in (
                "jurisdictions", "divisions", "bodies", "offices", "people",
                "role_terms", "leadership_roles", "elections", "contests",
                "candidacies", "known_gaps"
            )
            for row in data.get(collection, [])
            for source_id in row.get("source_ids", [])
        ),
        "known_gap_parity": data["known_gap_ids"] == [
            row["gap_id"] for row in data["known_gaps"]
        ],
        "record_count_parity": all(
            data["record_counts"].get(collection) == len(data.get(collection, []))
            for collection in data["record_counts"]
        ),
    }

    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    passed = all(checks.values())
    print(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
