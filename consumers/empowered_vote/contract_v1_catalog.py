#!/usr/bin/env python3
"""Shadow-route Empowered Vote through Representation Contract v1.

The existing Jurisdiction Package path remains authoritative during migration.
This module reconstructs the same governed package selected by the current
catalog, projects it into Contract v1, and consumes that contract in parallel.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.factory.export_representation import ExportError as FactoryExportError
from adapters.factory.export_representation import _legacy_division_ocdid, export_factory_package
from consumers.empowered_vote import (
    contract_v1,
    live_civic_gps,
    package_catalog,
    package_source,
    representation_catalog,
)


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": "EV-RC1-SHADOW",
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        out["detail"] = detail
    return out


def _generated_at(package: dict[str, Any]) -> str:
    """Use the newest deterministic observation date already carried by the package."""
    candidates: list[Any] = []
    jurisdiction = package.get("jurisdiction")
    if isinstance(jurisdiction, dict):
        candidates.extend(
            jurisdiction.get(key)
            for key in ("row_updated_at", "updated_at", "verified_as_of", "Verified_As_Of_ISO")
        )
    provenance = package.get("provenance")
    if isinstance(provenance, dict):
        for source in provenance.get("source_evidence", []):
            if not isinstance(source, dict):
                continue
            candidates.extend(
                source.get(key)
                for key in (
                    "accessed_at",
                    "verified_as_of",
                    "Verified_As_Of_ISO",
                    "row_updated_at",
                    "published_at",
                )
            )
    qa = package.get("qa")
    if isinstance(qa, dict):
        candidates.append(qa.get("checked_at"))
        for collection in ("checks", "address_tests"):
            for row in qa.get(collection, []):
                if isinstance(row, dict):
                    candidates.append(row.get("checked_at"))

    observed_dates: list[date] = []
    for value in candidates:
        if value in (None, ""):
            continue
        text = str(value).strip()
        try:
            observed_dates.append(datetime.fromisoformat(text.replace("Z", "+00:00")).date())
            continue
        except ValueError:
            pass
        try:
            observed_dates.append(date.fromisoformat(text[:10]))
        except ValueError:
            continue

    if not observed_dates:
        return "1970-01-01T00:00:00+00:00"
    latest = max(observed_dates)
    return datetime(latest.year, latest.month, latest.day, tzinfo=timezone.utc).isoformat()


def _factory_identifier(row: dict[str, Any], scheme: str) -> str | None:
    for identifier in row.get("identifiers") or []:
        if (
            isinstance(identifier, dict)
            and identifier.get("scheme") == scheme
            and identifier.get("id") not in (None, "")
        ):
            return str(identifier["id"])
    return None


def _division_ocdid_for_package_id(
    package: dict[str, Any],
    contract: dict[str, Any],
    division_id: str,
) -> str | None:
    """Resolve a legacy package division through the already-normalized Contract posts."""
    office_ids = {
        str(row.get("office_id") or row.get("id"))
        for row in package.get("records", {}).get("offices", [])
        if str(
            row.get("represented_division_id")
            or row.get("geography_id")
            or row.get("division_id")
            or ""
        )
        == division_id
    }
    if not office_ids:
        return None
    values = {
        str(post.get("division_ocdid"))
        for post in contract.get("posts", [])
        if _factory_identifier(post, "civicdata_factory_office") in office_ids
        and str(post.get("division_ocdid") or "").startswith("ocd-division/")
    }
    if len(values) != 1:
        return None
    return next(iter(values))


def _contract_binding(
    entry: dict[str, Any],
    package: dict[str, Any],
    contract: dict[str, Any],
    civic_gps_result: dict[str, Any],
) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "contract_jurisdiction_ocdid": (
            package.get("jurisdiction", {}).get("ocd_jurisdiction_id")
            or package.get("jurisdiction", {}).get("jurisdiction_ocdid")
        ),
        "civic_gps_jurisdiction_id": entry["civic_gps_jurisdiction_id"],
    }
    district = entry.get("district_binding")
    if not district:
        return binding

    normalized = live_civic_gps.normalize_civic_gps_result(
        "contract-v1-binding", civic_gps_result
    )
    if normalized.get("status") != "PASS":
        raise package_catalog.PackageCatalogError(
            "PACKAGE_CATALOG_GEOGRAPHY_INVALID", str(normalized.get("error"))
        )
    adapter_id = str(district["adapter_id"])
    district_key = normalized["district_assignments"].get(adapter_id)
    if district_key is None:
        raise package_catalog.PackageCatalogError(
            "CIVIC_GPS_REQUIRED_DISTRICT_MISSING", adapter_id
        )
    package_division_id = str(district["division_template"]).format(
        district_key=district_key
    )
    division_ocdid = _division_ocdid_for_package_id(
        package, contract, package_division_id
    )
    if division_ocdid is None:
        raise package_catalog.PackageCatalogError(
            "CONTRACT_V1_DIVISION_CROSSWALK_MISSING", package_division_id
        )
    binding["district_adapter_id"] = adapter_id
    binding["district_division_map"] = {str(district_key): division_ocdid}
    return binding


def build_representation_from_catalog(
    address: str,
    civic_gps_result: dict[str, Any],
    *,
    repo_root: str | Path,
    catalog_path: str | Path = package_catalog.DEFAULT_CATALOG,
    profile: str = "municipal_representation",
    identity_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one existing governed catalog entry through Contract v1."""
    try:
        catalog = package_catalog.load_catalog(catalog_path)
        entry = package_catalog.select_entry(catalog, civic_gps_result, profile=profile)
        if entry.get("countywide_profile") or entry.get("countywide_binding"):
            raise package_catalog.PackageCatalogError(
                "CONTRACT_V1_COUNTYWIDE_PROFILE_NOT_MIGRATED", str(entry["entry_id"])
            )
        if entry.get("production_profile") or entry.get("district_bindings"):
            raise package_catalog.PackageCatalogError(
                "CONTRACT_V1_MULTI_BINDING_PROFILE_NOT_MIGRATED", str(entry["entry_id"])
            )
        package = package_catalog.reconstruct_package(entry, repo_root)
        contract = export_factory_package(
            package,
            generated_at=_generated_at(package),
            governed_package=True,
            identity_registry=identity_registry,
        )
        binding = _contract_binding(entry, package, contract, civic_gps_result)
    except package_catalog.PackageCatalogError as exc:
        return _fail(address, exc.code, exc.detail)
    except FactoryExportError as exc:
        return _fail(address, "CONTRACT_V1_FACTORY_EXPORT_FAILED", str(exc))

    model = contract_v1.build_representation_from_civic_gps_result(
        contract,
        address,
        civic_gps_result,
        binding=binding,
    )
    if model.get("status") != "PASS" and model.get("error") == "CONTRACT_NOT_CERTIFIED":
        model["contract_certification"] = copy.deepcopy(contract.get("certification"))
    if model.get("status") == "PASS":
        model["consumer_gate"] = "EV-RC1-SHADOW"
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
        office_id = str(office.get("office_id") or office.get("post_id") or "")
        if not office_id:
            continue
        holders = office.get("holders")
        if not isinstance(holders, list):
            single = office.get("holder")
            holders = [single] if isinstance(single, dict) else []
        leadership = {
            str(role)
            for row in holders
            if isinstance(row, dict)
            for role in (row.get("leadership_roles") or [])
        }
        for row in holders:
            if isinstance(row, dict) and row.get("leadership_role"):
                leadership.add(str(row["leadership_role"]))
        raw_capacity = office.get("seat_capacity")
        out[office_id] = {
            "office_name": office.get("office_name"),
            "seat_capacity": int(raw_capacity) if raw_capacity not in (None, "") else None,
            "holders": sorted(
                str(row.get("name") or "")
                for row in holders
                if isinstance(row, dict)
            ),
            "leadership": sorted(leadership),
        }
    return out


def compare_shadow_to_legacy(
    address: str,
    civic_gps_result: dict[str, Any],
    *,
    repo_root: str | Path,
    catalog_path: str | Path = package_catalog.DEFAULT_CATALOG,
    profile: str = "municipal_representation",
    identity_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare voter-facing representation semantics without changing production routing."""
    if profile == "municipal_essentials":
        legacy = package_catalog.build_essentials_from_catalog(
            address,
            civic_gps_result,
            repo_root=repo_root,
            catalog_path=catalog_path,
            profile=profile,
        )
    else:
        legacy = representation_catalog.build_representation_from_catalog(
            address,
            civic_gps_result,
            repo_root=repo_root,
            catalog_path=catalog_path,
            profile=profile,
        )
    shadow = build_representation_from_catalog(
        address,
        civic_gps_result,
        repo_root=repo_root,
        catalog_path=catalog_path,
        profile=profile,
        identity_registry=identity_registry,
    )
    if legacy.get("status") != "PASS":
        return _fail(address, "LEGACY_REPRESENTATION_FAILED", str(legacy.get("error")))
    if shadow.get("status") != "PASS":
        return _fail(address, "CONTRACT_V1_SHADOW_FAILED", str(shadow.get("error")))

    legacy_offices = _office_summary(legacy)
    shadow_offices = _office_summary(shadow)
    differences: list[dict[str, Any]] = []
    for office_id in sorted(set(legacy_offices) | set(shadow_offices)):
        left = legacy_offices.get(office_id)
        right = shadow_offices.get(office_id)
        fields: dict[str, Any] = {}
        if left is None or right is None:
            fields["presence"] = {"legacy": left is not None, "contract_v1": right is not None}
        else:
            for field in ("office_name", "holders", "leadership"):
                if left[field] != right[field]:
                    fields[field] = {"legacy": left[field], "contract_v1": right[field]}
            if (
                left.get("seat_capacity") is not None
                and right.get("seat_capacity") is not None
                and left["seat_capacity"] != right["seat_capacity"]
            ):
                fields["seat_capacity"] = {
                    "legacy": left["seat_capacity"],
                    "contract_v1": right["seat_capacity"],
                }
        if fields:
            differences.append(
                {
                    "office_id": office_id,
                    "fields": fields,
                    "legacy": copy.deepcopy(left),
                    "contract_v1": copy.deepcopy(right),
                }
            )

    legacy_holder_count = sum(len(row["holders"]) for row in legacy_offices.values())
    shadow_holder_count = sum(len(row["holders"]) for row in shadow_offices.values())
    parity_ok = legacy_holder_count == shadow_holder_count and not differences
    result: dict[str, Any] = {
        "status": "PASS",
        "consumer_gate": "EV-RC1-SHADOW",
        "input_address": address,
        "parity_ok": parity_ok,
        "legacy_current_holder_count": legacy_holder_count,
        "contract_v1_current_holder_count": shadow_holder_count,
        "office_differences": differences,
        "legacy_deterministic_sha256": legacy.get("deterministic_sha256"),
        "contract_v1_deterministic_sha256": shadow.get("deterministic_sha256"),
        "canonical_writes": 0,
    }
    result["deterministic_sha256"] = package_source.sha256_bytes(
        package_source.canonical_json_bytes(result)
    )
    return result
