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
import re
from typing import Any

PROFILE_ID = "tx_legislative_two_office_v0.1"
RECEIPT_SCHEMA = "texas-bounded-acceptance/0.1"


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


def _person_status(person: dict[str, Any]) -> str | None:
    values = [person[key] for key in ("person_status", "identity_resolution_status", "status", "current_status")
              if person.get(key) not in (None, "")]
    if any(str(value).strip().upper() == "PROVISIONAL" for value in values):
        return "PROVISIONAL"
    value = person.get("person_status") or person.get("identity_resolution_status")
    return str(value) if value not in (None, "") else None


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
    _require(isinstance(qa, dict) and isinstance(records, dict), "PRODUCTION_PROFILE_PACKAGE_SHAPE_INVALID")
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
        _require(isinstance(records.get(table), list) and len(records[table]) == 2,
                 "PRODUCTION_PROFILE_EXACT_TWO_CHAINS_REQUIRED", table)
    for table in ("bodies", "leadership_roles", "identifier_crosswalk"):
        _require(isinstance(records.get(table), list) and not records[table],
                 "PRODUCTION_PROFILE_ADDITIONAL_SCOPE_UNSUPPORTED", table)
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
             and disposition.get("GEOMETRY_VERSION_GOVERNANCE") == "RESOLVED_INTERNAL_ONLY"
             and disposition.get("PUBLIC_PERSON_IDENTITY") == "RESOLVED_PUBLICATION_POLICY"
             and disposition.get("PRODUCTION_PARTIAL_PACKAGE_PROFILE") == "SUPPORTED_NOT_ACTIVATED"
             and disposition.get("REPOSITORY_ACTIVATION") == "NOT_ACTIVATED",
             "PRODUCTION_PROFILE_GOVERNANCE_NOT_READY")
    _require(receipt.get("complete_jurisdiction") is False and receipt.get("publication_eligible") is False
             and receipt.get("production_release_eligible") is False and receipt.get("canonical_writes") == 0,
             "PRODUCTION_PROFILE_RECEIPT_RELEASE_SCOPE_DRIFT")
