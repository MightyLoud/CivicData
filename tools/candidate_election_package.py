#!/usr/bin/env python3
"""Build and validate deterministic CivicData candidate-election packages."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

CONTRACT_VERSION = "candidate-election-0.1"
PACKAGE_TYPE = "candidate_election"
RELEASE_ID = "tx-candidate-election-2026-001"
PUBLICATION_STATUS = "STAGED_NOT_PUBLISHED"
SOURCE_WORKBOOK_ID = "WB-020"
SOURCE_SPREADSHEET_ID = "1xG1J2fliSTOHoohhDGbsCM4OYUJq0ArEFFLlNYWA6D8"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "candidate_election_package_v0.1.schema.json"
)
EXPECTED_PLACE_FPS = (
    "07552",
    "08128",
    "17917",
    "26808",
    "33794",
    "35228",
    "38548",
    "39952",
    "46824",
    "47316",
)
SUPPORTED_ASSERTION_KINDS = {"FIELD", "IDENTITY", "RELATIONSHIP"}
SUPPORTED_TARGET_ENTITIES = {
    "Jurisdiction",
    "Division",
    "Jurisdiction_Division",
    "Election",
    "Office",
    "Office_Division",
    "Contest",
    "Person",
    "Candidacy",
    "ContactPoint",
    "ExternalIdentifier",
}

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
    records = package.get("records", {})
    if not isinstance(records, dict):
        return []
    value = records.get(table)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _provenance_rows(package: dict[str, Any], table: str) -> list[dict[str, Any]]:
    provenance = package.get("provenance", {})
    if not isinstance(provenance, dict):
        return []
    value = provenance.get(table)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


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


def _schema_pointer(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported schema reference: {ref}")
    value: Any = root
    for part in ref[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    if not isinstance(value, dict):
        raise ValueError(f"schema reference is not an object: {ref}")
    return value


def _schema_type_matches(value: Any, schema_type: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(schema_type, False)


def _schema_format_matches(value: str, format_name: str) -> bool:
    try:
        if format_name == "date":
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
                return False
            dt.date.fromisoformat(value)
            return True
        if format_name == "date-time":
            if re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
                r"(?:Z|[+-][0-9]{2}:[0-9]{2})",
                value,
            ) is None:
                return False
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.tzinfo is not None
        if format_name == "uri":
            parsed = urlparse(value)
            return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))
    except ValueError:
        return False
    return True


def _schema_validation_errors(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Validate every JSON Schema keyword used by the v0.1 contract."""
    if "$ref" in schema:
        return _schema_validation_errors(
            value,
            _schema_pointer(root_schema, str(schema["$ref"])),
            root_schema,
            path,
        )

    errors: list[str] = []
    schema_types = schema.get("type")
    if schema_types is not None:
        allowed_types = (
            schema_types if isinstance(schema_types, list) else [schema_types]
        )
        if not any(
            isinstance(schema_type, str)
            and _schema_type_matches(value, schema_type)
            for schema_type in allowed_types
        ):
            return [f"schema:{path}:type"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"schema:{path}:const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"schema:{path}:enum")

    for sub_schema in schema.get("allOf", []):
        errors.extend(_schema_validation_errors(value, sub_schema, root_schema, path))
    if_schema = schema.get("if")
    if isinstance(if_schema, dict):
        condition_matches = not _schema_validation_errors(
            value, if_schema, root_schema, path
        )
        branch = schema.get("then") if condition_matches else schema.get("else")
        if isinstance(branch, dict):
            errors.extend(_schema_validation_errors(value, branch, root_schema, path))

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"schema:{path}.{key}:required")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"schema:{path}.{key}:additionalProperties")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(
                    _schema_validation_errors(
                        value[key], child_schema, root_schema, f"{path}.{key}"
                    )
                )

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"schema:{path}:minItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    _schema_validation_errors(
                        item, item_schema, root_schema, f"{path}[{index}]"
                    )
                )

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"schema:{path}:minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"schema:{path}:pattern")
        format_name = schema.get("format")
        if format_name and not _schema_format_matches(value, format_name):
            errors.append(f"schema:{path}:format")

    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and "minimum" in schema
        and value < schema["minimum"]
    ):
        errors.append(f"schema:{path}:minimum")
    return errors


def validate_schema(package: dict[str, Any]) -> list[str]:
    if not SCHEMA_PATH.exists():
        return ["schema:file_missing"]
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["schema:file_invalid"]
    try:
        return sorted(set(_schema_validation_errors(package, schema, schema)))
    except (KeyError, TypeError, ValueError):
        return ["schema:definition_invalid"]


def validate_package(package: dict[str, Any]) -> list[str]:
    errors: set[str] = set(validate_schema(package))
    if package.get("contract_version") != CONTRACT_VERSION:
        errors.add("contract_version")
    if package.get("package_type") != PACKAGE_TYPE:
        errors.add("package_type")
    if package.get("release_id") != RELEASE_ID:
        errors.add("release_id")
    if package.get("publication_status") != PUBLICATION_STATUS:
        errors.add("publication_status")

    jurisdiction = package.get("jurisdiction", {})
    if not isinstance(jurisdiction, dict):
        jurisdiction = {}
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
    if not isinstance(source_authority, dict):
        source_authority = {}
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
    if _rows(package, "external_identifiers"):
        errors.add("external_identifiers_reserved")

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

    target_ids_by_entity = {
        "Jurisdiction": {str(jurisdiction_id)} if jurisdiction_id else set(),
        "Division": divisions,
        "Jurisdiction_Division": jurisdiction_divisions,
        "Election": elections,
        "Office": offices,
        "Office_Division": office_divisions,
        "Contest": contests,
        "Person": people,
        "Candidacy": candidacies,
        "ContactPoint": contacts,
        "ExternalIdentifier": external_ids,
    }
    evidence_links = _provenance_rows(package, "evidence_links")
    if _duplicate_values(evidence_links, "evidence_link_id"):
        errors.add("duplicate_evidence_link_id")
    for link in evidence_links:
        if link.get("source_evidence_id") not in all_evidence_ids:
            errors.add("evidence_link_source_fk")
        assertion_kind = link.get("assertion_kind")
        if assertion_kind not in SUPPORTED_ASSERTION_KINDS:
            errors.add("evidence_link_assertion_kind")
        target_entity = link.get("target_entity")
        if target_entity not in SUPPORTED_TARGET_ENTITIES:
            errors.add("evidence_link_target_entity")
        elif link.get("target_id") not in target_ids_by_entity[target_entity]:
            errors.add("evidence_link_target_entity_fk")

    reconciliation = package.get("reconciliation", {})
    if not isinstance(reconciliation, dict):
        reconciliation = {}
    source_total = reconciliation.get("source_scope_total")
    if not (
        isinstance(source_total, int)
        and source_total == reconciliation.get("normalized_total")
        and source_total == reconciliation.get("qa_ready_total")
    ):
        errors.add("source_normalized_qa_reconciliation")
    type_counts = reconciliation.get("record_type_counts", {})
    if not isinstance(type_counts, dict):
        type_counts = {}
    expected_types = {"Candidate", "Structure", "Gap", "Retired"}
    if set(type_counts) != expected_types:
        errors.add("record_type_keys")
    elif not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in type_counts.values()
    ) or sum(type_counts.values()) != source_total:
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
    if not isinstance(excluded, list):
        excluded = []
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
    if not isinstance(qa, dict):
        qa = {}
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
    if not out.is_dir() or out.is_symlink():
        return ["output_directory_invalid"]
    try:
        entries = list(out.iterdir())
    except OSError:
        return ["output_directory_invalid"]
    actual = {path.name for path in entries}
    if actual != expected:
        errors.add("output_file_set")
    if any(path.is_symlink() or not path.is_file() for path in entries):
        errors.add("output_entry_type")
    canonical_path = out / "canonical.json"
    manifest_path = out / "manifest.json"
    sums_path = out / "SHA256SUMS.txt"
    if any(
        path.is_symlink() or not path.is_file()
        for path in (canonical_path, manifest_path, sums_path)
    ):
        return sorted(errors | {"missing_core_output"})
    try:
        package = json.loads(canonical_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sorted(errors | {"canonical_invalid"})
    if not isinstance(package, dict):
        return sorted(errors | {"canonical_invalid"})
    errors.update(validate_package(package))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sorted(errors | {"manifest_invalid"})
    if not isinstance(manifest, dict):
        return sorted(errors | {"manifest_invalid"})
    if manifest.get("package_id") != package.get("package_id"):
        errors.add("manifest_package_id")
    if all(
        not (out / name).is_symlink() and (out / name).is_file()
        for name in OUTPUT_FILES
    ):
        try:
            expected_manifest = _manifest(package, out)
        except (KeyError, OSError, TypeError, ValueError):
            errors.add("manifest_rebuild_failed")
            expected_manifest = None
        if expected_manifest is not None and manifest != expected_manifest:
            errors.add("manifest_content")
    manifest_files = manifest.get("files", [])
    if not isinstance(manifest_files, list):
        errors.add("manifest_files")
        manifest_files = []
    for file_row in manifest_files:
        if not isinstance(file_row, dict):
            errors.add("manifest_files")
            continue
        name = file_row.get("path")
        if not isinstance(name, str) or name not in OUTPUT_FILES:
            errors.add("manifest_path")
            continue
        path = out / name
        if path.is_symlink() or not path.is_file():
            errors.add("manifest_missing_file")
            continue
        try:
            if path.stat().st_size != file_row.get("bytes"):
                errors.add("manifest_bytes")
            if sha256_file(path) != file_row.get("sha256"):
                errors.add("manifest_sha256")
        except OSError:
            errors.add("manifest_file_unreadable")
    declared_sums: dict[str, str] = {}
    try:
        checksum_lines = sums_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return sorted(errors | {"checksum_invalid"})
    checksum_targets = expected - {"SHA256SUMS.txt"}
    for line in checksum_lines:
        if "  " not in line:
            errors.add("checksum_format")
            continue
        digest, name = line.split("  ", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not name:
            errors.add("checksum_format")
            continue
        if name in declared_sums:
            errors.add("checksum_duplicate")
            continue
        if name not in checksum_targets:
            errors.add("checksum_path")
            continue
        declared_sums[name] = digest
    if set(declared_sums) != checksum_targets:
        errors.add("checksum_file_set")
    for name, digest in declared_sums.items():
        path = out / name
        if path.is_symlink() or not path.is_file():
            errors.add("checksum_missing_file")
            continue
        try:
            if sha256_file(path) != digest:
                errors.add("checksum_mismatch")
        except OSError:
            errors.add("checksum_unreadable")
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
    generated_at_values = {
        manifest["generated_at"] for manifest, _ in package_manifests
    }
    if len(generated_at_values) != 1:
        raise ValueError("package generated_at values must match")
    return {
        "contract_version": CONTRACT_VERSION,
        "release_id": RELEASE_ID,
        "generated_at": generated_at_values.pop(),
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
    place_fps = [
        str(package.get("jurisdiction", {}).get("source_jurisdiction_key", ""))
        if isinstance(package, dict)
        and isinstance(package.get("jurisdiction", {}), dict)
        else ""
        for package in packages
    ]
    if len(place_fps) != len(set(place_fps)):
        raise ValueError("duplicate bundle place_fp")
    if tuple(sorted(place_fps)) != EXPECTED_PLACE_FPS:
        raise ValueError("bundle package set")
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


def _release_output_files(repo_root: Path) -> dict[Path, Path]:
    tx_root = repo_root / "data" / "normalized" / "tx"
    files: dict[Path, Path] = {}
    for package_root in tx_root.rglob("candidate-election/2026"):
        if package_root.is_symlink() or not package_root.is_dir():
            continue
        for path in package_root.rglob("*"):
            if path.is_file() or path.is_symlink():
                files[path.relative_to(repo_root)] = path
    release_path = tx_root / f"{RELEASE_ID}.manifest.json"
    if release_path.is_file() or release_path.is_symlink():
        files[release_path.relative_to(repo_root)] = release_path
    return files


def verify_release(repo_root: Path) -> list[str]:
    errors: set[str] = set()
    tx_root = repo_root / "data" / "normalized" / "tx"
    release_path = tx_root / f"{RELEASE_ID}.manifest.json"
    if release_path.is_symlink() or not release_path.is_file():
        return ["release_manifest_missing"]
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["release_manifest_invalid"]
    if not isinstance(release, dict):
        return ["release_manifest_invalid"]
    if release.get("contract_version") != CONTRACT_VERSION:
        errors.add("release_contract_version")
    if release.get("release_id") != RELEASE_ID:
        errors.add("release_id")
    if release.get("publication_status") != PUBLICATION_STATUS:
        errors.add("release_publication_status")
    if release.get("state_abbr") != "TX":
        errors.add("release_state_abbr")
    if release.get("source_workbook_id") != SOURCE_WORKBOOK_ID:
        errors.add("release_source_workbook_id")
    if release.get("source_spreadsheet_id") != SOURCE_SPREADSHEET_ID:
        errors.add("release_source_spreadsheet_id")
    release_packages = release.get("packages")
    if not isinstance(release_packages, list):
        errors.add("release_packages")
        release_packages = []
    if release.get("package_count") != len(release_packages):
        errors.add("release_package_count")

    canonical_paths = sorted(
        tx_root.glob("*/candidate-election/2026/canonical.json")
    )
    packages: list[dict[str, Any]] = []
    place_fps: list[str] = []
    for canonical_path in canonical_paths:
        if canonical_path.is_symlink() or not canonical_path.is_file():
            errors.add("release_canonical_entry_type")
            continue
        try:
            package = json.loads(canonical_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.add("release_canonical_invalid")
            continue
        if not isinstance(package, dict):
            errors.add("release_canonical_invalid")
            continue
        jurisdiction = package.get("jurisdiction", {})
        place_fp = (
            str(jurisdiction.get("source_jurisdiction_key", ""))
            if isinstance(jurisdiction, dict)
            else ""
        )
        place_fps.append(place_fp)
        packages.append(package)
        try:
            if canonical_path.parent != repo_root / package_relative_dir(package):
                errors.add(f"{place_fp}:package_path")
        except (KeyError, TypeError, ValueError):
            errors.add(f"{place_fp}:package_path")
        try:
            errors.update(
                f"{place_fp}:{error}"
                for error in verify_built_package(canonical_path.parent)
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            errors.add(f"{place_fp}:package_verify_failed")

    if len(place_fps) != len(set(place_fps)):
        errors.add("release_duplicate_place_fp")
    if tuple(sorted(place_fps)) != EXPECTED_PLACE_FPS:
        errors.add("release_package_set")

    if tuple(sorted(place_fps)) == EXPECTED_PLACE_FPS:
        bundle = {
            "contract_version": CONTRACT_VERSION,
            "release_id": RELEASE_ID,
            "packages": packages,
        }
        try:
            with tempfile.TemporaryDirectory() as temporary:
                expected_root = Path(temporary)
                build_release(bundle, expected_root)
                expected_files = _release_output_files(expected_root)
                actual_files = _release_output_files(repo_root)
                if set(expected_files) != set(actual_files):
                    errors.add("release_output_file_set")
                for relative_path in set(expected_files) & set(actual_files):
                    actual_path = actual_files[relative_path]
                    if actual_path.is_symlink() or not actual_path.is_file():
                        errors.add(f"release_output_entry_type:{relative_path}")
                        continue
                    if expected_files[relative_path].read_bytes() != actual_path.read_bytes():
                        errors.add(f"release_output_mismatch:{relative_path}")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            errors.add("release_rebuild_failed")
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
