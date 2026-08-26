#!/usr/bin/env python3
"""Export governed CO factory snapshot rows into deterministic packages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools import jurisdiction_package as jp
except ModuleNotFoundError:
    import jurisdiction_package as jp

AUTHORIZED_IDS = (
    "jurisdiction-co-akron",
    "jurisdiction-co-alamosa",
    "jurisdiction-co-alma",
    "jurisdiction-co-arvada",
    "jurisdiction-co-aspen",
)
EXCLUDED_IDS = (
    "jurisdiction-co-aguilar",
    "jurisdiction-co-antonito",
    "jurisdiction-co-arriba",
)
TABLE_MAP = {
    "divisions": ("02_Division", "division_id"),
    "bodies": ("03_Body", "body_id"),
    "offices": ("04_Office", "office_id"),
    "people": ("05_Person", "person_id"),
    "role_terms": ("06_RoleTerm", "role_term_id"),
    "leadership_roles": ("07_LeadershipRole", "leadership_id"),
    "identifier_crosswalk": ("10_IdentifierCrosswalk", "crosswalk_id"),
}


def _table(snapshot, name):
    table = snapshot["tables"][name]
    columns = table["columns"]
    output = []
    for item in table["rows"]:
        values = item["values"]
        if list(values) != columns:
            raise ValueError(f"{name} row {item['source_row']} column drift")
        output.append(values)
    return output


def _rows_for(rows, jurisdiction_id):
    return [row for row in rows if row.get("jurisdiction_id") == jurisdiction_id]


def _sort(rows, key):
    return sorted(rows, key=lambda row: (str(row.get(key) or ""), jp.canonical_json(row)))


def _is_open(row):
    return str(row.get("status") or "").upper() not in {"RESOLVED", "CLOSED"}


def _qa_true(checks, check_type):
    matches = [row for row in checks if row.get("check_type") == check_type]
    return bool(matches) and all(row.get("result") is True for row in matches)


def build_package(snapshot, jurisdiction_id):
    jurisdictions = _rows_for(_table(snapshot, "01_Jurisdiction"), jurisdiction_id)
    if len(jurisdictions) != 1:
        raise ValueError(f"{jurisdiction_id}: expected one jurisdiction row, got {len(jurisdictions)}")
    jurisdiction = jurisdictions[0]

    records = {}
    for package_name, (source_name, key) in TABLE_MAP.items():
        records[package_name] = _sort(
            _rows_for(_table(snapshot, source_name), jurisdiction_id),
            key,
        )

    source_evidence = _sort(
        _rows_for(_table(snapshot, "08_SourceEvidence"), jurisdiction_id),
        "source_id",
    )
    source_assertions = _sort(
        _rows_for(_table(snapshot, "09_SourceAssertion"), jurisdiction_id),
        "assertion_id",
    )
    gaps = _rows_for(_table(snapshot, "11_KnownGap"), jurisdiction_id)
    warnings = _sort(
        [row for row in gaps if row.get("blocking") is not True and _is_open(row)],
        "gap_id",
    )
    blocking_gaps = [row for row in gaps if row.get("blocking") is True and _is_open(row)]
    address_tests = _sort(
        _rows_for(_table(snapshot, "12_AddressTest"), jurisdiction_id),
        "test_id",
    )
    checks = _sort(
        _rows_for(_table(snapshot, "13_QA"), jurisdiction_id),
        "qa_id",
    )

    source_counts = {
        **{name: len(rows) for name, rows in records.items()},
        "source_evidence": len(source_evidence),
        "source_assertions": len(source_assertions),
        "warnings": len(warnings),
        "address_tests": len(address_tests),
        "checks": len(checks),
    }
    package = {
        "schema_version": "0.1",
        "jurisdiction": jurisdiction,
        "records": records,
        "provenance": {
            "source_evidence": source_evidence,
            "source_assertions": source_assertions,
        },
        "qa": {
            "parity_ok": _qa_true(checks, "PARITY"),
            "tracker_complete": _qa_true(checks, "REPLICATION"),
            "release_ready": jurisdiction.get("release_ready") is True,
            "qa_fail_count": sum(row.get("result") is not True for row in checks),
            "blocking_gap_count": len(blocking_gaps),
            "address_tests": address_tests,
            "checks": checks,
            "source_counts": source_counts,
        },
        "warnings": warnings,
    }
    errors = jp.validate(package)
    if package["qa"]["tracker_complete"] is not True:
        errors.append("tracker_complete")
    if package["qa"]["release_ready"] is not True:
        errors.append("release_ready")
    if errors:
        raise ValueError(f"{jurisdiction_id}: " + ", ".join(sorted(set(errors))))
    return package


def export_snapshot(snapshot, output_root):
    if snapshot.get("snapshot_contract") != "civicdata.co_factory_snapshot.v0.1":
        raise ValueError("snapshot_contract")
    if snapshot.get("decision_id") != "D-329":
        raise ValueError("decision_id")
    if tuple(snapshot.get("authorized_jurisdiction_ids", [])) != AUTHORIZED_IDS:
        raise ValueError("authorized_jurisdiction_ids")
    if tuple(snapshot.get("excluded_jurisdiction_ids", [])) != EXCLUDED_IDS:
        raise ValueError("excluded_jurisdiction_ids")
    all_rows = [
        item["values"]
        for table in snapshot["tables"].values()
        for item in table["rows"]
    ]
    observed = {row.get("jurisdiction_id") for row in all_rows}
    forbidden = observed & set(EXCLUDED_IDS)
    if forbidden:
        raise ValueError("excluded jurisdiction present: " + ", ".join(sorted(forbidden)))
    unexpected = observed - set(AUTHORIZED_IDS)
    if unexpected:
        raise ValueError("unexpected jurisdiction present: " + ", ".join(sorted(unexpected)))

    results = []
    for jurisdiction_id in AUTHORIZED_IDS:
        package = build_package(snapshot, jurisdiction_id)
        destination = output_root / jurisdiction_id
        jp.build(package, destination)
        verify_errors = jp.verify_package(destination)
        if verify_errors:
            raise ValueError(f"{jurisdiction_id}: " + ", ".join(verify_errors))
        results.append(
            {
                "jurisdiction_id": jurisdiction_id,
                "name": package["jurisdiction"]["name"],
                "output": destination.as_posix(),
                "record_counts": package["qa"]["source_counts"],
                "warning_count": len(package["warnings"]),
                "status": "PASS",
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    results = export_snapshot(snapshot, args.output_root)
    print(json.dumps({"decision_id": "D-329", "status": "PASS", "packages": results}, sort_keys=True))


if __name__ == "__main__":
    main()

