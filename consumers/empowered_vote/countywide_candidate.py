#!/usr/bin/env python3
"""Explicit, inactive Kauaʻi countywide catalog adapter candidate."""
from __future__ import annotations

import copy
from typing import Any

from consumers.empowered_vote import countywide_preview as preview

GATE = "EV-KAUAI-PROD-ADAPTER-CANDIDATE-001"
ENTRY_ID = "candidate-hi-kauai-countywide-v0.1"
ARCHIVE_SHA256 = "fac5f85e589d237252f7067563f90f73c09f566237967201ef30c994d524081e"
FLAGS = {"candidate_only": True, "production_eligible": False,
         "publication_eligible": False, "complete_jurisdiction": False}
SCOPE = "KAUAI_COUNTYWIDE_MAYOR_AND_COUNCIL_ONLY"


class CountywideCandidateError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CountywideCandidateError(code)


def validate_entry(entry: dict[str, Any]) -> None:
    """Reject mixed bindings, scope/identity drift, and attempted activation."""
    require(isinstance(entry, dict), "COUNTYWIDE_CANDIDATE_ENTRY_INVALID")
    require(all(entry.get(key) is value for key, value in FLAGS.items()),
            "COUNTYWIDE_CANDIDATE_HOLD_REQUIRED")
    require(entry.get("entry_id") == ENTRY_ID
            and entry.get("profile") == "municipal_representation"
            and entry.get("package_schema_version") == "0.1"
            and entry.get("package_jurisdiction_id") == preview.PACKAGE_ID
            and entry.get("civic_gps_jurisdiction_id") == preview.CIVIC_ID,
            "COUNTYWIDE_CANDIDATE_IDENTITY_INVALID")
    require(not any(key in entry for key in ("district_binding", "district_bindings", "production_profile")),
            "PACKAGE_CATALOG_BINDING_FORMS_CONFLICT")
    artifact = entry.get("artifact")
    require(isinstance(artifact, dict) and artifact.get("archive_sha256") == ARCHIVE_SHA256,
            "COUNTYWIDE_CANDIDATE_ARCHIVE_PIN_REQUIRED")
    binding = entry.get("countywide_binding")
    require(isinstance(binding, dict), "COUNTYWIDE_CANDIDATE_BINDING_REQUIRED")
    require(set(binding) == {"binding_version", "binding_id", "mode", "geoid", "scope",
                             "offices", "expected_leadership_ids"}
            and binding.get("binding_version") == "0.1"
            and binding.get("binding_id") == ENTRY_ID
            and binding.get("mode") == "COUNTYWIDE_CANDIDATE"
            and binding.get("geoid") == "15007" and binding.get("scope") == SCOPE,
            "COUNTYWIDE_CANDIDATE_BINDING_INVALID")
    offices = binding.get("offices")
    require(isinstance(offices, list) and len(offices) == 2
            and all(isinstance(row, dict) for row in offices),
            "COUNTYWIDE_CANDIDATE_OFFICES_INVALID")
    require({row.get("office_id") for row in offices} == set(preview.OFFICES),
            "COUNTYWIDE_CANDIDATE_OFFICES_INVALID")
    for row in offices:
        constituency, seats = preview.OFFICES[row["office_id"]]
        ids = row.get("expected_person_ids")
        require(set(row) == {"office_id", "constituency", "seats", "expected_person_ids"}
                and row.get("constituency") == constituency
                and type(row.get("seats")) is int and row["seats"] == seats
                and isinstance(ids, list) and len(ids) == seats
                and all(isinstance(value, str) and value for value in ids)
                and len(set(ids)) == seats, "COUNTYWIDE_CANDIDATE_OFFICES_INVALID")
    leaders = binding.get("expected_leadership_ids")
    require(isinstance(leaders, list) and len(leaders) == 2
            and all(isinstance(value, str) and value for value in leaders)
            and len(set(leaders)) == 2, "COUNTYWIDE_CANDIDATE_LEADERSHIP_INVALID")


def build_representation(package: dict[str, Any], address: str, geographic: Any,
                         entry: dict[str, Any]) -> dict[str, Any]:
    """Reuse the certified projection with an explicit candidate catalog contract."""
    try:
        validate_entry(entry)
        binding = entry["countywide_binding"]
        preview_binding = {
            "preview_version": "0.1", "binding_id": "preview-hi-kauai-countywide-v0.1",
            "mode": "COUNTYWIDE_PREVIEW", "preview_only": True,
            "publication_eligible": False, "complete_jurisdiction": False,
            "package_jurisdiction_id": entry["package_jurisdiction_id"],
            "civic_gps_jurisdiction_id": entry["civic_gps_jurisdiction_id"],
            "geoid": binding["geoid"], "offices": copy.deepcopy(binding["offices"]),
            "expected_leadership_ids": copy.deepcopy(binding["expected_leadership_ids"]),
        }
        result = preview.preview_countywide_representation(
            package, address, geographic, binding=preview_binding)
    except CountywideCandidateError as exc:
        result = {"status": "FAIL-CLOSED", "error": exc.code}
    except (KeyError, TypeError, ValueError, AttributeError):
        result = {"status": "FAIL-CLOSED", "error": "COUNTYWIDE_CANDIDATE_INPUT_INVALID"}
    result.pop("preview_gate", None)
    result.pop("deterministic_sha256", None)
    result.update(FLAGS)
    result.update({"candidate_gate": GATE, "consumer_gate": "EV-IMP-005", "canonical_writes": 0})
    if result["status"] == "PASS":
        result["package_catalog_entry_id"] = entry["entry_id"]
        result.update({"representation_only": True, "full_essentials_supported": False,
                       "package_schema_version": entry["package_schema_version"]})
    result["deterministic_sha256"] = preview.package_source.sha256_bytes(
        preview.package_source.canonical_json_bytes(result))
    return result
