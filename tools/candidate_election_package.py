#!/usr/bin/env python3
"""Build and validate deterministic CivicData candidate-election packages."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

CONTRACT_VERSION = "candidate-election-0.1"
PACKAGE_TYPE = "candidate_election"
RELEASE_ID = "tx-candidate-election-2026-001"
PUBLICATION_STATUS = "STAGED_NOT_PUBLISHED"
SOURCE_WORKBOOK_ID = "WB-020"
SOURCE_SPREADSHEET_ID = "1xG1J2fliSTOHoohhDGbsCM4OYUJq0ArEFFLlNYWA6D8"

RECORD_TABLES = (
    "divisions",
    "jurisdiction_divisions",
    "elections",
    "offices",
    "office_divisions",
    "contests",
    "people",
    "candidacies",
    "contact_points",
    "external_identifiers",
)
ID_KEYS = {
    "divisions": "division_id",
    "jurisdiction_divisions": "jurisdiction_division_id",
    "elections": "election_id",
    "offices": "office_id",
    "office_divisions": "office_division_id",
    "contests": "contest_id",
    "people": "person_id",
    "candidacies": "candidacy_id",
    "contact_points": "contact_point_id",
    "external_identifiers": "external_identifier_id",
}
PROVENANCE_TABLES = (
    "source_record_refs",
    "source_evidence",
    "context_source_record_refs",
    "context_evidence",
    "evidence_links",
)
RESTRICTED_KEYS = {
    "raw_payload_json",
    "source_notes",
    "notes_raw",
    "candidate_email",
    "candidate_phone",
    "candidate_address",
    "candidate_website",
    "outreach_log",
    "primary_contact_email",
    "primary_contact_phone",
    "secondary_contact_email",
    "secondary_contact_phone",
    "normalized_by",
    "migration_notes",
}
OUTPUT_FILES = {
    "canonical.json": "canonical_authority",
    "candidates.csv": "review_mirror",
    "contests.csv": "review_mirror",
    "sources.csv": "review_mirror",
    "qa_report.json": "qa_report",
    "README.md": "consumer_readme",
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("empty jurisdiction slug")
    return slug


def package_relative_dir(package: dict[str, Any]) -> Path:
    place_fp = package["jurisdiction"]["source_jurisdiction_key"]
    slug = slugify(package["jurisdiction"]["official_name"])
    return Path("data") / "normalized" / "tx" / f"{place_fp}-{slug}" / "candidate-election" / "2026"


def _rows(package: dict[str, Any], table: str) -> list[dict[str, Any]]:
    value = package.get("records", {}).get(table)
    return value if isinstance(value, list) else []


def _provenance_rows(package: dict[str, Any], table: str) -> list[dict[str, Any]]:
    value = package.get("provenance", {}).get(table)
    return value if isinstance(value, list) else []


def _id_set(rows: Iterable[dict[str, Any]], key: str) -> set[str]:
    return {str(row[key]) for row in rows if isinstance(row, dict) and row.get(key)}


def _duplicate_values(rows: Iterable[dict[str, Any]], key: str) -> set[str]:
    values = [str(row[key]) for row in rows if isinstance(row, dict) and row.get(key)]
    return {value for value, count in Counter(values).items() if count > 1}


def _restricted_key_paths(value: Any, prefix: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if str(key).lower() in RESTRICTED_KEYS:
                findings.append(child_path)
            findings.extend(_restricted_key_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_restricted_key_paths(child, f"{prefix}[{index}]"))
    return findings


def validate_package(package: dict[str, Any]) -> list[str]:
    errors: set[str] = set()
    if package.get("contract_version") != CONTRACT_VERSION:
        errors.add("contract_version")
    if package.get("package_type") != PACKAGE_TYPE:
        errors.add("package_type")
    if package.get("release_id") != RELEASE_ID:
        errors.add("release_id")
    if package.get("publication_status") != PUBLICATION_STATUS:
        errors.add("publication_status")

    jurisdiction = package.get("jurisdiction", {})
    place_fp = str(jurisdiction.get("source_jurisdiction_key", ""))
    jurisdiction_id = jurisdiction.get("jurisdiction_id")
    if not re.fullmatch(r"[0-9]{5}", place_fp):
        errors.add("place_fp")
    if jurisdiction.get("state_code") != "TX":
        errors.add("state_code")
    if package.get("package_id") != f"tx-{place_fp}-candidate-election-2026":
        errors.add("package_id")
    if not jurisdiction_id:
        errors.add("jurisdiction_id")

    source_authority = package.get("source_authority", {})
    if source_authority.get("workbook_id") != SOURCE_WORKBOOK_ID:
        errors.add("source_workbook_id")
    if source_authority.get("spreadsheet_id") != SOURCE_SPREADSHEET_ID:
        errors.add("source_spreadsheet_id")

    records = package.get("records", {})
    if not isinstance(records, dict):
        errors.add("records")
        records = {}
    for table in RECORD_TABLES:
        if not isinstance(records.get(table), list):
            errors.add(f"missing_table:{table}")
    provenance = package.get("provenance", {})
    if not isinstance(provenance, dict):
        errors.add("provenance")
        provenance = {}
    for table in PROVENANCE_TABLES:
        if not isinstance(provenance.get(table), list):
            errors.add(f"missing_provenance_table:{table}")

    for table, id_key in ID_KEYS.items():
        duplicates = _duplicate_values(_rows(package, table), id_key)
        if duplicates:
            errors.add(f"duplicate_id:{table}")

    divisions = _id_set(_rows(package, "divisions"), "division_id")
    jurisdiction_divisions = _id_set(
        _rows(package, "jurisdiction_divisions"), "jurisdiction_division_id"
    )
    elections = _id_set(_rows(package, "elections"), "election_id")
    offices = _id_set(_rows(package, "offices"), "office_id")
    office_divisions = _id_set(
        _rows(package, "office_divisions"), "office_division_id"
    )
    contests = _id_set(_rows(package, "contests"), "contest_id")
    people = _id_set(_rows(package, "people"), "person_id")
    candidacies = _id_set(_rows(package, "candidacies"), "candidacy_id")
    contacts = _id_set(_rows(package, "contact_points"), "contact_point_id")
    external_ids = _id_set(
        _rows(package, "external_identifiers"), "external_identifier_id"
    )

    public_source_rows = _provenance_rows(package, "source_record_refs")
    context_source_rows = _provenance_rows(package, "context_source_record_refs")
    public_source_ids = _id_set(public_source_rows, "source_record_id")
    context_source_ids = _id_set(context_source_rows, "source_record_id")
    all_source_ids = public_source_ids | context_source_ids
    if _duplicate_values(public_source_rows + context_source_rows, "source_record_id"):
        errors.add("duplicate_source_record_id")
    for source in public_source_rows:
        if source.get("record_type") not in {"Candidate", "Structure"}:
            errors.add("nonpublic_source_record")
        if source.get("workbook_id") != SOURCE_WORKBOOK_ID:
            errors.add("source_record_workbook")

    scoped_evidence = _provenance_rows(package, "source_evidence")
    context_evidence = _provenance_rows(package, "context_evidence")
    all_evidence = scoped_evidence + context_evidence
    scoped_evidence_ids = _id_set(scoped_evidence, "source_evidence_id")
    context_evidence_ids = _id_set(context_evidence, "source_evidence_id")
    all_evidence_ids = scoped_evidence_ids | context_evidence_ids
    if _duplicate_values(all_evidence, "source_evidence_id"):
        errors.add("duplicate_source_evidence_id")
    if not scoped_evidence:
        errors.add("source_evidence_empty")
    for evidence in scoped_evidence:
        if evidence.get("source_record_id") not in public_source_ids:
            errors.add("source_evidence_source_fk")
        if evidence.get("authority_level") != "OFFICIAL_PRIMARY":
            errors.add("source_evidence_authority")
        if evidence.get("evidence_status") != "ACTIVE":
            errors.add("source_evidence_status")
        if not evidence.get("source_url_normalized"):
            errors.add("source_evidence_url")
    for evidence in context_evidence:
        if evidence.get("source_record_id") not in context_source_ids:
            errors.add("context_evidence_source_fk")
        if evidence.get("evidence_status") != "ACTIVE":
            errors.add("context_evidence_status")

    for row in _rows(package, "jurisdiction_divisions"):
        if row.get("jurisdiction_id") != jurisdiction_id:
            errors.add("jurisdiction_division_jurisdiction_fk")
        if row.get("division_id") not in divisions:
            errors.add("jurisdiction_division_division_fk")
        if row.get("source_evidence_id") not in all_evidence_ids:
            errors.add("jurisdiction_division_evidence_fk")

    for row in _rows(package, "elections"):
        if row.get("administering_jurisdiction_id") != jurisdiction_id:
            errors.add("election_jurisdiction_fk")
        if row.get("source_record_id") not in public_source_ids:
            errors.add("election_source_fk")
        if not row.get("election_date"):
            errors.add("election_date")

    for row in _rows(package, "offices"):
        if row.get("jurisdiction_id") != jurisdiction_id:
            errors.add("office_jurisdiction_fk")
    for row in _rows(package, "office_divisions"):
        if row.get("office_id") not in offices:
            errors.add("office_division_office_fk")
        if row.get("division_id") not in divisions:
            errors.add("office_division_division_fk")
        if row.get("source_evidence_id") not in all_evidence_ids:
            errors.add("office_division_evidence_fk")
    for row in _rows(package, "contests"):
        if row.get("election_id") not in elections:
            errors.add("contest_election_fk")
        if row.get("office_id") not in offices:
            errors.add("contest_office_fk")
    for row in _rows(package, "people"):
        if row.get("provisional_source_record_id") not in public_source_ids:
            errors.add("person_source_fk")
        superseded = row.get("superseded_by_person_id")
        if superseded and superseded not in people:
            errors.add("person_superseded_fk")
    for row in _rows(package, "candidacies"):
        if row.get("person_id") not in people:
            errors.add("candidacy_person_fk")
        if row.get("contest_id") not in contests:
            errors.add("candidacy_contest_fk")
        if row.get("primary_source_record_id") not in public_source_ids:
            errors.add("candidacy_source_fk")
    for row in _rows(package, "contact_points"):
        if row.get("person_id") and row.get("person_id") not in people:
            errors.add("contact_person_fk")
        if row.get("candidacy_id") and row.get("candidacy_id") not in candidacies:
            errors.add("contact_candidacy_fk")
        if row.get("sensitivity") != "PUBLIC":
            errors.add("contact_sensitivity")
        if str(row.get("publication_ok")).upper() != "TRUE":
            errors.add("contact_publication_ok")
        if row.get("contact_status") != "ACTIVE":
            errors.add("contact_status")
        if row.get("source_evidence_id") not in all_evidence_ids:
            errors.add("contact_evidence_fk")

    target_ids = (
        {str(jurisdiction_id)}
        | divisions
        | jurisdiction_divisions
        | elections
        | offices
        | office_divisions
        | contests
        | people
        | candidacies
        | contacts
        | external_ids
    )
    evidence_links = _provenance_rows(package, "evidence_links")
    if _duplicate_values(evidence_links, "evidence_link_id"):
        errors.add("duplicate_evidence_link_id")
    for link in evidence_links:
        if link.get("source_evidence_id") not in all_evidence_ids:
            errors.add("evidence_link_source_fk")
        if link.get("target_id") not in target_ids:
            errors.add("evidence_link_target_fk")

    reconciliation = package.get("reconciliation", {})
    source_total = reconciliation.get("source_scope_total")
    if not (
        isinstance(source_total, int)
        and source_total == reconciliation.get("normalized_total")
        and source_total == reconciliation.get("qa_ready_total")
    ):
        errors.add("source_normalized_qa_reconciliation")
    type_counts = reconciliation.get("record_type_counts", {})
    expected_types = {"Candidate", "Structure", "Gap", "Retired"}
    if set(type_counts) != expected_types:
        errors.add("record_type_keys")
    elif sum(type_counts.values()) != source_total:
        errors.add("record_type_total")
    if type_counts.get("Candidate") != len(candidacies):
        errors.add("candidate_candidacy_reconciliation")
    expected_public_refs = type_counts.get("Candidate", 0) + type_counts.get(
        "Structure", 0
    )
    if expected_public_refs != len(public_source_rows):
        errors.add("public_source_record_reconciliation")
    if reconciliation.get("public_source_record_ref_count") != len(public_source_rows):
        errors.add("public_source_record_count")
    excluded = reconciliation.get("excluded_source_records", [])
    expected_excluded = type_counts.get("Gap", 0) + type_counts.get("Retired", 0)
    if len(excluded) != expected_excluded:
        errors.add("excluded_source_record_count")
    if any(
        row.get("record_type") not in {"Gap", "Retired"}
        or row.get("reason") != "NON_PUBLIC_AUDIT_RECORD"
        for row in excluded
    ):
        errors.add("excluded_source_record_policy")
    if reconciliation.get("canonical_candidacy_total") != len(candidacies):
        errors.add("canonical_candidacy_total")

    qa = package.get("qa", {})
    required_qa = {
        "workflow_status": "9.00 – Complete",
        "complete_eligible": True,
        "parity_ok": True,
        "parity_status": "3.00 – Pass",
        "ready_for_done": True,
        "false_complete": False,
        "release_disposition": "COMPLETE_ROSTER",
        "qa_fail_count": 0,
        "blocking_gap_count": 0,
        "provenance_complete": True,
        "sensitivity_filter_pass": True,
        "deterministic": True,
    }
    for key, expected in required_qa.items():
        if qa.get(key) != expected:
            errors.add(f"qa:{key}")

    if _restricted_key_paths(package):
        errors.add("restricted_fields")
    return sorted(errors)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _candidate_rows(package: dict[str, Any]) -> list[dict[str, Any]]:
    people = {row["person_id"]: row for row in _rows(package, "people")}
    contests = {row["contest_id"]: row for row in _rows(package, "contests")}
    offices = {row["office_id"]: row for row in _rows(package, "offices")}
    elections = {row["election_id"]: row for row in _rows(package, "elections")}
    rows = []
    for candidacy in _rows(package, "candidacies"):
        person = people[candidacy["person_id"]]
        contest = contests[candidacy["contest_id"]]
        office = offices[contest["office_id"]]
        election = elections[contest["election_id"]]
        rows.append(
            {
                "candidacy_id": candidacy["candidacy_id"],
                "person_id": person["person_id"],
                "candidate_full_name": person["person_full_name"],
                "candidacy_status": candidacy["candidacy_status"],
                "incumbent_status": candidacy.get("incumbent_status", ""),
                "contest_id": contest["contest_id"],
                "contest_label": contest["contest_label"],
                "office_id": office["office_id"],
                "office_name": office["office_name"],
                "election_id": election["election_id"],
                "election_date": election["election_date"],
                "primary_source_record_id": candidacy["primary_source_record_id"],
            }
        )
    return sorted(rows, key=lambda row: row["candidacy_id"])


def _contest_rows(package: dict[str, Any]) -> list[dict[str, Any]]:
    offices = {row["office_id"]: row for row in _rows(package, "offices")}
    elections = {row["election_id"]: row for row in _rows(package, "elections")}
    candidate_counts = Counter(
        row["contest_id"] for row in _rows(package, "candidacies")
    )
    rows = []
    for contest in _rows(package, "contests"):
        office = offices[contest["office_id"]]
        election = elections[contest["election_id"]]
        rows.append(
            {
                "contest_id": contest["contest_id"],
                "contest_label": contest["contest_label"],
                "contest_status": contest["contest_status"],
                "expected_seats": contest.get("expected_seats", ""),
                "candidate_count": candidate_counts[contest["contest_id"]],
                "office_id": office["office_id"],
                "office_name": office["office_name"],
                "election_id": election["election_id"],
                "election_date": election["election_date"],
            }
        )
    return sorted(rows, key=lambda row: row["contest_id"])


def _source_rows(package: dict[str, Any]) -> list[dict[str, Any]]:
    source_rows = {
        row["source_record_id"]: row
        for row in _provenance_rows(package, "source_record_refs")
    }
    context_rows = {
        row["source_record_id"]: row
        for row in _provenance_rows(package, "context_source_record_refs")
    }
    rows = []
    for scope, evidence_rows, lookup in (
        ("SCOPED", _provenance_rows(package, "source_evidence"), source_rows),
        ("CONTEXT", _provenance_rows(package, "context_evidence"), context_rows),
    ):
        for evidence in evidence_rows:
            source = lookup[evidence["source_record_id"]]
            rows.append(
                {
                    "provenance_scope": scope,
                    "source_evidence_id": evidence["source_evidence_id"],
                    "source_record_id": source["source_record_id"],
                    "source_native_id": source["source_native_id"],
                    "record_type": source["record_type"],
                    "source_url": evidence["source_url_normalized"],
                    "source_type": evidence["source_type"],
                    "authority_level": evidence["authority_level"],
                    "confidence": evidence["confidence"],
                    "evidence_status": evidence["evidence_status"],
                    "raw_row_sha256": source["raw_row_sha256"],
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["provenance_scope"],
            row["source_record_id"],
            row["source_evidence_id"],
        ),
    )


def _readme(package: dict[str, Any]) -> str:
    jurisdiction = package["jurisdiction"]
    reconciliation = package["reconciliation"]
    return (
        f"# {jurisdiction['official_name']} — 2026 candidate-election package\n\n"
        f"- Contract: `{CONTRACT_VERSION}`\n"
        f"- Place FP: `{jurisdiction['source_jurisdiction_key']}`\n"
        f"- Source authority: `{SOURCE_WORKBOOK_ID}`\n"
        f"- Candidate records: **{len(_rows(package, 'candidacies'))}**\n"
        f"- Governed source scope: **{reconciliation['source_scope_total']}**\n"
        f"- Publication status: `{PUBLICATION_STATUS}`\n\n"
        "The canonical authority is `canonical.json`. CSV files are deterministic "
        "review mirrors. The package excludes raw payloads, raw notes, outreach "
        "metadata, unsupported contact data, and source-document bytes.\n"
    )


def _manifest(package: dict[str, Any], out: Path) -> dict[str, Any]:
    file_rows = []
    for name, role in sorted(OUTPUT_FILES.items()):
        path = out / name
        file_rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "content_role": role,
            }
        )
    records = package["records"]
    provenance = package["provenance"]
    return {
        "contract_version": CONTRACT_VERSION,
        "package_type": PACKAGE_TYPE,
        "package_id": package["package_id"],
        "release_id": package["release_id"],
        "generated_at": package["generated_at"],
        "publication_status": PUBLICATION_STATUS,
        "state_abbr": "TX",
        "place_fp": package["jurisdiction"]["source_jurisdiction_key"],
        "jurisdiction_id": package["jurisdiction"]["jurisdiction_id"],
        "election_ids": sorted(row["election_id"] for row in records["elections"]),
        "election_dates": sorted(
            {row["election_date"] for row in records["elections"]}
        ),
        "source_workbook_id": SOURCE_WORKBOOK_ID,
        "source_spreadsheet_id": SOURCE_SPREADSHEET_ID,
        "entity_counts": {
            table: len(records[table]) for table in RECORD_TABLES
        },
        "provenance_counts": {
            table: len(provenance[table]) for table in PROVENANCE_TABLES
        },
        "reconciliation": package["reconciliation"],
        "warning_ids": sorted(
            warning["warning_id"] for warning in package.get("warnings", [])
        ),
        "qa_summary": package["qa"],
        "parity_ok": True,
        "tracker_complete": True,
        "provenance_complete": True,
        "sensitivity_filter_pass": True,
        "files": file_rows,
    }


def build_package(package: dict[str, Any], out: Path) -> dict[str, Any]:
    errors = validate_package(package)
    if errors:
        raise ValueError("validation failed: " + ", ".join(errors))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "canonical.json").write_text(canonical_json(package), encoding="utf-8")
    _write_csv(
        out / "candidates.csv",
        _candidate_rows(package),
        [
            "candidacy_id",
            "person_id",
            "candidate_full_name",
            "candidacy_status",
            "incumbent_status",
            "contest_id",
            "contest_label",
            "office_id",
            "office_name",
            "election_id",
            "election_date",
            "primary_source_record_id",
        ],
    )
    _write_csv(
        out / "contests.csv",
        _contest_rows(package),
        [
            "contest_id",
            "contest_label",
            "contest_status",
            "expected_seats",
            "candidate_count",
            "office_id",
            "office_name",
            "election_id",
            "election_date",
        ],
    )
    _write_csv(
        out / "sources.csv",
        _source_rows(package),
        [
            "provenance_scope",
            "source_evidence_id",
            "source_record_id",
            "source_native_id",
            "record_type",
            "source_url",
            "source_type",
            "authority_level",
            "confidence",
            "evidence_status",
            "raw_row_sha256",
        ],
    )
    (out / "qa_report.json").write_text(
        canonical_json(
            {
                "package_id": package["package_id"],
                "qa": package["qa"],
                "reconciliation": package["reconciliation"],
                "warnings": package["warnings"],
            }
        ),
        encoding="utf-8",
    )
    (out / "README.md").write_text(_readme(package), encoding="utf-8")
    manifest = _manifest(package, out)
    (out / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    checksum_files = sorted(
        path for path in out.iterdir() if path.name != "SHA256SUMS.txt"
    )
    sums = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in checksum_files
    )
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    return manifest


def verify_built_package(out: Path) -> list[str]:
    errors: set[str] = set()
    expected = set(OUTPUT_FILES) | {"manifest.json", "SHA256SUMS.txt"}
    actual = {path.name for path in out.iterdir() if path.is_file()}
    if actual != expected:
        errors.add("output_file_set")
    canonical_path = out / "canonical.json"
    manifest_path = out / "manifest.json"
    sums_path = out / "SHA256SUMS.txt"
    if not canonical_path.exists() or not manifest_path.exists() or not sums_path.exists():
        return sorted(errors | {"missing_core_output"})
    package = json.loads(canonical_path.read_text(encoding="utf-8"))
    errors.update(validate_package(package))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_id") != package.get("package_id"):
        errors.add("manifest_package_id")
    for file_row in manifest.get("files", []):
        path = out / file_row.get("path", "")
        if not path.exists():
            errors.add("manifest_missing_file")
            continue
        if path.stat().st_size != file_row.get("bytes"):
            errors.add("manifest_bytes")
        if sha256_file(path) != file_row.get("sha256"):
            errors.add("manifest_sha256")
    declared_sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        declared_sums[name] = digest
    checksum_targets = actual - {"SHA256SUMS.txt"}
    if set(declared_sums) != checksum_targets:
        errors.add("checksum_file_set")
    for name, digest in declared_sums.items():
        if sha256_file(out / name) != digest:
            errors.add("checksum_mismatch")
    return sorted(errors)


def _release_manifest(
    bundle: dict[str, Any],
    repo_root: Path,
    package_manifests: list[tuple[dict[str, Any], Path]],
) -> dict[str, Any]:
    package_rows = []
    record_totals: Counter[str] = Counter()
    provenance_totals: Counter[str] = Counter()
    reconciliation_totals: Counter[str] = Counter()
    record_type_totals: Counter[str] = Counter()
    for manifest, package_dir in package_manifests:
        for key, value in manifest["entity_counts"].items():
            record_totals[key] += value
        for key, value in manifest["provenance_counts"].items():
            provenance_totals[key] += value
        reconciliation = manifest["reconciliation"]
        for key in (
            "source_scope_total",
            "normalized_total",
            "qa_ready_total",
            "canonical_candidacy_total",
            "public_source_record_ref_count",
        ):
            reconciliation_totals[key] += reconciliation[key]
        record_type_totals.update(reconciliation["record_type_counts"])
        package_rows.append(
            {
                "package_id": manifest["package_id"],
                "place_fp": manifest["place_fp"],
                "jurisdiction_id": manifest["jurisdiction_id"],
                "path": package_dir.relative_to(repo_root).as_posix(),
                "manifest_sha256": sha256_file(package_dir / "manifest.json"),
                "canonical_sha256": sha256_file(package_dir / "canonical.json"),
                "election_dates": manifest["election_dates"],
                "source_scope_total": reconciliation["source_scope_total"],
                "candidacy_total": reconciliation["canonical_candidacy_total"],
                "publication_status": PUBLICATION_STATUS,
            }
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "release_id": RELEASE_ID,
        "generated_at": bundle["packages"][0]["generated_at"],
        "publication_status": PUBLICATION_STATUS,
        "state_abbr": "TX",
        "source_workbook_id": SOURCE_WORKBOOK_ID,
        "source_spreadsheet_id": SOURCE_SPREADSHEET_ID,
        "package_count": len(package_rows),
        "packages": sorted(package_rows, key=lambda row: row["place_fp"]),
        "entity_totals": dict(sorted(record_totals.items())),
        "provenance_totals": dict(sorted(provenance_totals.items())),
        "reconciliation_totals": {
            **dict(sorted(reconciliation_totals.items())),
            "record_type_counts": dict(sorted(record_type_totals.items())),
        },
        "qa_summary": {
            "package_validation_pass": True,
            "parity_ok": True,
            "tracker_complete": True,
            "provenance_complete": True,
            "sensitivity_filter_pass": True,
            "deterministic": True,
        },
    }


def build_release(bundle: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    if bundle.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("bundle contract_version")
    if bundle.get("release_id") != RELEASE_ID:
        raise ValueError("bundle release_id")
    packages = bundle.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("bundle packages")
    package_manifests = []
    seen_paths: set[Path] = set()
    for package in sorted(
        packages,
        key=lambda row: row["jurisdiction"]["source_jurisdiction_key"],
    ):
        relative_dir = package_relative_dir(package)
        if relative_dir in seen_paths:
            raise ValueError(f"duplicate package path: {relative_dir}")
        seen_paths.add(relative_dir)
        package_dir = repo_root / relative_dir
        manifest = build_package(package, package_dir)
        package_manifests.append((manifest, package_dir))
    release_manifest = _release_manifest(bundle, repo_root, package_manifests)
    release_path = (
        repo_root / "data" / "normalized" / "tx" / f"{RELEASE_ID}.manifest.json"
    )
    release_path.parent.mkdir(parents=True, exist_ok=True)
    release_path.write_text(canonical_json(release_manifest), encoding="utf-8")
    return release_manifest


def verify_release(repo_root: Path) -> list[str]:
    errors: set[str] = set()
    release_path = (
        repo_root / "data" / "normalized" / "tx" / f"{RELEASE_ID}.manifest.json"
    )
    if not release_path.exists():
        return ["release_manifest_missing"]
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if release.get("contract_version") != CONTRACT_VERSION:
        errors.add("release_contract_version")
    if release.get("publication_status") != PUBLICATION_STATUS:
        errors.add("release_publication_status")
    if release.get("package_count") != len(release.get("packages", [])):
        errors.add("release_package_count")
    for package_row in release.get("packages", []):
        package_dir = repo_root / package_row["path"]
        errors.update(
            f"{package_row['place_fp']}:{error}"
            for error in verify_built_package(package_dir)
        )
        if sha256_file(package_dir / "manifest.json") != package_row.get(
            "manifest_sha256"
        ):
            errors.add(f"{package_row['place_fp']}:release_manifest_sha")
        if sha256_file(package_dir / "canonical.json") != package_row.get(
            "canonical_sha256"
        ):
            errors.add(f"{package_row['place_fp']}:release_canonical_sha")
    return sorted(errors)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("canonical", type=Path)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("canonical", type=Path)
    build_parser.add_argument("output", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("output", type=Path)
    release_parser = subparsers.add_parser("build-release")
    release_parser.add_argument("bundle", type=Path)
    release_parser.add_argument("repo_root", type=Path)
    verify_release_parser = subparsers.add_parser("verify-release")
    verify_release_parser.add_argument("repo_root", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    if args.command == "validate":
        errors = validate_package(_load(args.canonical))
    elif args.command == "build":
        build_package(_load(args.canonical), args.output)
    elif args.command == "verify":
        errors = verify_built_package(args.output)
    elif args.command == "build-release":
        build_release(_load(args.bundle), args.repo_root)
        errors = verify_release(args.repo_root)
    elif args.command == "verify-release":
        errors = verify_release(args.repo_root)
    if errors:
        raise SystemExit("FAIL: " + ", ".join(errors))
    print("PASS")


if __name__ == "__main__":
    main()
