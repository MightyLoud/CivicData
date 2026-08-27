#!/usr/bin/env python3
"""Build and validate deterministic CivicData jurisdiction packages."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
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
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
VALID_STATE_CODES = {
    "AK", "AL", "AR", "AS", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "FM", "GA",
    "GU", "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME",
    "MH", "MI", "MN", "MO", "MP", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM",
    "NV", "NY", "OH", "OK", "OR", "PA", "PR", "PW", "RI", "SC", "SD", "TN", "TX",
    "UM", "UT", "VA", "VI", "VT", "WA", "WI", "WV", "WY",
}
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

ENTITY_FAMILIES = {
    "jurisdiction": ("Jurisdiction", None),
    "divisions": ("Division", "division_id"),
    "bodies": ("Body", "body_id"),
    "offices": ("Office", "office_id"),
    "people": ("Person", "person_id"),
    "role_terms": ("RoleTerm", "role_term_id"),
    "leadership_roles": ("LeadershipRole", "leadership_id"),
    "identifier_crosswalk": ("IdentifierCrosswalk", "crosswalk_id"),
    "elections": ("Election", "election_id"),
    "contests": ("Contest", "contest_id"),
    "candidacies": ("Candidacy", "candidacy_id"),
}


def _json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _type_matches(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _schema_errors(value, schema, path="$", errors=None):
    """Validate the JSON Schema keywords used by the governed package contracts."""
    if errors is None:
        errors = []

    expected_type = schema.get("type")
    if expected_type is not None:
        allowed = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_type_matches(value, item) for item in allowed):
            errors.append(f"schema:{path}:type")
            return errors

    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(f"schema:{path}:const")
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        errors.append(f"schema:{path}:enum")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"schema:{path}.{key}:required")
        for key, item in value.items():
            if key in properties:
                _schema_errors(item, properties[key], f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"schema:{path}.{key}:additionalProperties")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"schema:{path}:minItems")
        if schema.get("uniqueItems") is True:
            tokens = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(tokens) != len(set(tokens)):
                errors.append(f"schema:{path}:uniqueItems")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _schema_errors(item, item_schema, f"{path}[{index}]", errors)

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"schema:{path}:minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"schema:{path}:pattern")
        if schema.get("format") == "date":
            try:
                parsed = dt.date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
            except ValueError:
                errors.append(f"schema:{path}:format:date")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"schema:{path}:minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"schema:{path}:maximum")

    for item in schema.get("allOf", []):
        _schema_errors(value, item, path, errors)
    if "if" in schema:
        condition_errors = []
        _schema_errors(value, schema["if"], path, condition_errors)
        branch = schema.get("then") if not condition_errors else schema.get("else")
        if branch:
            _schema_errors(value, branch, path, errors)
    return errors


def validate_schema_contract(pkg):
    if not isinstance(pkg, dict):
        return ["schema:$:type"]
    version = pkg.get("schema_version")
    if version not in SUPPORTED_VERSIONS:
        return ["schema_version"]
    schema_path = SCHEMA_DIR / f"jurisdiction_package_v{version}.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["schema_contract_unavailable"]
    return sorted(set(_schema_errors(pkg, schema)))


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
    schema_errors = validate_schema_contract(pkg)
    if schema_errors:
        aliases = []
        for error in schema_errors:
            for field in (
                "schema_version",
                "parity_ok",
                "qa_fail_count",
                "blocking_gap_count",
                "election_scope_complete",
                "unexplained_loss",
                "outcome",
                "votes",
                "vote_share",
            ):
                if f".{field}:" in error:
                    aliases.append(field)
        if isinstance(pkg, dict):
            candidacies = (
                pkg.get("records", {}).get("candidacies", [])
                if isinstance(pkg.get("records"), dict)
                else []
            )
            if isinstance(candidacies, list):
                for row in candidacies:
                    if not isinstance(row, dict):
                        continue
                    if row.get("candidate_kind") == "WRITE_IN_BUCKET" and row.get("person_id") is not None:
                        aliases.append("write_in_person_forbidden")
                    if row.get("candidate_kind") == "PERSON" and not row.get("person_id"):
                        aliases.append("candidacy_person_fk")
            warnings = pkg.get("warnings", [])
            if isinstance(warnings, list) and any(
                isinstance(row, dict) and type(row.get("blocking")) is not bool for row in warnings
            ):
                aliases.append("warning_blocking_boolean")
        return sorted(set(schema_errors + aliases))

    errors = []
    version = pkg["schema_version"]

    jurisdiction = pkg.get("jurisdiction", {})
    jurisdiction_id = jurisdiction.get("jurisdiction_id")
    for field in ("jurisdiction_id", "name", "state_abbr", "geoid"):
        if jurisdiction.get(field) in (None, ""):
            errors.append("jurisdiction_" + field)
    if jurisdiction.get("state_abbr") not in VALID_STATE_CODES:
        errors.append("jurisdiction_state_abbr")

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
    if any(row.get("result") is not True for row in qa.get("checks", [])):
        errors.append("qa_checks")

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
    entity_types = {jurisdiction_id: "Jurisdiction"}
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
        family = ENTITY_FAMILIES[table][0]
        entity_types.update({entity_id: family for entity_id in ids})
        for row in rows:
            if row.get("jurisdiction_id") not in (None, jurisdiction_id):
                errors.append("jurisdiction_scope:" + table)

    division_ids = ids_by_table.get("divisions", set())
    body_ids = ids_by_table.get("bodies", set())
    office_ids = ids_by_table.get("offices", set())
    person_ids = ids_by_table.get("people", set())
    role_term_rows = records.get("role_terms", [])

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
    for row in role_term_rows:
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
        if not row.get("person_id") or not row.get("office_id") or not row.get("body_id"):
            errors.append("leadership_required_relationship")
        office = next(
            (item for item in records.get("offices", []) if item.get("office_id") == row.get("office_id")),
            None,
        )
        if office and office.get("body_id") not in (None, row.get("body_id")):
            errors.append("leadership_office_body_relationship")
        if not any(
            term.get("person_id") == row.get("person_id")
            and term.get("office_id") == row.get("office_id")
            and term.get("body_id") in (None, row.get("body_id"))
            for term in role_term_rows
        ):
            errors.append("leadership_role_term_relationship")
    for row in records.get("identifier_crosswalk", []):
        allowed = all_ids | ({jurisdiction_id} if jurisdiction_id else set())
        _add_missing_fk(errors, "crosswalk_entity_fk", row.get("entity_id"), allowed)
        _add_missing_fk(errors, "crosswalk_source_fk", row.get("source_id"), source_ids)
        expected_type = entity_types.get(row.get("entity_id"))
        if expected_type and row.get("entity_type") != expected_type:
            errors.append("crosswalk_entity_family")

    for row in source_rows:
        if row.get("jurisdiction_id") not in (None, jurisdiction_id):
            errors.append("source_scope")
        target_id = row.get("supports_entity_id")
        if target_id not in entity_types:
            errors.append("source_target_fk")
        elif row.get("supports_entity_type") != entity_types[target_id]:
            errors.append("source_entity_family")
    for row in assertion_rows:
        if row.get("jurisdiction_id") not in (None, jurisdiction_id):
            errors.append("assertion_scope")
        _add_missing_fk(errors, "assertion_source_fk", row.get("source_id"), source_ids)
        subject_id = row.get("subject_id")
        if subject_id not in entity_types:
            errors.append("assertion_subject_fk")
        elif row.get("subject_type") != entity_types[subject_id]:
            errors.append("assertion_entity_family")
        if row.get("object_type") == "ID" and row.get("object_value") not in entity_types:
            errors.append("assertion_object_fk")

    for table in BASE_TABLES:
        for row in records.get(table, []):
            for source_id in _tokens(row.get("source_ids")):
                _add_missing_fk(errors, table + "_source_fk", source_id, source_ids)
            _add_missing_fk(errors, table + "_source_fk", row.get("source_id"), source_ids)

    address_ids = [row.get("test_id") for row in address_tests]
    address_inputs = [str(row.get("address_input") or "").strip().casefold() for row in address_tests]
    if any(not value for value in address_ids) or len(address_ids) != len(set(address_ids)):
        errors.append("address_test_id_unique")
    if any(not value for value in address_inputs) or len(address_inputs) != len(set(address_inputs)):
        errors.append("address_test_independence")
    for row in address_tests:
        if row.get("jurisdiction_id") not in (None, jurisdiction_id):
            errors.append("address_scope")
        _add_missing_fk(errors, "address_source_fk", row.get("boundary_source_id"), source_ids)
        _add_missing_fk(errors, "address_actual_division_fk", row.get("actual_division_id"), division_ids)
        _add_missing_fk(errors, "address_expected_division_fk", row.get("expected_division_id"), division_ids)
        for office_id in _tokens(row.get("actual_office_ids")) + _tokens(row.get("expected_office_ids")):
            _add_missing_fk(errors, "address_office_fk", office_id, office_ids)
    for row in qa.get("checks", []):
        _add_missing_fk(errors, "qa_source_fk", row.get("source_id"), source_ids)
    for row in pkg.get("warnings", []):
        if row.get("blocking") is not False:
            errors.append("warning_blocking_boolean")
        if row.get("jurisdiction_id") not in (None, jurisdiction_id):
            errors.append("warning_scope")
        _add_missing_fk(errors, "warning_source_fk", row.get("source_id"), source_ids)
        entity_id = row.get("entity_id")
        if entity_id not in entity_types:
            errors.append("warning_entity_fk")
        elif row.get("entity_type") != entity_types[entity_id]:
            errors.append("warning_entity_family")

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


def _payload_names(pkg):
    return {
        "jurisdiction.json",
        "qa_report.json",
        "source_evidence.csv",
        "source_assertions.csv",
        "address_tests.csv",
        "qa_checks.csv",
        "warnings.csv",
        *{f"{table}.csv" for table in tables_for(pkg)},
    }


def _safe_package_name(name):
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    candidate = Path(name)
    return not candidate.is_absolute() and len(candidate.parts) == 1 and candidate.parts[0] not in {".", ".."}


def _prepare_clean_output(out):
    out = Path(out)
    resolved = out.absolute()
    repository_root = Path(__file__).resolve().parents[1]
    if (
        not out.name
        or resolved == Path("/")
        or resolved == repository_root
        or resolved in repository_root.parents
        or out.is_symlink()
    ):
        raise ValueError("unsafe_output_path")
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():
        if child.is_symlink():
            raise ValueError("output_symlink")
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def build(pkg, out):
    errors = validate(pkg)
    if errors:
        raise ValueError("validation failed: " + ", ".join(errors))
    _prepare_clean_output(out)
    (out / "jurisdiction.json").write_text(canonical_json(pkg), encoding="utf-8")
    for table in tables_for(pkg):
        write_csv(out / (table + ".csv"), pkg["records"].get(table, []))
    write_csv(out / "source_evidence.csv", pkg["provenance"]["source_evidence"])
    write_csv(out / "source_assertions.csv", pkg["provenance"]["source_assertions"])
    write_csv(out / "address_tests.csv", pkg["qa"]["address_tests"])
    write_csv(out / "qa_checks.csv", pkg["qa"]["checks"])
    write_csv(out / "warnings.csv", pkg["warnings"])
    (out / "qa_report.json").write_text(canonical_json(pkg["qa"]), encoding="utf-8")
    files = sorted(out / name for name in _payload_names(pkg))
    manifest = {
        "schema_version": pkg["schema_version"],
        "jurisdiction_id": pkg["jurisdiction"]["jurisdiction_id"],
        "files": [{"path": path.name, "bytes": path.stat().st_size} for path in files],
        "record_counts": pkg["qa"].get("source_counts", {}),
    }
    (out / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    files = sorted([*files, out / "manifest.json"])
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
    )
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")


def verify_package(out):
    errors = []
    out = Path(out)
    if not out.is_dir() or out.is_symlink():
        return ["unsafe_package_directory"]
    pkg_path = out / "jurisdiction.json"
    manifest_path = out / "manifest.json"
    sums_path = out / "SHA256SUMS.txt"
    for path in (pkg_path, manifest_path, sums_path):
        if not path.is_file():
            errors.append("missing_file:" + path.name)
    if errors:
        return errors
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["jurisdiction_json"]
    errors.extend(validate(pkg))
    pkg_dict = pkg if isinstance(pkg, dict) else {}
    pkg_jurisdiction = pkg_dict.get("jurisdiction") if isinstance(pkg_dict.get("jurisdiction"), dict) else {}
    pkg_qa = pkg_dict.get("qa") if isinstance(pkg_dict.get("qa"), dict) else {}
    expected_payload = _payload_names(pkg) if not errors else set()
    expected_inventory = expected_payload | {"manifest.json", "SHA256SUMS.txt"}

    actual_inventory = set()
    for path in out.rglob("*"):
        relative = path.relative_to(out).as_posix()
        if path.is_symlink():
            errors.append("package_symlink:" + relative)
        elif path.is_dir():
            errors.append("nested_directory:" + relative)
        else:
            actual_inventory.add(relative)
            if not _safe_package_name(relative):
                errors.append("unsafe_inventory_path:" + relative)
    if expected_inventory and actual_inventory != expected_inventory:
        errors.append("package_inventory")
        for name in sorted(actual_inventory - expected_inventory):
            errors.append("unexpected_file:" + name)
        for name in sorted(expected_inventory - actual_inventory):
            errors.append("missing_file:" + name)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("manifest_json")
        manifest = {}
    if not isinstance(manifest, dict):
        errors.append("manifest_object")
        manifest = {}
    if manifest.get("jurisdiction_id") != pkg_jurisdiction.get("jurisdiction_id"):
        errors.append("manifest_jurisdiction_id")
    if manifest.get("schema_version") != pkg_dict.get("schema_version"):
        errors.append("manifest_schema_version")
    if manifest.get("record_counts") != pkg_qa.get("source_counts", {}):
        errors.append("manifest_record_counts")
    manifest_entries = manifest.get("files")
    if not isinstance(manifest_entries, list):
        errors.append("manifest_files")
        manifest_entries = []
    manifest_names = []
    for entry in manifest_entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes"}:
            errors.append("manifest_entry")
            continue
        name = entry.get("path")
        if not _safe_package_name(name):
            errors.append("manifest_unsafe_path")
            continue
        manifest_names.append(name)
        path = out / name
        if not path.is_file() or path.is_symlink():
            errors.append("manifest_missing:" + name)
        elif not isinstance(entry.get("bytes"), int) or isinstance(entry.get("bytes"), bool):
            errors.append("manifest_bytes_type:" + name)
        elif path.stat().st_size != entry["bytes"]:
            errors.append("manifest_bytes:" + name)
    if len(manifest_names) != len(set(manifest_names)):
        errors.append("manifest_path_unique")
    if expected_payload and set(manifest_names) != expected_payload:
        errors.append("manifest_file_set")

    expected = {}
    try:
        checksum_lines = sums_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        checksum_lines = []
        errors.append("checksum_read")
    duplicate_checksum_name = False
    for line in checksum_lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None:
            errors.append("checksum_line")
            continue
        digest, name = parts
        if not _safe_package_name(name):
            errors.append("checksum_unsafe_path")
            continue
        if name in expected:
            duplicate_checksum_name = True
        expected[name] = digest
    if duplicate_checksum_name:
        errors.append("checksum_target_unique")
    expected_checksum_targets = (
        expected_payload | {"manifest.json"}
        if expected_payload
        else actual_inventory - {"SHA256SUMS.txt"}
    )
    if set(expected) != expected_checksum_targets:
        errors.append("checksum_file_set")
    for name in sorted(expected_checksum_targets):
        path = out / name
        if path.is_file() and not path.is_symlink():
            if expected.get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
                errors.append("checksum:" + name)
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
