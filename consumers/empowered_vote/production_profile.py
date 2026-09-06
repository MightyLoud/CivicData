"""Production-profile contract for the bounded Texas legislative representation slice.

The ordinary Jurisdiction Package contract remains full-jurisdiction only. This
module defines one explicit exception envelope: a hash-bound, exactly two-office
Texas legislative representation profile backed by the existing bounded
acceptance receipt. It does not activate a catalog route or authorize unresolved
Person identities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tools.jurisdiction_package import (
    BASE_TABLES,
    validate_identity_graph,
    validate_public_identity_disposition,
    validate_role_term_sources,
)

PROFILE_ID = "tx_legislative_two_office_v0.1"
RECEIPT_SCHEMA = "texas-bounded-acceptance/0.1"
REQUIRED_FILES = ("jurisdiction.json", "qa_report.json", "manifest.json", "SHA256SUMS.txt")


class ProductionProfileError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def _require(condition: bool, code: str, detail: str | None = None) -> None:
    if not condition:
        raise ProductionProfileError(code, detail)


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha(path.read_bytes())


def _directory_digest(path: Path) -> str:
    h = hashlib.sha256()
    for item in sorted(p for p in path.iterdir() if p.is_file()):
        h.update(item.name.encode("utf-8")); h.update(b"\0")
        h.update(item.read_bytes()); h.update(b"\0")
    return h.hexdigest()


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionProfileError(code, str(exc)) from exc
    _require(isinstance(value, dict), code, "expected JSON object")
    return value


def _parse_sums(text: str) -> dict[str, str]:
    sums: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        _require(len(parts) == 2, "PRODUCTION_PROFILE_CHECKSUM_FILE_INVALID", line)
        digest, name = parts
        name = name.lstrip("*").strip()
        _require(re.fullmatch(r"[a-fA-F0-9]{64}", digest) is not None,
                 "PRODUCTION_PROFILE_CHECKSUM_FILE_INVALID", line)
        sums[name] = digest.lower()
    return sums


def _person_status(person: dict[str, Any]) -> str | None:
    values = [person[key] for key in ("person_status", "identity_resolution_status", "status", "current_status")
              if person.get(key) not in (None, "")]
    normalized = [str(value).strip().upper() for value in values]
    if "PROVISIONAL" in normalized:
        return "PROVISIONAL"
    value = person.get("person_status") or person.get("identity_resolution_status")
    return str(value).strip().upper() if value not in (None, "") else None


def _normalized_bindings(bindings: Any) -> list[dict[str, Any]]:
    _require(isinstance(bindings, list) and len(bindings) == 2, "PRODUCTION_PROFILE_TWO_BINDINGS_REQUIRED")
    normalized = []
    for row in bindings:
        _require(isinstance(row, dict), "PRODUCTION_PROFILE_BINDING_INVALID")
        required = {"binding_id", "package_jurisdiction_id", "civic_gps_jurisdiction_id",
                    "district_adapter_id", "district_division_map"}
        _require(set(row) == required, "PRODUCTION_PROFILE_BINDING_FIELDS_INVALID")
        mapping = row["district_division_map"]
        _require(isinstance(mapping, dict) and len(mapping) == 1
                 and all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in mapping.items()),
                 "PRODUCTION_PROFILE_BINDING_MAP_INVALID")
        normalized.append({key: row[key] for key in sorted(required)})
    normalized.sort(key=lambda row: row["binding_id"])
    _require([row["binding_id"] for row in normalized] == ["tx-house", "tx-senate"],
             "PRODUCTION_PROFILE_BINDING_IDS_INVALID")
    expected = {
        "tx-house": ("DIST-TX-HOUSE-H2316", "49"),
        "tx-senate": ("DIST-TX-SENATE-S2168", "14"),
    }
    for row in normalized:
        adapter, district = expected[row["binding_id"]]
        _require(row["district_adapter_id"] == adapter, "PRODUCTION_PROFILE_ADAPTER_INVALID", row["binding_id"])
        _require(list(row["district_division_map"]) == [district], "PRODUCTION_PROFILE_DISTRICT_INVALID", row["binding_id"])
    return normalized


def validate_source_package(package: dict[str, Any], *, profile_id: str,
                            acceptance_receipt: dict[str, Any], package_sha256: str,
                            bindings: list[dict[str, Any]]) -> None:
    """Validate a partial source package under the explicit bounded production profile."""
    _require(profile_id == PROFILE_ID, "PRODUCTION_PROFILE_UNSUPPORTED", str(profile_id))
    _require(isinstance(package_sha256, str) and re.fullmatch(r"[a-f0-9]{64}", package_sha256) is not None,
             "PRODUCTION_PROFILE_PACKAGE_HASH_INVALID")
    _require(isinstance(package, dict) and package.get("schema_version") == "0.1",
             "PRODUCTION_PROFILE_PACKAGE_VERSION_UNSUPPORTED")
    jurisdiction = package.get("jurisdiction")
    qa = package.get("qa")
    records = package.get("records")
    _require(isinstance(jurisdiction, dict) and jurisdiction.get("state_abbr") == "TX" and jurisdiction.get("geoid") == "48",
             "PRODUCTION_PROFILE_TEXAS_PACKAGE_REQUIRED")
    for key in ("jurisdiction_id", "name", "state_abbr", "geoid"):
        _require(jurisdiction.get(key), "PRODUCTION_PROFILE_JURISDICTION_FIELD_MISSING", key)
    _require(isinstance(qa, dict) and isinstance(records, dict), "PRODUCTION_PROFILE_PACKAGE_SHAPE_INVALID")
    for table in BASE_TABLES:
        _require(isinstance(records.get(table), list), "PRODUCTION_PROFILE_RECORD_TABLE_MISSING", table)
        _require(all(isinstance(row, dict) for row in records[table]), "PRODUCTION_PROFILE_RECORD_INVALID", table)
    graph_errors = validate_identity_graph(records)
    _require(not graph_errors, "PRODUCTION_PROFILE_IDENTITY_GRAPH_INVALID", ",".join(graph_errors))

    provenance = package.get("provenance")
    _require(isinstance(provenance, dict) and isinstance(provenance.get("source_evidence"), list)
             and bool(provenance["source_evidence"]) and isinstance(provenance.get("source_assertions"), list),
             "PRODUCTION_PROFILE_PROVENANCE_INVALID")
    source_errors = validate_role_term_sources(records, provenance)
    _require(not source_errors, "PRODUCTION_PROFILE_ROLE_TERM_EVIDENCE_INVALID", ",".join(source_errors))
    _require(isinstance(package.get("warnings"), list), "PRODUCTION_PROFILE_WARNINGS_INVALID")

    for block in (jurisdiction, qa):
        _require(block.get("complete_jurisdiction") is False and block.get("publication_eligible") is False,
                 "PRODUCTION_PROFILE_EXPLICIT_PARTIAL_SCOPE_REQUIRED")
    _require(qa.get("parity_ok") is True and type(qa.get("qa_fail_count")) is int and qa["qa_fail_count"] == 0,
             "PRODUCTION_PROFILE_SOURCE_QA_FAILED")
    _require(type(qa.get("blocking_gap_count")) is int and qa["blocking_gap_count"] >= 0,
             "PRODUCTION_PROFILE_SOURCE_GAP_COUNT_INVALID")
    _require(isinstance(qa.get("blocking_gaps"), list) and len(qa["blocking_gaps"]) == qa["blocking_gap_count"],
             "PRODUCTION_PROFILE_SOURCE_GAP_COUNT_DRIFT")
    _require(isinstance(qa.get("address_tests"), list), "PRODUCTION_PROFILE_SOURCE_ADDRESS_TESTS_INVALID")

    for table in ("divisions", "offices", "people", "role_terms"):
        _require(len(records[table]) == 2, "PRODUCTION_PROFILE_EXACT_TWO_CHAINS_REQUIRED", table)
    for table in ("bodies", "leadership_roles", "identifier_crosswalk"):
        _require(not records[table], "PRODUCTION_PROFILE_ADDITIONAL_SCOPE_UNSUPPORTED", table)
    _require(not any(records.get(table) for table in ("elections", "contests", "candidacies")),
             "PRODUCTION_PROFILE_ELECTION_SCOPE_UNSUPPORTED")

    catalog_bindings = _normalized_bindings(bindings)
    jid = jurisdiction.get("jurisdiction_id")
    _require(all(row["package_jurisdiction_id"] == jid and row["civic_gps_jurisdiction_id"] == jid for row in catalog_bindings),
             "PRODUCTION_PROFILE_JURISDICTION_BINDING_DRIFT")
    division_ids = {row.get("division_id") or row.get("id") for row in records["divisions"]}
    _require({next(iter(row["district_division_map"].values())) for row in catalog_bindings} == division_ids,
             "PRODUCTION_PROFILE_DIVISION_SCOPE_DRIFT")

    receipt = acceptance_receipt
    _require(isinstance(receipt, dict) and receipt.get("schema_version") == RECEIPT_SCHEMA,
             "PRODUCTION_PROFILE_RECEIPT_SCHEMA_INVALID")
    _require(receipt.get("status") == "INTERNAL_REVIEW_ACCEPTED", "PRODUCTION_PROFILE_RECEIPT_NOT_ACCEPTED")
    receipt_digest = receipt.get("deterministic_sha256")
    unsigned = dict(receipt)
    unsigned.pop("deterministic_sha256", None)
    _require(isinstance(receipt_digest, str) and receipt_digest == _sha(_canonical(unsigned)),
             "PRODUCTION_PROFILE_RECEIPT_DIGEST_INVALID")
    _require(receipt.get("inputs", {}).get("package_sha256") == package_sha256,
             "PRODUCTION_PROFILE_RECEIPT_PACKAGE_MISMATCH")

    scope = receipt.get("scope")
    _require(isinstance(scope, dict) and scope.get("profile") == "EXACT_TWO_OFFICE_REPRESENTATION"
             and scope.get("coverage_rule") == "ALL_BINDINGS_REQUIRED"
             and scope.get("address_domain") == "HOUSE_49_INTERSECTION_SENATE_14"
             and scope.get("omitted_data_meaning") == "NOT_INCLUDED_NOT_ABSENT"
             and scope.get("elections_included") is False,
             "PRODUCTION_PROFILE_RECEIPT_SCOPE_INVALID")
    _require(_normalized_bindings(scope.get("bindings")) == catalog_bindings,
             "PRODUCTION_PROFILE_RECEIPT_BINDING_DRIFT")
    _require(set(scope.get("office_ids") or []) == {row.get("office_id") or row.get("id") for row in records["offices"]}
             and set(scope.get("person_ids") or []) == {row.get("person_id") or row.get("id") for row in records["people"]}
             and set(scope.get("role_term_ids") or []) == {row.get("role_term_id") or row.get("term_id") or row.get("id") for row in records["role_terms"]},
             "PRODUCTION_PROFILE_RECEIPT_CHAIN_DRIFT")

    source_qa = receipt.get("source_qa_preserved")
    _require(isinstance(source_qa, dict)
             and source_qa.get("blocking_gap_count") == qa["blocking_gap_count"]
             and source_qa.get("address_test_count") == len(qa["address_tests"])
             and source_qa.get("qa_sha256") == _sha(_canonical(qa)),
             "PRODUCTION_PROFILE_RECEIPT_SOURCE_QA_DRIFT")
    identity = {str(row.get("person_id") or row.get("id")): _person_status(row) for row in records["people"]}
    _require(receipt.get("person_identity_status") == identity, "PRODUCTION_PROFILE_RECEIPT_IDENTITY_DRIFT")

    disposition = receipt.get("gate_disposition")
    _require(isinstance(disposition, dict)
             and disposition.get("BOUNDED_COVERAGE_CONTRACT") == "RESOLVED_INTERNAL_ONLY"
             and disposition.get("REPOSITORY_ACTIVATION") == "NOT_ACTIVATED",
             "PRODUCTION_PROFILE_RECEIPT_BASE_GOVERNANCE_INVALID")
    _require(receipt.get("complete_jurisdiction") is False and receipt.get("publication_eligible") is False
             and receipt.get("production_release_eligible") is False and receipt.get("canonical_writes") == 0,
             "PRODUCTION_PROFILE_RECEIPT_RELEASE_SCOPE_DRIFT")

    identity_errors = validate_public_identity_disposition(package)
    _require(not identity_errors, "PRODUCTION_PROFILE_PUBLIC_IDENTITY_UNRESOLVED", ",".join(identity_errors))
    authoritative_errors = [
        f"{str(person.get('person_id') or person.get('id') or 'unknown')}:{_person_status(person) or 'MISSING'}"
        for person in records["people"]
        if _person_status(person) != "AUTHORITATIVE"
    ]
    _require(not authoritative_errors, "PRODUCTION_PROFILE_AUTHORITATIVE_IDENTITY_REQUIRED",
             ",".join(authoritative_errors))


def load_profile_package(package_dir: str | Path, *, profile_id: str,
                         acceptance_receipt: dict[str, Any], bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """Load a profile-scoped package without weakening the ordinary package loader."""
    root = Path(package_dir)
    _require(root.is_dir(), "PRODUCTION_PROFILE_PACKAGE_DIRECTORY_NOT_FOUND", str(root))
    for name in REQUIRED_FILES:
        _require((root / name).is_file(), "PRODUCTION_PROFILE_REQUIRED_FILE_MISSING", name)

    before = _directory_digest(root)
    sums = _parse_sums((root / "SHA256SUMS.txt").read_text(encoding="utf-8"))
    for name in ("jurisdiction.json", "qa_report.json", "manifest.json"):
        expected = sums.get(name)
        _require(bool(expected), "PRODUCTION_PROFILE_CHECKSUM_MISSING", name)
        _require(_sha_file(root / name) == expected, "PRODUCTION_PROFILE_CHECKSUM_MISMATCH", name)

    package_path = root / "jurisdiction.json"
    package = _load_json(package_path, "PRODUCTION_PROFILE_JURISDICTION_JSON_INVALID")
    qa_report = _load_json(root / "qa_report.json", "PRODUCTION_PROFILE_QA_REPORT_INVALID")
    manifest = _load_json(root / "manifest.json", "PRODUCTION_PROFILE_MANIFEST_INVALID")
    validate_source_package(package, profile_id=profile_id, acceptance_receipt=acceptance_receipt,
                            package_sha256=_sha_file(package_path), bindings=bindings)

    _require(qa_report == package.get("qa"), "PRODUCTION_PROFILE_QA_SIDECAR_DRIFT")
    _require(str(manifest.get("schema_version")) == str(package.get("schema_version")),
             "PRODUCTION_PROFILE_MANIFEST_SCHEMA_DRIFT")
    _require(manifest.get("jurisdiction_id") == package["jurisdiction"]["jurisdiction_id"],
             "PRODUCTION_PROFILE_MANIFEST_JURISDICTION_DRIFT")
    files = manifest.get("files")
    _require(isinstance(files, list), "PRODUCTION_PROFILE_MANIFEST_FILES_INVALID")
    for entry in files:
        _require(isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"],
                 "PRODUCTION_PROFILE_MANIFEST_ENTRY_INVALID")
        relative = Path(entry["path"])
        _require(not relative.is_absolute() and ".." not in relative.parts,
                 "PRODUCTION_PROFILE_MANIFEST_PATH_INVALID", entry["path"])
        file_path = root / relative
        _require(file_path.is_file(), "PRODUCTION_PROFILE_MANIFEST_FILE_MISSING", entry["path"])
        _require(file_path.stat().st_size == entry.get("bytes"),
                 "PRODUCTION_PROFILE_MANIFEST_BYTE_DRIFT", entry["path"])
    _require(before == _directory_digest(root), "PRODUCTION_PROFILE_READ_MUTATED_SOURCE")
    return package
