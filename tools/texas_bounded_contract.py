"""Hash-bound acceptance receipt for the two-office internal Texas preview.

This creates metadata, never a production package or a public eligibility grant.
Expected input pins must come from previously reviewed artifacts, not be chosen
merely to make an arbitrary new artifact pass.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import zipfile

from civic_gps_extensions.texas_legislative import build_texas_internal_configuration
from consumers.empowered_vote import representation
from tools.jurisdiction_package import canonical_json, validate_identity_graph, validate_role_term_sources


class BoundedContractError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise BoundedContractError(code)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _pin(data, expected, name):
    _require(isinstance(expected, str) and re.fullmatch(r"[a-f0-9]{64}", expected), name + "_PIN_INVALID")
    _require(isinstance(data, bytes) and _sha(data) == expected, name + "_HASH_MISMATCH")


def build_contract(package_bytes, evidence_zip_bytes, *, expected_package_sha256,
                   expected_evidence_sha256, expected_tested_commit,
                   house_division_id, senate_division_id):
    """Replay reviewed evidence offline and produce a deterministic bounded receipt."""
    _pin(package_bytes, expected_package_sha256, "PACKAGE")
    _pin(evidence_zip_bytes, expected_evidence_sha256, "EVIDENCE")
    _require(isinstance(expected_tested_commit, str) and re.fullmatch(r"[a-f0-9]{40}", expected_tested_commit), "TESTED_COMMIT_INVALID")
    try:
        package = json.loads(package_bytes)
        return _build(package, evidence_zip_bytes, expected_package_sha256, expected_evidence_sha256,
                      expected_tested_commit, house_division_id, senate_division_id)
    except BoundedContractError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile) as exc:
        raise BoundedContractError("INPUT_CONTRACT_INVALID") from exc


def _build(package, evidence_bytes, package_sha, evidence_sha, commit, house_id, senate_id):
    _require(package.get("schema_version") == "0.1", "PACKAGE_VERSION_UNSUPPORTED")
    _require(not validate_identity_graph(package.get("records")), "PACKAGE_IDENTITY_INVALID")
    _require(not validate_role_term_sources(package["records"], package.get("provenance")), "PACKAGE_PROVENANCE_INVALID")
    for block in ("jurisdiction", "qa"):
        _require(package[block].get("complete_jurisdiction") is False and package[block].get("publication_eligible") is False,
                 "EXPLICIT_INTERNAL_PARTIAL_SCOPE_REQUIRED")
    qa = package["qa"]
    _require(qa.get("parity_ok") is True and type(qa.get("qa_fail_count")) is int and qa["qa_fail_count"] == 0,
             "SOURCE_PARITY_OR_QA_FAILED")
    _require(type(qa.get("blocking_gap_count")) is int and qa["blocking_gap_count"] >= 0, "SOURCE_GAP_COUNT_INVALID")
    _require(isinstance(qa.get("blocking_gaps"), list) and len(qa["blocking_gaps"]) == qa["blocking_gap_count"],
             "SOURCE_GAP_COUNT_DRIFT")
    _require(isinstance(qa.get("address_tests"), list), "SOURCE_ADDRESS_TESTS_INVALID")
    records = package["records"]
    _require(all(len(records[t]) == 2 for t in ("divisions", "offices", "people", "role_terms")), "EXACT_TWO_CHAINS_REQUIRED")
    _require(not any(records[t] for t in ("bodies", "leadership_roles", "identifier_crosswalk")), "ADDITIONAL_SCOPE_UNSUPPORTED")
    _require(not any(records.get(t) for t in ("elections", "contests", "candidacies")), "ELECTION_SCOPE_UNSUPPORTED")
    _require(len({t["office_id"] for t in records["role_terms"]}) == 2 and len({t["person_id"] for t in records["role_terms"]}) == 2,
             "ONE_CHAIN_PER_OFFICE_REQUIRED")
    _, bindings = build_texas_internal_configuration(package, house_division_id=house_id, senate_division_id=senate_id)
    with zipfile.ZipFile(io.BytesIO(evidence_bytes)) as archive:
        names = archive.namelist()
        paths = [PurePosixPath(n) for n in names]
        _require(len(names) == len(set(names)) and all(not p.is_absolute() and ".." not in p.parts and len(p.parts) >= 2 for p in paths),
                 "EVIDENCE_ARCHIVE_PATH_INVALID")
        _require(sum(i.file_size for i in archive.infolist()) < 64 * 1024 * 1024, "EVIDENCE_ARCHIVE_TOO_LARGE")
        roots = {p.parts[0] for p in paths}
        _require(len(roots) == 1, "EVIDENCE_ARCHIVE_ROOT_AMBIGUOUS")
        prefix = next(iter(roots)) + "/"
        def read(name):
            return json.loads(archive.read(prefix + name))
        snapshot = read("source_snapshot.json")
        _require(snapshot["source_candidate_sha256"] == package_sha, "EVIDENCE_PACKAGE_MISMATCH")
        acceptance = read("acceptance_verification.json")
        checks = acceptance.get("checks")
        _require(acceptance.get("commit") == commit, "EVIDENCE_COMMIT_MISMATCH")
        _require(acceptance.get("scope") == "BOUNDED_INTERNAL_LIVE_ACCEPTANCE" and acceptance.get("status") == "PASS"
                 and isinstance(checks, list) and checks and all(c.get("status") == "PASS" for c in checks)
                 and type(acceptance.get("passed")) is int and type(acceptance.get("total")) is int
                 and acceptance["passed"] == acceptance["total"] == len(checks), "EVIDENCE_ACCEPTANCE_FAILED")
        addresses = read("address_control_summary.json")
        _require(isinstance(addresses, list) and len(addresses) == 2
                 and all(type(r.get("geocoder_requests")) is int and r["geocoder_requests"] == 1
                         and r.get("expected_status_met") is True for r in addresses),
                 "ADDRESS_CONTROL_COVERAGE_INVALID")
        _require({r.get("expect") for r in addresses} == {"PASS", "FAIL-CLOSED"}, "ADDRESS_OUTCOMES_INVALID")
        positive_models, negative_models = [], []
        for row in addresses:
            case_id = row["case_id"]
            _require(isinstance(case_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", case_id), "CONTROL_ID_INVALID")
            result = read("address_controls/" + case_id + "/result.json")
            _require(result.get("publication_eligible") is False and type(result.get("canonical_writes")) is int and result["canonical_writes"] == 0
                     and result.get("complete_jurisdiction") is False and result.get("scope") == "INTERNAL_REVIEW",
                     "PREVIEW_SCOPE_DRIFT")
            replay = representation.preview_representation_for_bindings(package, row["address"], result["geography"], bindings=bindings)
            _require(replay == result["representation"], "CAPTURED_REPRESENTATION_DRIFT")
            _require(replay.get("status") == row["expect"] == result.get("status"), "CONTROL_OUTCOME_DRIFT")
            if row["expect"] == "PASS":
                positive_models.append(replay)
            else:
                _require("projections" not in replay, "PARTIAL_NEGATIVE_RESULT")
                negative_models.append(replay)
        _require(len(positive_models) == len(negative_models) == 1, "POSITIVE_NEGATIVE_PAIR_REQUIRED")
        boundary = read("boundary_control_summary.json")
        _require(isinstance(boundary, list) and len(boundary) == 6, "BOUNDARY_COVERAGE_INVALID")
        for chamber in ("house", "senate"):
            rows = [r for r in boundary if r.get("chamber") == chamber]
            _require(len(rows) == 3 and len({r.get("case_id") for r in rows}) == 3
                     and sorted(r.get("expected") for r in rows) == ["CONFLICT", "CONFLICT", "PASS"], "BOUNDARY_CHAMBER_COVERAGE_INVALID")
            for row in rows:
                _require(row.get("control_scope") == "LIVE_COORDINATE_ADAPTER_ONLY"
                         and type(row.get("geocoder_requests")) is int and row["geocoder_requests"] == 0
                         and row.get("address") is None and row.get("expected_status_met") is True
                         and row.get("result", {}).get("status") == row.get("expected"), "BOUNDARY_OUTCOME_INVALID")
        geometry = read("geometry_comparison.json")

    preview = positive_models[0]
    outputs = [o for p in preview["projections"] for o in p["representation"]["applicable_offices"]]
    holders = [h for o in outputs for h in o["holders"]]
    _require({o["office_id"] for o in outputs} == {o["office_id"] for o in records["offices"]}
             and {o["division_id"] for o in outputs} == {house_id, senate_id}
             and len(holders) == 2 and {h["role_term_id"] for h in holders} == {r["role_term_id"] for r in records["role_terms"]},
             "DECLARED_CHAIN_SCOPE_DRIFT")
    receipt = {
        "schema_version": "texas-bounded-acceptance/0.1", "status": "INTERNAL_REVIEW_ACCEPTED",
        "scope": {"profile": "EXACT_TWO_OFFICE_REPRESENTATION", "jurisdiction_id": package["jurisdiction"]["jurisdiction_id"],
                  "coverage_rule": "ALL_BINDINGS_REQUIRED", "address_domain": "HOUSE_49_INTERSECTION_SENATE_14",
                  "bindings": bindings, "office_ids": sorted(o["office_id"] for o in outputs),
                  "person_ids": sorted(h["person_id"] for h in holders), "role_term_ids": sorted(h["role_term_id"] for h in holders),
                  "omitted_data_meaning": "NOT_INCLUDED_NOT_ABSENT", "elections_included": False},
        "authority": {"civic_facts": "PINNED_SOURCE_PACKAGE", "geography": "PINNED_LIVE_ACCEPTANCE_EVIDENCE",
                      "canonical_ids": "PASS_THROUGH", "unknown_dates": "PRESERVE_UNKNOWN"},
        "person_identity_status": {h["person_id"]: h.get("person_status") for h in holders},
        "inputs": {"package_sha256": package_sha, "live_evidence_zip_sha256": evidence_sha,
                   "live_tested_commit": commit, "runtime_zip_sha256": snapshot["runtime_zip_sha256"]},
        "acceptance": {"live_address_controls": 2, "live_boundary_coordinate_controls": 6,
                       "captured_integrity_checks": len(checks), "representation_replay": "PASS",
                       "geography_comparison": geometry},
        "source_qa_preserved": {"blocking_gap_count": qa["blocking_gap_count"],
                                "address_test_count": len(qa.get("address_tests", [])),
                                "qa_sha256": _sha(canonical_json(qa).encode("utf-8"))},
        "gate_disposition": {"BOUNDED_COVERAGE_CONTRACT": "RESOLVED_INTERNAL_ONLY",
                             "GPS_BINDINGS": "VERIFIED_CAPTURED_CANDIDATE", "LIVE_ADDRESS_CONTROLS": "VERIFIED_CAPTURED_CANDIDATE",
                             "GEOMETRY_VERSION_GOVERNANCE": "OPEN",
                             "PUBLIC_PERSON_IDENTITY": "BLOCKED_PROVISIONAL" if any(h.get("person_status") == "PROVISIONAL" for h in holders) else "PUBLIC_DISPOSITION_REQUIRED",
                             "PRODUCTION_PARTIAL_PACKAGE_PROFILE": "UNSUPPORTED", "REPOSITORY_ACTIVATION": "NOT_ACTIVATED"},
        "complete_jurisdiction": False, "publication_eligible": False, "production_release_eligible": False,
        "canonical_writes": 0,
    }
    receipt["deterministic_sha256"] = _sha(canonical_json(receipt).encode("utf-8"))
    return receipt
