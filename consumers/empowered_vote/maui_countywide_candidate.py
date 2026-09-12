#!/usr/bin/env python3
"""Inactive catalog adapter for the certified Maui residency-aware preview."""
from __future__ import annotations

import copy
from typing import Any

from consumers.empowered_vote import maui_countywide_preview as preview

GATE = "EV-MAUI-PROD-ADAPTER-CANDIDATE-001"
ENTRY_ID = "candidate-hi-maui-countywide-v0.1"
SCOPE = "MAUI_COUNTYWIDE_MAYOR_AND_COUNCIL_ONLY"
FLAGS = {"candidate_only": True, "production_eligible": False,
         "publication_eligible": False, "complete_jurisdiction": False}
PACKAGE_SHA256 = "7ddaf33b2184f9a465128cac581e75b5b6a3a5601ca052d5ff9403b2ffc006e3"
ARTIFACT = {
    "encoding": "base64-parts",
    "parts_glob": "previews/ev/maui/Maui_County_Preview_Package_v0.1_2026-09-12.zip.b64.part01",
    "archive_sha256": "3ba797f102b18d7c560cd918f2eddb0ffeb406c850e7c1751d6ed7cd9222301a",
    "package_subdir": "Maui_County_Preview_Package_v0.1_2026-09-12/package",
}
SOURCE_CORRECTION = {
    "path": "previews/ev/maui_source_correction.v0.1.json",
    "sha256": "1155e5ba2128cd6d85daf212d8e1b0acd01ac39df791db941b40cd7d70dbc262",
}


class MauiCandidateError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise MauiCandidateError(code)


def validate_entry(entry: dict[str, Any]) -> None:
    require(isinstance(entry, dict), "MAUI_CANDIDATE_ENTRY_INVALID")
    require(all(entry.get(key) is value for key, value in FLAGS.items()),
            "MAUI_CANDIDATE_HOLD_REQUIRED")
    require(not any(key in entry for key in (
        "district_binding", "district_bindings", "production_profile", "countywide_profile")),
        "PACKAGE_CATALOG_BINDING_FORMS_CONFLICT")
    require(set(entry) == {"entry_id", "profile", "package_schema_version", "package_jurisdiction_id",
        "civic_gps_jurisdiction_id", "artifact", "countywide_binding", *FLAGS}
        and entry.get("entry_id") == ENTRY_ID and entry.get("profile") == "municipal_representation"
        and entry.get("package_schema_version") == "0.1"
        and entry.get("package_jurisdiction_id") == preview.PACKAGE_ID
        and entry.get("civic_gps_jurisdiction_id") == preview.CIVIC_ID,
        "MAUI_CANDIDATE_IDENTITY_INVALID")
    require(entry.get("artifact") == ARTIFACT, "MAUI_CANDIDATE_ARTIFACT_PIN_REQUIRED")
    binding = entry.get("countywide_binding")
    require(isinstance(binding, dict), "MAUI_CANDIDATE_BINDING_REQUIRED")
    require(set(binding) == {"binding_version", "binding_id", "mode", "geoid", "scope", "offices",
        "expected_leadership_ids", "expected_package_sha256", "source_correction"}
        and binding.get("binding_version") == "0.1" and binding.get("binding_id") == ENTRY_ID
        and binding.get("mode") == "MAUI_COUNTYWIDE_RESIDENCY_CANDIDATE"
        and binding.get("geoid") == "15009" and binding.get("scope") == SCOPE
        and binding.get("expected_package_sha256") == PACKAGE_SHA256
        and binding.get("source_correction") == SOURCE_CORRECTION,
        "MAUI_CANDIDATE_BINDING_INVALID")
    offices = binding.get("offices")
    require(isinstance(offices, list) and all(isinstance(row, dict) for row in offices)
        and all(type(row.get("seats")) is int for row in offices)
        and sorted(offices, key=lambda row: str(row.get("office_id")))
            == sorted(preview.office_contracts(), key=lambda row: row["office_id"])
        and binding.get("expected_leadership_ids") == list(preview.LEADERSHIP),
        "MAUI_CANDIDATE_ROSTER_INVALID")


def build_representation(package: dict[str, Any], address: str, geographic: Any,
                         entry: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_entry(entry)
        binding = entry["countywide_binding"]
        preview_binding = {
            "preview_version": "0.1", "binding_id": "preview-hi-maui-countywide-v0.1",
            "mode": "MAUI_COUNTYWIDE_RESIDENCY_PREVIEW", "preview_only": True,
            "publication_eligible": False, "complete_jurisdiction": False,
            "package_jurisdiction_id": preview.PACKAGE_ID,
            "civic_gps_jurisdiction_id": preview.CIVIC_ID, "geoid": "15009",
            "offices": copy.deepcopy(binding["offices"]),
            "expected_leadership_ids": copy.deepcopy(binding["expected_leadership_ids"]),
            "expected_package_sha256": binding["expected_package_sha256"],
        }
        result = preview.preview_maui_representation(package, address, geographic, binding=preview_binding)
    except MauiCandidateError as exc:
        result = {"status": "FAIL-CLOSED", "error": exc.code}
    except (KeyError, TypeError, ValueError, AttributeError):
        result = {"status": "FAIL-CLOSED", "error": "MAUI_CANDIDATE_INPUT_INVALID"}
    result.pop("preview_gate", None)
    result.pop("deterministic_sha256", None)
    result.update(FLAGS)
    result.update({"candidate_gate": GATE, "consumer_gate": "EV-IMP-005",
                   "preview_only": True, "canonical_writes": 0})
    if result["status"] == "PASS":
        result.update({"package_catalog_entry_id": ENTRY_ID, "representation_only": True,
            "full_essentials_supported": False, "package_schema_version": "0.1"})
    result["deterministic_sha256"] = preview.package_source.sha256_bytes(
        preview.package_source.canonical_json_bytes(result))
    return result
