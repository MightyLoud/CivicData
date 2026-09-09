#!/usr/bin/env python3
"""Catalog-routed representation consumer for governed v0.1 packages."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import countywide_candidate, package_catalog, package_source, representation


def _catalog_failure(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": "EV-IMP-005",
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        out["detail"] = detail
    return out


def _bounded_profile_representation(package: dict[str, Any], address: str,
                                    civic_gps_result: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Compose both governed bindings publicly or return no partial projection."""
    bindings = package_catalog.bindings_from_entry(entry)
    projections: list[dict[str, Any]] = []
    seen_offices: set[str] = set()
    for binding in sorted(bindings, key=lambda row: str(row.get("binding_id"))):
        model = representation.build_representation_from_civic_gps_result(
            package, address, civic_gps_result, binding=binding
        )
        if model.get("status") != "PASS":
            return _catalog_failure(
                address,
                str(model.get("error") or "PRODUCTION_PROFILE_REPRESENTATION_FAILED"),
                str(binding.get("binding_id")),
            )
        office_ids = {str(row["office_id"]) for row in model.get("applicable_offices", [])}
        if seen_offices & office_ids:
            return _catalog_failure(address, "REPRESENTATION_BINDING_OVERLAP", str(binding.get("binding_id")))
        seen_offices.update(office_ids)
        projections.append({"binding_id": binding["binding_id"], "representation": model})

    if len(projections) != 2:
        return _catalog_failure(address, "PRODUCTION_PROFILE_TWO_BINDINGS_REQUIRED")
    result: dict[str, Any] = {
        "status": "PASS",
        "consumer_gate": "EV-IMP-005",
        "scope": "BOUND_BINDINGS_ONLY",
        "production_profile_id": entry["production_profile"]["profile_id"],
        "package_catalog_entry_id": entry["entry_id"],
        "projections": projections,
        "complete_jurisdiction": False,
        "publication_eligible": True,
        "canonical_writes": 0,
    }
    result["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(result))
    return result


def build_representation_from_catalog(
    address: str,
    civic_gps_result: dict[str, Any],
    *,
    repo_root: str | Path,
    catalog_path: str | Path = package_catalog.DEFAULT_CATALOG,
    profile: str = "municipal_representation",
    allow_candidate: bool = False,
) -> dict[str, Any]:
    try:
        catalog = package_catalog.load_catalog(catalog_path, allow_candidate=allow_candidate)
        entry = package_catalog.select_entry(catalog, civic_gps_result, profile=profile)
        package = package_catalog.reconstruct_package(entry, repo_root)
    except package_catalog.PackageCatalogError as exc:
        return _catalog_failure(address, exc.code, exc.detail)
    except package_source.PackageContractError as exc:
        return _catalog_failure(address, exc.code, exc.detail)

    if "countywide_binding" in entry:
        return countywide_candidate.build_representation(package, address, civic_gps_result, entry)

    if entry.get("production_profile"):
        return _bounded_profile_representation(package, address, civic_gps_result, entry)

    model = representation.build_representation_from_civic_gps_result(
        package,
        address,
        civic_gps_result,
        binding=package_catalog.binding_from_entry(entry),
    )
    if model.get("status") == "PASS":
        model["package_catalog_entry_id"] = entry["entry_id"]
        model.pop("deterministic_sha256", None)
        model["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(model))
    return model


def build_representation_from_live_address(
    address: str,
    *,
    repo_root: str | Path,
    resolver: Any | None = None,
    catalog_path: str | Path = package_catalog.DEFAULT_CATALOG,
    profile: str = "municipal_representation",
    allow_candidate: bool = False,
) -> dict[str, Any]:
    if resolver is None:
        try:
            from civic_gps_extensions.loader import load_resolver_with_extensions
            resolver = load_resolver_with_extensions(repo_root)
        except Exception as exc:
            return _catalog_failure(address, "CIVIC_GPS_RESOLVER_LOAD_FAILED", str(exc))
    try:
        geographic = resolver.resolve(address, observed_on=None)
    except Exception as exc:
        return _catalog_failure(address, "CIVIC_GPS_RESOLUTION_EXCEPTION", str(exc))
    return build_representation_from_catalog(
        address,
        geographic,
        repo_root=repo_root,
        catalog_path=catalog_path,
        profile=profile,
        allow_candidate=allow_candidate,
    )
