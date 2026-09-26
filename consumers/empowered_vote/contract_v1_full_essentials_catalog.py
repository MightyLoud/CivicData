#!/usr/bin/env python3
"""Catalog-routed Empowered Vote Full Essentials shadow for Contract v1."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from adapters.factory.export_representation import ExportError as FactoryExportError
from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote import (
    contract_v1_catalog,
    contract_v1_full_essentials,
    full_essentials_catalog,
    package_catalog,
    package_source,
)


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": "EV-RC1-FULL-SHADOW",
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        out["detail"] = detail
    return out


def build_full_essentials_from_catalog(
    address: str,
    civic_gps_result: dict[str, Any],
    *,
    repo_root: str | Path,
    catalog_path: str | Path = package_catalog.DEFAULT_CATALOG,
    profile: str = "municipal_essentials",
    identity_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select the existing governed package, project Contract v1, and consume it."""
    try:
        catalog = package_catalog.load_catalog(catalog_path)
        entry = package_catalog.select_entry(catalog, civic_gps_result, profile=profile)
        if entry.get("countywide_profile") or entry.get("countywide_binding"):
            raise package_catalog.PackageCatalogError(
                "CONTRACT_V1_COUNTYWIDE_FULL_ESSENTIALS_NOT_MIGRATED",
                str(entry["entry_id"]),
            )
        if entry.get("production_profile") or entry.get("district_bindings"):
            raise package_catalog.PackageCatalogError(
                "CONTRACT_V1_MULTI_BINDING_FULL_ESSENTIALS_NOT_MIGRATED",
                str(entry["entry_id"]),
            )
        package = package_catalog.reconstruct_package(entry, repo_root)
        contract = export_factory_package(
            package,
            generated_at=contract_v1_catalog._generated_at(package),
            governed_package=True,
            identity_registry=identity_registry,
        )
        binding = contract_v1_catalog._contract_binding(
            entry,
            package,
            contract,
            civic_gps_result,
        )
    except package_catalog.PackageCatalogError as exc:
        return _fail(address, exc.code, exc.detail)
    except FactoryExportError as exc:
        return _fail(address, "CONTRACT_V1_FACTORY_EXPORT_FAILED", str(exc))

    model = contract_v1_full_essentials.build_full_essentials_from_civic_gps_result(
        contract,
        address,
        civic_gps_result,
        binding=binding,
    )
    if model.get("status") == "PASS":
        model["consumer_gate"] = "EV-RC1-FULL-SHADOW"
        model["package_catalog_entry_id"] = entry["entry_id"]
        model["contract_source"] = "FACTORY_PACKAGE_PROJECTION"
        model["legacy_package_schema_version"] = package.get("schema_version")
        model.pop("deterministic_sha256", None)
        model["deterministic_sha256"] = package_source.sha256_bytes(
            package_source.canonical_json_bytes(model)
        )
    return model


def _office_summary(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for office in model.get("applicable_offices", []):
        if not isinstance(office, dict):
            continue
        office_id = str(office.get("office_id") or office.get("post_id") or "")
        if not office_id:
            continue
        holders = office.get("holders")
        if not isinstance(holders, list):
            single = office.get("holder")
            holders = [single] if isinstance(single, dict) else []
        leadership: set[str] = set()
        for holder in holders:
            if not isinstance(holder, dict):
                continue
            leadership.update(str(x) for x in holder.get("leadership_roles") or [])
            if holder.get("leadership_role"):
                leadership.add(str(holder["leadership_role"]))
        out[office_id] = {
            "office_name": office.get("office_name"),
            "holders": sorted(
                str(holder.get("name") or "")
                for holder in holders
                if isinstance(holder, dict)
            ),
            "leadership": sorted(leadership),
        }
    return out


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidacy_id": candidate.get("candidacy_id"),
        "candidate_source_id": candidate.get("candidate_source_id"),
        "person_id": candidate.get("person_id"),
        "candidate_name": candidate.get("candidate_name"),
        "ballot_name": candidate.get("ballot_name"),
        "outcome": candidate.get("outcome"),
        "votes": candidate.get("votes"),
        "vote_share": candidate.get("vote_share"),
        "is_write_in_bucket": bool(candidate.get("is_write_in_bucket")),
    }


def _contest_summary(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for contest in model.get("recent_certified_contests", []):
        if not isinstance(contest, dict) or not contest.get("contest_id"):
            continue
        candidates = [
            _candidate_summary(row)
            for row in contest.get("candidates", [])
            if isinstance(row, dict)
        ]
        candidates.sort(
            key=lambda row: (
                str(row.get("candidacy_id") or ""),
                str(row.get("candidate_source_id") or ""),
            )
        )
        out[str(contest["contest_id"])] = {
            "contest_name": contest.get("contest_name"),
            "election_id": contest.get("election_id"),
            "office_id": contest.get("office_id"),
            "candidates": candidates,
        }
    return out


def compare_full_essentials_shadow_to_legacy(
    address: str,
    civic_gps_result: dict[str, Any],
    *,
    repo_root: str | Path,
    catalog_path: str | Path = package_catalog.DEFAULT_CATALOG,
    profile: str = "municipal_essentials",
    identity_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare current package output with Contract v1 Full Essentials semantics."""
    legacy = full_essentials_catalog.build_full_essentials_from_catalog(
        address,
        civic_gps_result,
        repo_root=repo_root,
        catalog_path=catalog_path,
        profile=profile,
    )
    shadow = build_full_essentials_from_catalog(
        address,
        civic_gps_result,
        repo_root=repo_root,
        catalog_path=catalog_path,
        profile=profile,
        identity_registry=identity_registry,
    )
    if legacy.get("status") != "PASS":
        return _fail(address, "LEGACY_FULL_ESSENTIALS_FAILED", str(legacy.get("error")))
    if shadow.get("status") != "PASS":
        return _fail(address, "CONTRACT_V1_FULL_ESSENTIALS_FAILED", str(shadow.get("error")))

    legacy_offices = _office_summary(legacy)
    shadow_offices = _office_summary(shadow)
    office_differences: list[dict[str, Any]] = []
    for office_id in sorted(set(legacy_offices) | set(shadow_offices)):
        left = legacy_offices.get(office_id)
        right = shadow_offices.get(office_id)
        if left != right:
            office_differences.append(
                {
                    "office_id": office_id,
                    "legacy": copy.deepcopy(left),
                    "contract_v1": copy.deepcopy(right),
                }
            )

    legacy_contests = _contest_summary(legacy)
    shadow_contests = _contest_summary(shadow)
    contest_differences: list[dict[str, Any]] = []
    for contest_id in sorted(set(legacy_contests) | set(shadow_contests)):
        left = legacy_contests.get(contest_id)
        right = shadow_contests.get(contest_id)
        if left != right:
            contest_differences.append(
                {
                    "contest_id": contest_id,
                    "legacy": copy.deepcopy(left),
                    "contract_v1": copy.deepcopy(right),
                }
            )

    legacy_candidate_count = sum(
        len(row["candidates"]) for row in legacy_contests.values()
    )
    shadow_candidate_count = sum(
        len(row["candidates"]) for row in shadow_contests.values()
    )
    parity_ok = (
        not office_differences
        and not contest_differences
        and len(legacy_contests) == len(shadow_contests)
        and legacy_candidate_count == shadow_candidate_count
    )

    result: dict[str, Any] = {
        "status": "PASS",
        "consumer_gate": "EV-RC1-FULL-SHADOW",
        "input_address": address,
        "parity_ok": parity_ok,
        "legacy_office_count": len(legacy_offices),
        "contract_v1_office_count": len(shadow_offices),
        "legacy_contest_count": len(legacy_contests),
        "contract_v1_contest_count": len(shadow_contests),
        "legacy_candidate_count": legacy_candidate_count,
        "contract_v1_candidate_count": shadow_candidate_count,
        "office_differences": office_differences,
        "contest_differences": contest_differences,
        "legacy_deterministic_sha256": legacy.get("deterministic_sha256"),
        "contract_v1_deterministic_sha256": shadow.get("deterministic_sha256"),
        "canonical_writes": 0,
    }
    result["deterministic_sha256"] = package_source.sha256_bytes(
        package_source.canonical_json_bytes(result)
    )
    return result
