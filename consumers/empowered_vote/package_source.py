#!/usr/bin/env python3
"""Read-only CivicData jurisdiction-package boundary for Empowered.Vote.

EV-IMP-002 consumes deterministic package artifacts and never writes to the
package directory or CivicData canonical data. Jurisdiction Package v0.1 stays
representation-only. Version v0.2 adds governed Election, Contest, and
Candidacy collections and can drive bounded Full Essentials when its QA gates
explicitly declare election scope complete and unexplained loss zero.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA_VERSIONS = {"0.1", "0.2"}
REQUIRED_RECORD_TABLES = (
    "divisions", "bodies", "offices", "people", "role_terms",
    "leadership_roles", "identifier_crosswalk",
)
FULL_ESSENTIALS_RECORD_TABLES = ("elections", "contests", "candidacies")
REQUIRED_FILES = ("jurisdiction.json", "qa_report.json", "manifest.json", "SHA256SUMS.txt")


class PackageContractError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def directory_digest(path: Path) -> str:
    h = hashlib.sha256()
    for item in sorted(p for p in path.iterdir() if p.is_file()):
        h.update(item.name.encode("utf-8")); h.update(b"\0")
        h.update(item.read_bytes()); h.update(b"\0")
    return h.hexdigest()


def _norm_address(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold().strip())
    return " ".join(value.split())


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageContractError(code, str(exc)) from exc
    if not isinstance(data, dict):
        raise PackageContractError(code, "expected JSON object")
    return data


def _parse_sums(text: str) -> dict[str, str]:
    sums: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line: continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise PackageContractError("PACKAGE_CHECKSUM_FILE_INVALID", line)
        digest, name = parts
        name = name.lstrip("*").strip()
        if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
            raise PackageContractError("PACKAGE_CHECKSUM_FILE_INVALID", line)
        sums[name] = digest.lower()
    return sums


def _validate_package_shape(package: dict[str, Any]) -> None:
    version = str(package.get("schema_version"))
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise PackageContractError("PACKAGE_SCHEMA_VERSION_UNSUPPORTED", version)

    jurisdiction = package.get("jurisdiction")
    if not isinstance(jurisdiction, dict):
        raise PackageContractError("PACKAGE_JURISDICTION_MISSING")
    for key in ("jurisdiction_id", "name", "state_abbr", "geoid"):
        if not jurisdiction.get(key):
            raise PackageContractError("PACKAGE_JURISDICTION_FIELD_MISSING", key)

    records = package.get("records")
    if not isinstance(records, dict):
        raise PackageContractError("PACKAGE_RECORDS_MISSING")
    required = list(REQUIRED_RECORD_TABLES)
    if version == "0.2": required += list(FULL_ESSENTIALS_RECORD_TABLES)
    missing_tables = [name for name in required if not isinstance(records.get(name), list)]
    if missing_tables:
        raise PackageContractError("PACKAGE_RECORD_TABLE_MISSING", ",".join(missing_tables))

    provenance = package.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("source_evidence"), list):
        raise PackageContractError("PACKAGE_PROVENANCE_MISSING")
    if not provenance.get("source_evidence"):
        raise PackageContractError("PACKAGE_PROVENANCE_EMPTY")
    if not isinstance(provenance.get("source_assertions"), list):
        raise PackageContractError("PACKAGE_SOURCE_ASSERTIONS_MISSING")

    qa = package.get("qa")
    if not isinstance(qa, dict):
        raise PackageContractError("PACKAGE_QA_MISSING")
    if qa.get("parity_ok") is not True:
        raise PackageContractError("PACKAGE_PARITY_NOT_TRUE")
    if qa.get("qa_fail_count") != 0:
        raise PackageContractError("PACKAGE_QA_FAILURES_PRESENT", str(qa.get("qa_fail_count")))
    if qa.get("blocking_gap_count") != 0:
        raise PackageContractError("PACKAGE_BLOCKING_GAPS_PRESENT", str(qa.get("blocking_gap_count")))
    address_tests = qa.get("address_tests")
    if not isinstance(address_tests, list) or len(address_tests) < 2:
        raise PackageContractError("PACKAGE_ADDRESS_CONTROLS_INSUFFICIENT")
    if any(not isinstance(test, dict) for test in address_tests):
        raise PackageContractError("PACKAGE_ADDRESS_CONTROL_INVALID")
    if any(test.get("result") is not True for test in address_tests):
        raise PackageContractError("PACKAGE_ADDRESS_CONTROL_FAILED")
    if version == "0.2":
        if qa.get("election_scope_complete") is not True:
            raise PackageContractError("PACKAGE_ELECTION_SCOPE_INCOMPLETE")
        if qa.get("unexplained_loss") != 0:
            raise PackageContractError("PACKAGE_UNEXPLAINED_LOSS", str(qa.get("unexplained_loss")))

    if not isinstance(package.get("warnings"), list):
        raise PackageContractError("PACKAGE_WARNINGS_INVALID")


def load_jurisdiction_package(package_dir: str | Path) -> dict[str, Any]:
    root = Path(package_dir)
    if not root.is_dir():
        raise PackageContractError("PACKAGE_DIRECTORY_NOT_FOUND", str(root))
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            raise PackageContractError("PACKAGE_REQUIRED_FILE_MISSING", name)

    before = directory_digest(root)
    sums = _parse_sums((root / "SHA256SUMS.txt").read_text(encoding="utf-8"))
    for name in ("jurisdiction.json", "qa_report.json", "manifest.json"):
        expected = sums.get(name)
        if not expected:
            raise PackageContractError("PACKAGE_CHECKSUM_MISSING", name)
        if sha256_file(root / name) != expected:
            raise PackageContractError("PACKAGE_CHECKSUM_MISMATCH", name)

    package = _load_json(root / "jurisdiction.json", "PACKAGE_JURISDICTION_JSON_INVALID")
    qa_report = _load_json(root / "qa_report.json", "PACKAGE_QA_REPORT_INVALID")
    manifest = _load_json(root / "manifest.json", "PACKAGE_MANIFEST_INVALID")
    _validate_package_shape(package)

    if qa_report != package.get("qa"):
        raise PackageContractError("PACKAGE_QA_SIDECAR_DRIFT")
    if str(manifest.get("schema_version")) != str(package.get("schema_version")):
        raise PackageContractError("PACKAGE_MANIFEST_SCHEMA_VERSION_MISMATCH")
    if manifest.get("jurisdiction_id") != package["jurisdiction"]["jurisdiction_id"]:
        raise PackageContractError("PACKAGE_MANIFEST_JURISDICTION_MISMATCH")

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        raise PackageContractError("PACKAGE_MANIFEST_FILES_INVALID")
    for entry in manifest_files:
        if not isinstance(entry, dict) or not entry.get("path"):
            raise PackageContractError("PACKAGE_MANIFEST_ENTRY_INVALID")
        file_path = root / str(entry["path"])
        if not file_path.is_file():
            raise PackageContractError("PACKAGE_MANIFEST_FILE_MISSING", str(entry["path"]))
        if file_path.stat().st_size != entry.get("bytes"):
            raise PackageContractError("PACKAGE_MANIFEST_BYTE_DRIFT", str(entry["path"]))

    if before != directory_digest(root):
        raise PackageContractError("PACKAGE_READ_MUTATED_SOURCE")
    return package


def package_capabilities(package: dict[str, Any]) -> dict[str, bool]:
    records = package.get("records") if isinstance(package.get("records"), dict) else {}
    version = str(package.get("schema_version"))
    representation = all(isinstance(records.get(name), list) for name in REQUIRED_RECORD_TABLES)
    elections = (
        version == "0.2"
        and all(isinstance(records.get(name), list) for name in FULL_ESSENTIALS_RECORD_TABLES)
        and package.get("qa", {}).get("election_scope_complete") is True
        and package.get("qa", {}).get("unexplained_loss") == 0
    )
    return {"representation": representation, "elections": elections, "full_essentials": representation and elections, "read_only": True}


def require_full_essentials(package: dict[str, Any]) -> None:
    if package_capabilities(package)["full_essentials"]:
        return
    if str(package.get("schema_version")) == "0.1":
        raise PackageContractError("FULL_ESSENTIALS_UNSUPPORTED_BY_PACKAGE_V0_1")
    raise PackageContractError("FULL_ESSENTIALS_PACKAGE_GATES_NOT_MET")


def representation_projection(package: dict[str, Any]) -> dict[str, Any]:
    records = package["records"]
    projection: dict[str, Any] = {
        "status": "PASS", "consumer_gate": "EV-IMP-002",
        "package_schema_version": package["schema_version"],
        "jurisdiction": package["jurisdiction"],
        "divisions": records["divisions"], "bodies": records["bodies"],
        "offices": records["offices"], "people": records["people"],
        "role_terms": records["role_terms"], "leadership_roles": records["leadership_roles"],
        "identifier_crosswalk": records["identifier_crosswalk"],
        "source_evidence": package["provenance"]["source_evidence"],
        "source_assertions": package["provenance"]["source_assertions"],
        "address_tests": package["qa"]["address_tests"], "warnings": package["warnings"],
        "canonical_writes": 0,
    }
    projection["deterministic_sha256"] = sha256_bytes(canonical_json_bytes(projection))
    return projection


def _source_projection(source: dict[str, Any] | None) -> dict[str, Any] | None:
    if not source: return None
    return {
        "source_id": source.get("source_id") or source.get("Source_ID"),
        "title": source.get("Title") or source.get("title"),
        "publisher": source.get("Publisher") or source.get("publisher"),
        "url": source.get("Source_URL_or_File") or source.get("url"),
        "authority_level": source.get("Authority_Level") or source.get("authority_level"),
        "verification_status": source.get("Verification_Status") or source.get("verification_status"),
        "verified_as_of": source.get("Verified_As_Of_ISO") or source.get("verified_as_of"),
    }


def build_essentials_from_package(package: dict[str, Any], address: str) -> dict[str, Any]:
    """Build bounded Full Essentials directly from a validated v0.2 package."""
    require_full_essentials(package)
    target = _norm_address(address)
    control = next((x for x in package["qa"]["address_tests"] if _norm_address(str(x.get("input", ""))) == target), None)
    if control is None:
        return {"status": "FAIL-CLOSED", "error": "ADDRESS_NOT_IN_GOVERNED_PACKAGE", "input_address": address, "canonical_writes": 0}

    records = package["records"]
    jurisdiction_division = package["jurisdiction"].get("division_id")
    district_division = control.get("fixture_tacoma_division_id")
    active = district_division is not None

    source_idx = {str(x.get("source_id") or x.get("Source_ID")): x for x in package["provenance"]["source_evidence"]}
    people_idx = {str(x.get("person_id") or x.get("id")): x for x in records["people"]}
    terms_by_office = {str(x.get("office_id")): x for x in records["role_terms"] if x.get("office_id")}
    leadership_by_pair = {(str(x.get("office_id")), str(x.get("person_id"))): x for x in records["leadership_roles"]}

    applicable_offices = []
    applicable_ids: set[str] = set()
    if active:
        for office in records["offices"]:
            geography = office.get("geography_id")
            if geography not in {jurisdiction_division, district_division}: continue
            office_id = str(office.get("office_id") or office.get("id"))
            applicable_ids.add(office_id)
            term = terms_by_office.get(office_id)
            holder = None
            source_id = office.get("source_id")
            if term:
                person_id = str(term.get("person_id"))
                person = people_idx.get(person_id, {})
                lead = leadership_by_pair.get((office_id, person_id), {})
                source_id = term.get("source_id") or source_id
                holder = {
                    "person_id": person_id,
                    "name": person.get("name") or person.get("Canonical_Name"),
                    "currentness_status": term.get("currentness_status"),
                    "leadership_role": lead.get("role"),
                    "selection_method": term.get("selection_method"),
                    "term_start": term.get("term_start"),
                    "term_end": term.get("term_end"),
                    "term_end_basis": term.get("term_end_basis"),
                }
            applicable_offices.append({
                "office_id": office_id,
                "office_name": office.get("name") or office.get("Canonical_Name"),
                "seat_type": office.get("classification_or_role"),
                "division_id": geography,
                "current_status": office.get("current_status"),
                "holder": holder,
                "provenance": _source_projection(source_idx.get(str(source_id))),
            })

    contests = []
    contest_ids: set[str] = set()
    for contest in records["contests"]:
        if contest.get("office_id") not in applicable_ids: continue
        cid = str(contest["contest_id"]); contest_ids.add(cid)
        source_id = (contest.get("source_ids") or [None])[0]
        contests.append({
            "contest_id": cid, "contest_name": contest.get("contest_name"),
            "election_id": contest.get("election_id"), "office_id": contest.get("office_id"),
            "provenance": _source_projection(source_idx.get(str(source_id))), "candidates": [],
        })
    contest_idx = {x["contest_id"]: x for x in contests}
    for candidacy in records["candidacies"]:
        cid = str(candidacy.get("contest_id"))
        if cid not in contest_ids: continue
        contest_idx[cid]["candidates"].append({
            "candidacy_id": candidacy.get("candidacy_id"),
            "candidate_source_id": candidacy.get("source_candidate_id"),
            "person_id": candidacy.get("person_id"),
            "candidate_name": candidacy.get("candidate_name"),
            "ballot_name": candidacy.get("ballot_name"),
            "outcome": candidacy.get("outcome"), "votes": candidacy.get("votes"),
            "vote_share": candidacy.get("vote_share"),
            "is_write_in_bucket": candidacy.get("candidate_kind") == "WRITE_IN_BUCKET",
            "provenance": _source_projection(source_idx.get(str(candidacy.get("source_id")))),
        })
    for contest in contests:
        contest["candidates"].sort(key=lambda row: (0 if row.get("outcome") == "WINNER" else 1, str(row.get("candidate_name") or ""), str(row.get("candidate_source_id") or "")))
    applicable_offices.sort(key=lambda row: (str(row.get("seat_type")), str(row.get("office_name"))))
    contests.sort(key=lambda row: (str(row.get("election_id")), str(row.get("contest_name"))))

    model: dict[str, Any] = {
        "status": "PASS", "consumer_gate": "EV-IMP-002",
        "package_schema_version": package["schema_version"], "input_address": address,
        "address_control_id": control.get("control_id"),
        "resolved_jurisdictions": sorted(control.get("resolved_jurisdictions", [])),
        "district_assignments": dict(sorted((control.get("district_assignments") or {}).items())),
        "jurisdiction": package["jurisdiction"] if active else None,
        "applicable_offices": applicable_offices, "recent_certified_contests": contests,
        "warnings": package.get("warnings", []), "canonical_writes": 0,
    }
    model["deterministic_sha256"] = sha256_bytes(canonical_json_bytes(model))
    return model
