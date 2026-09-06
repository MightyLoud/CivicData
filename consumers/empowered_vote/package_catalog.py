#!/usr/bin/env python3
"""Governed Jurisdiction Package catalog for Empowered.Vote.

The catalog maps Civic GPS jurisdiction identities to package artifacts and
optional district adapters. It selects exactly one supported package for a live
geographic result and fails closed on unsupported or ambiguous matches.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from consumers.empowered_vote import live_civic_gps, package_source, production_profile

CATALOG_VERSION = "0.1"
DEFAULT_CATALOG = Path(__file__).with_name("package_catalog.v0.1.json")


class PackageCatalogError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def bindings_from_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = entry.get("district_bindings")
    if not isinstance(bindings, list):
        return []
    out = []
    for row in bindings:
        if not isinstance(row, dict):
            continue
        out.append({
            "binding_id": row.get("binding_id"),
            "package_jurisdiction_id": entry.get("package_jurisdiction_id"),
            "civic_gps_jurisdiction_id": entry.get("civic_gps_jurisdiction_id"),
            "district_adapter_id": row.get("adapter_id"),
            "district_division_map": row.get("district_division_map"),
        })
    return out


def load_catalog(path: str | Path = DEFAULT_CATALOG) -> dict[str, Any]:
    try:
        catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageCatalogError("PACKAGE_CATALOG_INVALID", str(exc)) from exc
    if not isinstance(catalog, dict) or str(catalog.get("catalog_version")) != CATALOG_VERSION:
        raise PackageCatalogError("PACKAGE_CATALOG_VERSION_UNSUPPORTED")
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise PackageCatalogError("PACKAGE_CATALOG_ENTRIES_INVALID")

    seen_entry_ids: set[str] = set()
    seen_geo_profiles: set[tuple[str, str]] = set()
    for row in entries:
        if not isinstance(row, dict):
            raise PackageCatalogError("PACKAGE_CATALOG_ENTRY_INVALID")
        for key in ("entry_id", "profile", "civic_gps_jurisdiction_id", "package_jurisdiction_id", "package_schema_version", "artifact"):
            if not row.get(key):
                raise PackageCatalogError("PACKAGE_CATALOG_ENTRY_FIELD_MISSING", key)
        entry_id = str(row["entry_id"])
        if entry_id in seen_entry_ids:
            raise PackageCatalogError("PACKAGE_CATALOG_ENTRY_ID_DUPLICATE", entry_id)
        seen_entry_ids.add(entry_id)
        geo_profile = (str(row["civic_gps_jurisdiction_id"]), str(row["profile"]))
        if geo_profile in seen_geo_profiles:
            raise PackageCatalogError("PACKAGE_CATALOG_ROUTE_DUPLICATE", ":".join(geo_profile))
        seen_geo_profiles.add(geo_profile)
        artifact = row["artifact"]
        if not isinstance(artifact, dict) or artifact.get("encoding") != "base64-parts":
            raise PackageCatalogError("PACKAGE_CATALOG_ARTIFACT_UNSUPPORTED", entry_id)
        for key in ("parts_glob", "archive_sha256", "package_subdir"):
            if not artifact.get(key):
                raise PackageCatalogError("PACKAGE_CATALOG_ARTIFACT_FIELD_MISSING", f"{entry_id}:{key}")

        binding = row.get("district_binding")
        multi_bindings = row.get("district_bindings")
        if binding is not None and multi_bindings is not None:
            raise PackageCatalogError("PACKAGE_CATALOG_BINDING_FORMS_CONFLICT", entry_id)
        if binding is not None:
            if not isinstance(binding, dict) or not binding.get("adapter_id") or not binding.get("division_template"):
                raise PackageCatalogError("PACKAGE_CATALOG_DISTRICT_BINDING_INVALID", entry_id)
            if "{district_key}" not in str(binding["division_template"]):
                raise PackageCatalogError("PACKAGE_CATALOG_DIVISION_TEMPLATE_INVALID", entry_id)

        profile_contract = row.get("production_profile")
        if profile_contract is not None:
            if not isinstance(profile_contract, dict) or set(profile_contract) != {"profile_id", "acceptance_receipt"}:
                raise PackageCatalogError("PACKAGE_CATALOG_PRODUCTION_PROFILE_INVALID", entry_id)
            if profile_contract.get("profile_id") != production_profile.PROFILE_ID:
                raise PackageCatalogError("PACKAGE_CATALOG_PRODUCTION_PROFILE_UNSUPPORTED", entry_id)
            if row.get("profile") != "state_legislative_representation":
                raise PackageCatalogError("PACKAGE_CATALOG_PRODUCTION_ROUTE_INVALID", entry_id)
            receipt = profile_contract.get("acceptance_receipt")
            if not isinstance(receipt, dict) or set(receipt) != {"path", "sha256"}
                    or not isinstance(receipt.get("path"), str)
                    or re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("sha256") or "")) is None:
                raise PackageCatalogError("PACKAGE_CATALOG_ACCEPTANCE_RECEIPT_INVALID", entry_id)
            try:
                production_profile._normalized_bindings(bindings_from_entry(row))
            except production_profile.ProductionProfileError as exc:
                raise PackageCatalogError(exc.code, exc.detail) from exc
        elif multi_bindings is not None:
            raise PackageCatalogError("PACKAGE_CATALOG_MULTI_BINDING_PROFILE_REQUIRED", entry_id)
    return catalog


def select_entry(catalog: dict[str, Any], civic_gps_result: dict[str, Any], *, profile: str = "municipal_essentials") -> dict[str, Any]:
    normalized = live_civic_gps.normalize_civic_gps_result("catalog-selection", civic_gps_result)
    if normalized.get("status") != "PASS":
        raise PackageCatalogError("PACKAGE_CATALOG_GEOGRAPHY_INVALID", str(normalized.get("error")))
    jurisdiction_ids = set(normalized["jurisdiction_ids"])
    matches = [
        row for row in catalog.get("entries", [])
        if row.get("profile") == profile and row.get("civic_gps_jurisdiction_id") in jurisdiction_ids
    ]
    if not matches:
        raise PackageCatalogError("PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")
    if len(matches) != 1:
        raise PackageCatalogError("PACKAGE_SELECTION_AMBIGUOUS", ",".join(sorted(str(x.get("entry_id")) for x in matches)))
    return matches[0]


def _acceptance_receipt(entry: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    contract = entry["production_profile"]["acceptance_receipt"]
    relative = Path(contract["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise PackageCatalogError("PACKAGE_CATALOG_ACCEPTANCE_PATH_INVALID", str(entry["entry_id"]))
    path = repo_root / relative
    if not path.is_file():
        raise PackageCatalogError("PACKAGE_CATALOG_ACCEPTANCE_RECEIPT_MISSING", str(entry["entry_id"]))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != contract["sha256"]:
        raise PackageCatalogError("PACKAGE_CATALOG_ACCEPTANCE_RECEIPT_SHA256_MISMATCH", digest)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageCatalogError("PACKAGE_CATALOG_ACCEPTANCE_RECEIPT_PARSE_FAILED", str(exc)) from exc
    if not isinstance(receipt, dict):
        raise PackageCatalogError("PACKAGE_CATALOG_ACCEPTANCE_RECEIPT_PARSE_FAILED", "expected JSON object")
    return receipt


def reconstruct_package(entry: dict[str, Any], repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    artifact = entry["artifact"]
    parts = sorted(root.glob(str(artifact["parts_glob"])))
    if not parts:
        raise PackageCatalogError("PACKAGE_ARTIFACT_PARTS_MISSING", str(entry["entry_id"]))
    encoded = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise PackageCatalogError("PACKAGE_ARTIFACT_BASE64_INVALID", str(entry["entry_id"])) from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != artifact["archive_sha256"]:
        raise PackageCatalogError("PACKAGE_ARTIFACT_SHA256_MISMATCH", digest)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "package.zip"
        archive.write_bytes(raw)
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(Path(tmp) / "expanded")
        except zipfile.BadZipFile as exc:
            raise PackageCatalogError("PACKAGE_ARTIFACT_ZIP_INVALID") from exc
        package_dir = Path(tmp) / "expanded" / str(artifact["package_subdir"])
        if entry.get("production_profile"):
            receipt = _acceptance_receipt(entry, root)
            try:
                package = production_profile.load_profile_package(
                    package_dir,
                    profile_id=entry["production_profile"]["profile_id"],
                    acceptance_receipt=receipt,
                    bindings=bindings_from_entry(entry),
                )
            except production_profile.ProductionProfileError as exc:
                raise PackageCatalogError(exc.code, exc.detail) from exc
        else:
            package = package_source.load_jurisdiction_package(package_dir)
    if package["jurisdiction"]["jurisdiction_id"] != entry["package_jurisdiction_id"]:
        raise PackageCatalogError("PACKAGE_CATALOG_JURISDICTION_DRIFT")
    if str(package["schema_version"]) != str(entry["package_schema_version"]):
        raise PackageCatalogError("PACKAGE_CATALOG_SCHEMA_DRIFT")
    return package


def binding_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "package_jurisdiction_id": entry["package_jurisdiction_id"],
        "civic_gps_jurisdiction_id": entry["civic_gps_jurisdiction_id"],
    }
    district = entry.get("district_binding")
    if district:
        binding["district_adapter_id"] = district["adapter_id"]
        binding["division_template"] = district["division_template"]
    return binding


def build_essentials_from_catalog(
    address: str,
    civic_gps_result: dict[str, Any],
    *,
    repo_root: str | Path,
    catalog_path: str | Path = DEFAULT_CATALOG,
    profile: str = "municipal_essentials",
) -> dict[str, Any]:
    try:
        catalog = load_catalog(catalog_path)
        entry = select_entry(catalog, civic_gps_result, profile=profile)
        if entry.get("production_profile"):
            raise PackageCatalogError("PACKAGE_PRODUCTION_PROFILE_NOT_FULL_ESSENTIALS", str(entry["entry_id"]))
        package = reconstruct_package(entry, repo_root)
    except PackageCatalogError as exc:
        return {
            "status": "FAIL-CLOSED",
            "consumer_gate": "EV-IMP-004",
            "input_address": address,
            "error": exc.code,
            "detail": exc.detail,
            "canonical_writes": 0,
        }

    model = live_civic_gps.build_essentials_from_civic_gps_result(
        package,
        address,
        civic_gps_result,
        binding=binding_from_entry(entry),
    )
    if model.get("status") == "PASS":
        model["consumer_gate"] = "EV-IMP-004"
        model["package_catalog_entry_id"] = entry["entry_id"]
        model.pop("deterministic_sha256", None)
        model["deterministic_sha256"] = package_source.sha256_bytes(package_source.canonical_json_bytes(model))
    return model
