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


def tables_for(pkg):
    return BASE_TABLES + (ELECTION_TABLES if pkg.get("schema_version") == "0.2" else ())


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _id_set(rows, key):
    return {row.get(key) for row in rows if row.get(key)}


def validate(pkg):
    errors = []
    version = pkg.get("schema_version")
    if version not in SUPPORTED_VERSIONS:
        errors.append("schema_version")
        return errors

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

    sources = {
        x.get("source_id")
        for x in pkg.get("provenance", {}).get("source_evidence", [])
        if isinstance(x, dict)
    }
    if not sources:
        errors.append("provenance")
    if None in sources:
        errors.append("source_id")

    ids = set()
    for table in BASE_TABLES:
        for row in records.get(table, []):
            key = next(
                (
                    k
                    for k in row
                    if k.endswith("_id")
                    and k
                    not in {
                        "jurisdiction_id",
                        "body_id",
                        "person_id",
                        "office_id",
                        "represented_division_id",
                    }
                ),
                None,
            )
            if key and row[key] in ids:
                errors.append("duplicate_id:" + str(row[key]))
            if key:
                ids.add(row[key])

    office_ids = _id_set(records.get("offices", []), "office_id") | _id_set(records.get("offices", []), "id")
    person_ids = _id_set(records.get("people", []), "person_id") | _id_set(records.get("people", []), "id")

    for rt in records.get("role_terms", []):
        if not rt.get("person_id") or not rt.get("office_id"):
            errors.append("role_term_fk")

    if version == "0.2":
        if qa.get("election_scope_complete") is not True:
            errors.append("election_scope_complete")
        if qa.get("unexplained_loss") != 0:
            errors.append("unexplained_loss")

        election_ids = _id_set(records.get("elections", []), "election_id")
        contest_ids = _id_set(records.get("contests", []), "contest_id")
        candidacy_ids = _id_set(records.get("candidacies", []), "candidacy_id")
        if len(election_ids) != len(records.get("elections", [])):
            errors.append("election_id_unique")
        if len(contest_ids) != len(records.get("contests", [])):
            errors.append("contest_id_unique")
        if len(candidacy_ids) != len(records.get("candidacies", [])):
            errors.append("candidacy_id_unique")

        for election in records.get("elections", []):
            if not election.get("election_id") or not election.get("election_date"):
                errors.append("election_required_fields")
            source_ids = election.get("source_ids", [])
            if not source_ids or any(src not in sources for src in source_ids):
                errors.append("election_source_fk")

        for contest in records.get("contests", []):
            if contest.get("election_id") not in election_ids:
                errors.append("contest_election_fk")
            if contest.get("office_id") not in office_ids:
                errors.append("contest_office_fk")
            source_ids = contest.get("source_ids", [])
            if not source_ids or any(src not in sources for src in source_ids):
                errors.append("contest_source_fk")

        for candidacy in records.get("candidacies", []):
            if candidacy.get("contest_id") not in contest_ids:
                errors.append("candidacy_contest_fk")
            if candidacy.get("source_id") not in sources:
                errors.append("candidacy_source_fk")
            kind = candidacy.get("candidate_kind")
            if kind == "PERSON":
                if not candidacy.get("person_id") or candidacy.get("person_id") not in person_ids:
                    errors.append("candidacy_person_fk")
            elif kind == "WRITE_IN_BUCKET":
                if candidacy.get("person_id") not in (None, ""):
                    errors.append("write_in_person_forbidden")
            else:
                errors.append("candidate_kind")
            if not candidacy.get("source_candidate_id") or not candidacy.get("candidate_name"):
                errors.append("candidacy_required_fields")

    return sorted(set(errors))


def write_csv(path, rows):
    keys = sorted({k for r in rows for k in r})
    with path.open("w", newline="", encoding="utf-8") as f:
        if not keys:
            f.write("")
            return
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def build(pkg, out):
    errs = validate(pkg)
    if errs:
        raise SystemExit("validation failed: " + ", ".join(errs))
    out.mkdir(parents=True, exist_ok=True)
    (out / "jurisdiction.json").write_text(canonical_json(pkg), encoding="utf-8")
    for table in tables_for(pkg):
        write_csv(out / (table + ".csv"), pkg["records"].get(table, []))
    (out / "qa_report.json").write_text(canonical_json(pkg["qa"]), encoding="utf-8")
    files = sorted(
        p
        for p in out.iterdir()
        if p.is_file() and p.name not in {"manifest.json", "SHA256SUMS.txt"}
    )
    manifest = {
        "schema_version": pkg["schema_version"],
        "jurisdiction_id": pkg["jurisdiction"]["jurisdiction_id"],
        "files": [{"path": p.name, "bytes": p.stat().st_size} for p in files],
    }
    (out / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    files = sorted(p for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    sums = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files
    )
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args()
    pkg = json.loads(a.input.read_text(encoding="utf-8"))
    errs = validate(pkg)
    if errs:
        raise SystemExit("validation failed: " + ", ".join(errs))
    if not a.validate_only:
        build(pkg, a.output)
    print("PASS")


if __name__ == "__main__":
    main()
