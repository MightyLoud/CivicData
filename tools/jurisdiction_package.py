#!/usr/bin/env python3
"""Build and validate deterministic CivicData jurisdiction packages."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

BASE_TABLES = (
    "divisions",
    "bodies",
    "offices",
    "people",
    "role_terms",
    "leadership_roles",
    "identifier_crosswalk",
)
ELECTION_TABLES = ("elections", "contests", "candidacies")
SUPPORTED_VERSIONS = {"0.1", "0.2"}
PRIMARY_KEYS = {
    "divisions": "division_id",
    "bodies": "body_id",
    "offices": "office_id",
    "people": "person_id",
    "role_terms": "role_term_id",
    "leadership_roles": "leadership_id",
    "identifier_crosswalk": "crosswalk_id",
    "elections": "election_id",
    "contests": "contest_id",
    "candidacies": "candidacy_id",
}


def tables_for(pkg):
    return BASE_TABLES + (ELECTION_TABLES if pkg.get("schema_version") == "0.2" else ())


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _id_set(rows, key):
    return {row.get(key) for row in rows if row.get(key)}


def _tokens(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).split(";") if x.strip()]


def _add_missing_fk(errors, label, value, allowed):
    if value not in (None, "") and value not in allowed:
        errors.append(label)
        errors.append(f"{label}:{value}")


def validate(pkg):
    errors = []
    version = pkg.get("schema_version")
    if version not in SUPPORTED_VERSIONS:
        return ["schema_version"]

    jurisdiction = pkg.get("jurisdiction", {})
    jurisdiction_id = jurisdiction.get("jurisdiction_id")
    for field in ("jurisdiction_id", "name", "state_abbr", "geoid"):
        if jurisdiction.get(field) in (None, ""):
            errors.append("jurisdiction_" + field)

    records = pkg.get("records", {})
    for table in tables_for(pkg):
        if not isinstance(records.get(table), list):
            errors.append("missing_table:" + table)

    qa = pkg.get("qa", {})
    if qa.get("parity_ok") is not True:
        errors.append("parity_ok")
    if qa.get("qa_fail_count") != 0:
        errors.append("qa_fail_count")
    if qa.get("blocking_gap_count") != 0:
        errors.append("blocking_gap_count")
    address_tests = qa.get("address_tests", [])
    if len(address_tests) < 2 or any(x.get("result") is not True for x in address_tests):
        errors.append("address_tests")

    source_rows = pkg.get("provenance", {}).get("source_evidence", [])
    assertion_rows = pkg.get("provenance", {}).get("source_assertions", [])
    if not isinstance(source_rows, list) or not source_rows:
        errors.append("provenance")
        source_rows = []
    if not isinstance(assertion_rows, list):
        errors.append("source_assertions")
        assertion_rows = []
    source_ids = _id_set(source_rows, "source_id")
    assertion_ids = _id_set(assertion_rows, "assertion_id")
    if len(source_ids) != len(source_rows):
        errors.append("source_id_unique")
    if len(assertion_ids) != len(assertion_rows):
        errors.append("assertion_id_unique")

    all_ids = set()
    ids_by_table = {}
    for table in tables_for(pkg):
        rows = records.get(table, [])
        key = PRIMARY_KEYS[table]
        ids = _id_set(rows, key)
        ids_by_table[table] = ids
        if len(ids) != len(rows):
            errors.append(key + "_unique")
        overlap = all_ids & ids
        if overlap:
            errors.append("duplicate_id:" + sorted(overlap)[0])
        all_ids |= ids
        for row in rows:
            if row.get("jurisdiction_id") not in (None, jurisdiction_id):
                errors.append("jurisdiction_scope:" + table)

    division_ids = ids_by_table.get("divisions", set())
    body_ids = ids_by_table.get("bodies", set())
    office_ids = ids_by_table.get("offices", set())
    person_ids = ids_by_table.get("people", set())

    for row in records.get("divisions", []):
        _add_missing_fk(errors, "division_parent_fk", row.get("parent_division_id"), division_ids)
        _add_missing_fk(errors, "division_source_fk", row.get("boundary_source_id"), source_ids)
    for row in records.get("bodies", []):
        _add_missing_fk(errors, "body_parent_fk", row.get("parent_body_id"), body_ids)
    for row in records.get("offices", []):
        _add_missing_fk(errors, "office_body_fk", row.get("body_id"), body_ids)
        _add_missing_fk(
            errors,
            "office_division_fk",
            row.get("represented_division_id"),
            division_ids,
        )
    for row in records.get("role_terms", []):
        _add_missing_fk(errors, "role_term_person_fk", row.get("person_id"), person_ids)
        _add_missing_fk(errors, "role_term_office_fk", row.get("office_id"), office_ids)
        _add_missing_fk(errors, "role_term_body_fk", row.get("body_id"), body_ids)
        if not row.get("person_id") or not row.get("office_id"):
            errors.append("role_term_fk")
        for assertion_id in _tokens(row.get("assertion_ids")):
            _add_missing_fk(errors, "role_term_assertion_fk", assertion_id, assertion_ids)
    for row in records.get("leadership_roles", []):
        _add_missing_fk(errors, "leadership_person_fk", row.get("person_id"), person_ids)
        _add_missing_fk(errors, "leadership_office_fk", row.get("office_id"), office_ids)
        _add_missing_fk(errors, "leadership_body_fk", row.get("body_id"), body_ids)
    for row in records.get("identifier_crosswalk", []):
        allowed = all_ids | ({jurisdiction_id} if jurisdiction_id else set())
        _add_missing_fk(errors, "crosswalk_entity_fk", row.get("entity_id"), allowed)
        _add_missing_fk(errors, "crosswalk_source_fk", row.get("source_id"), source_ids)

    for row in source_rows:
        if row.get("jurisdiction_id") not in (None, jurisdiction_id):
            errors.append("source_scope")
    for row in assertion_rows:
        if row.get("jurisdiction_id") not in (None, jurisdiction_id):
            errors.append("assertion_scope")
        _add_missing_fk(errors, "assertion_source_fk", row.get("source_id"), source_ids)

    for table in BASE_TABLES:
        for row in records.get(table, []):
            for source_id in _tokens(row.get("source_ids")):
                _add_missing_fk(errors, table + "_source_fk", source_id, source_ids)
            _add_missing_fk(errors, table + "_source_fk", row.get("source_id"), source_ids)

    for row in address_tests:
        _add_missing_fk(errors, "address_source_fk", row.get("boundary_source_id"), source_ids)
    for row in qa.get("checks", []):
        _add_missing_fk(errors, "qa_source_fk", row.get("source_id"), source_ids)
    for row in pkg.get("warnings", []):
        _add_missing_fk(errors, "warning_source_fk", row.get("source_id"), source_ids)

    expected_counts = qa.get("source_counts")
    if expected_counts is not None:
        actual_counts = {
            **{table: len(records.get(table, [])) for table in tables_for(pkg)},
            "source_evidence": len(source_rows),
            "source_assertions": len(assertion_rows),
            "warnings": len(pkg.get("warnings", [])),
            "address_tests": len(address_tests),
            "checks": len(qa.get("checks", [])),
        }
        if expected_counts != actual_counts:
            errors.append("source_count_reconciliation")

    if version == "0.2":
        if qa.get("election_scope_complete") is not True:
            errors.append("election_scope_complete")
        if qa.get("unexplained_loss") != 0:
            errors.append("unexplained_loss")
        election_ids = ids_by_table.get("elections", set())
        contest_ids = ids_by_table.get("contests", set())
        for election in records.get("elections", []):
            if not election.get("election_id") or not election.get("election_date"):
                errors.append("election_required_fields")
            election_source_ids = election.get("source_ids", [])
            if not election_source_ids:
                errors.append("election_source_fk")
            for source_id in election_source_ids:
                _add_missing_fk(errors, "election_source_fk", source_id, source_ids)
        for contest in records.get("contests", []):
            _add_missing_fk(errors, "contest_election_fk", contest.get("election_id"), election_ids)
            _add_missing_fk(errors, "contest_office_fk", contest.get("office_id"), office_ids)
            contest_source_ids = contest.get("source_ids", [])
            if not contest_source_ids:
                errors.append("contest_source_fk")
            for source_id in contest_source_ids:
                _add_missing_fk(errors, "contest_source_fk", source_id, source_ids)
        for candidacy in records.get("candidacies", []):
            _add_missing_fk(errors, "candidacy_contest_fk", candidacy.get("contest_id"), contest_ids)
            _add_missing_fk(errors, "candidacy_source_fk", candidacy.get("source_id"), source_ids)
            kind = candidacy.get("candidate_kind")
            if kind == "PERSON":
                if not candidacy.get("person_id"):
                    errors.append("candidacy_person_fk")
                _add_missing_fk(errors, "candidacy_person_fk", candidacy.get("person_id"), person_ids)
            elif kind == "WRITE_IN_BUCKET":
                if candidacy.get("person_id") not in (None, ""):
                    errors.append("write_in_person_forbidden")
            else:
                errors.append("candidate_kind")
            if not candidacy.get("source_candidate_id") or not candidacy.get("candidate_name"):
                errors.append("candidacy_required_fields")

    return sorted(set(errors))


def write_csv(path, rows):
    keys = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not keys:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(pkg, out):
    errors = validate(pkg)
    if errors:
        raise ValueError("validation failed: " + ", ".join(errors))
    out.mkdir(parents=True, exist_ok=True)
    (out / "jurisdiction.json").write_text(canonical_json(pkg), encoding="utf-8")
    for table in tables_for(pkg):
        write_csv(out / (table + ".csv"), pkg["records"].get(table, []))
    write_csv(out / "source_evidence.csv", pkg["provenance"]["source_evidence"])
    write_csv(out / "source_assertions.csv", pkg["provenance"]["source_assertions"])
    write_csv(out / "address_tests.csv", pkg["qa"]["address_tests"])
    write_csv(out / "qa_checks.csv", pkg["qa"]["checks"])
    write_csv(out / "warnings.csv", pkg["warnings"])
    (out / "qa_report.json").write_text(canonical_json(pkg["qa"]), encoding="utf-8")
    files = sorted(
        path
        for path in out.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS.txt"}
    )
    manifest = {
        "schema_version": pkg["schema_version"],
        "jurisdiction_id": pkg["jurisdiction"]["jurisdiction_id"],
        "files": [{"path": path.name, "bytes": path.stat().st_size} for path in files],
        "record_counts": pkg["qa"].get("source_counts", {}),
    }
    (out / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    files = sorted(path for path in out.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
    )
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")


def verify_package(out):
    errors = []
    pkg_path = out / "jurisdiction.json"
    manifest_path = out / "manifest.json"
    sums_path = out / "SHA256SUMS.txt"
    for path in (pkg_path, manifest_path, sums_path):
        if not path.is_file():
            errors.append("missing_file:" + path.name)
    if errors:
        return errors
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    errors.extend(validate(pkg))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("jurisdiction_id") != pkg.get("jurisdiction", {}).get("jurisdiction_id"):
        errors.append("manifest_jurisdiction_id")
    for entry in manifest.get("files", []):
        path = out / entry["path"]
        if not path.is_file():
            errors.append("manifest_missing:" + entry["path"])
        elif path.stat().st_size != entry["bytes"]:
            errors.append("manifest_bytes:" + entry["path"])
    expected = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    actual_files = sorted(path for path in out.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    if set(expected) != {path.name for path in actual_files}:
        errors.append("checksum_file_set")
    for path in actual_files:
        if expected.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            errors.append("checksum:" + path.name)
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--verify-package", action="store_true")
    args = parser.parse_args()
    if args.verify_package:
        errors = verify_package(args.output)
        if errors:
            raise SystemExit("verification failed: " + ", ".join(errors))
    else:
        if args.input is None:
            parser.error("input is required unless --verify-package is used")
        pkg = json.loads(args.input.read_text(encoding="utf-8"))
        errors = validate(pkg)
        if errors:
            raise SystemExit("validation failed: " + ", ".join(errors))
        if not args.validate_only:
            build(pkg, args.output)
    print("PASS")


if __name__ == "__main__":
    main()
