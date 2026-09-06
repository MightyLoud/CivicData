#!/usr/bin/env python3
"""Non-mutating activation-readiness gate for the bounded Texas legislative profile."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from civic_gps_extensions.legislative import validate_legislative_groups
from civic_gps_extensions.texas_geometry_governance import POLICY_ID as GEOMETRY_POLICY_ID
from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile
from tools.jurisdiction_package import canonical_json

READINESS_SCHEMA = "texas-activation-readiness/0.1"
EXPECTED_DEPLOYMENT_CHECKS = {
    "geometry-governance-preflight",
    "package-profile-reconstruction",
    "positive-both-bindings",
    "outside-slice-negative",
    "no-partial-projection",
    "public-identity-gate",
    "hosted-runtime-route",
}


class ActivationReadinessError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def _require(condition: bool, code: str, detail: str | None = None) -> None:
    if not condition:
        raise ActivationReadinessError(code, detail)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_json(value: Any) -> str:
    return _sha_bytes(canonical_json(value).encode("utf-8"))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _validate_catalog_entry(entry: dict[str, Any], *, package: dict[str, Any], acceptance_receipt: dict[str, Any],
                            package_sha256: str, artifact_archive_sha256: str) -> list[dict[str, Any]]:
    required = {
        "entry_id", "profile", "civic_gps_jurisdiction_id", "package_jurisdiction_id",
        "package_schema_version", "artifact", "district_bindings", "production_profile",
    }
    _require(isinstance(entry, dict) and set(entry) == required, "ACTIVATION_CATALOG_ENTRY_FIELDS_INVALID")
    _require(entry.get("profile") == "state_legislative_representation", "ACTIVATION_CATALOG_PROFILE_INVALID")
    jid = package["jurisdiction"]["jurisdiction_id"]
    _require(entry.get("civic_gps_jurisdiction_id") == jid and entry.get("package_jurisdiction_id") == jid,
             "ACTIVATION_CATALOG_JURISDICTION_DRIFT")
    _require(str(entry.get("package_schema_version")) == "0.1", "ACTIVATION_CATALOG_SCHEMA_INVALID")

    artifact = entry.get("artifact")
    _require(isinstance(artifact, dict) and set(artifact) == {"encoding", "parts_glob", "archive_sha256", "package_subdir"},
             "ACTIVATION_ARTIFACT_CONTRACT_INVALID")
    _require(artifact.get("encoding") == "base64-parts" and isinstance(artifact.get("parts_glob"), str)
             and bool(artifact["parts_glob"]) and isinstance(artifact.get("package_subdir"), str)
             and bool(artifact["package_subdir"]), "ACTIVATION_ARTIFACT_CONTRACT_INVALID")
    _require(_is_sha256(artifact_archive_sha256) and artifact.get("archive_sha256") == artifact_archive_sha256,
             "ACTIVATION_ARTIFACT_HASH_MISMATCH")

    profile = entry.get("production_profile")
    _require(isinstance(profile, dict) and set(profile) == {"profile_id", "acceptance_receipt"}
             and profile.get("profile_id") == production_profile.PROFILE_ID,
             "ACTIVATION_PRODUCTION_PROFILE_INVALID")
    receipt_ref = profile.get("acceptance_receipt")
    _require(isinstance(receipt_ref, dict) and set(receipt_ref) == {"path", "sha256"}
             and _safe_relative(receipt_ref.get("path")) and _is_sha256(receipt_ref.get("sha256")),
             "ACTIVATION_ACCEPTANCE_POINTER_INVALID")
    _require(receipt_ref["sha256"] == _sha_json(acceptance_receipt), "ACTIVATION_ACCEPTANCE_HASH_MISMATCH")

    bindings = package_catalog.bindings_from_entry(entry)
    try:
        production_profile._normalized_bindings(bindings)
        production_profile.validate_source_package(
            package,
            profile_id=production_profile.PROFILE_ID,
            acceptance_receipt=acceptance_receipt,
            package_sha256=package_sha256,
            bindings=bindings,
        )
    except production_profile.ProductionProfileError as exc:
        raise ActivationReadinessError(exc.code, exc.detail) from exc
    return bindings


def _validate_production_group(package: dict[str, Any], bindings: list[dict[str, Any]], group: dict[str, Any]) -> None:
    try:
        validate_legislative_groups([group])
    except ValueError as exc:
        raise ActivationReadinessError("ACTIVATION_LEGISLATIVE_GROUP_INVALID", str(exc)) from exc
    _require(group.get("scope") == "PRODUCTION_BOUNDED" and group.get("publication_eligible") is False,
             "ACTIVATION_LEGISLATIVE_SCOPE_INVALID")
    _require(group.get("geometry_governance") == {"policy_id": GEOMETRY_POLICY_ID},
             "ACTIVATION_GEOMETRY_POLICY_INVALID")
    normalized = production_profile._normalized_bindings(bindings)
    maps = {row["binding_id"]: row["district_division_map"] for row in normalized}
    house_id = maps["tx-house"]["49"]
    senate_id = maps["tx-senate"]["14"]
    expected_groups, expected_bindings = build_texas_production_configuration(
        package, house_division_id=house_id, senate_division_id=senate_id)
    _require(group == expected_groups[0], "ACTIVATION_LEGISLATIVE_GROUP_DRIFT")
    _require(production_profile._normalized_bindings(expected_bindings) == normalized,
             "ACTIVATION_LEGISLATIVE_BINDING_DRIFT")


def _validate_deployment(evidence: dict[str, Any], *, expected_head_sha: str) -> None:
    _require(isinstance(expected_head_sha, str) and re.fullmatch(r"[a-f0-9]{40}", expected_head_sha) is not None,
             "ACTIVATION_HEAD_SHA_INVALID")
    required = {"environment", "head_sha", "status", "profile_id", "checks"}
    _require(isinstance(evidence, dict) and set(evidence) == required, "ACTIVATION_DEPLOYMENT_EVIDENCE_INVALID")
    _require(evidence.get("environment") == "production" and evidence.get("status") == "PASS"
             and evidence.get("profile_id") == production_profile.PROFILE_ID,
             "ACTIVATION_DEPLOYMENT_NOT_PASSED")
    _require(evidence.get("head_sha") == expected_head_sha, "ACTIVATION_DEPLOYMENT_HEAD_DRIFT")
    checks = evidence.get("checks")
    _require(isinstance(checks, list) and all(isinstance(row, dict) and set(row) == {"check_id", "status"} for row in checks),
             "ACTIVATION_DEPLOYMENT_CHECKS_INVALID")
    ids = [row["check_id"] for row in checks]
    _require(len(ids) == len(set(ids)) and set(ids) == EXPECTED_DEPLOYMENT_CHECKS,
             "ACTIVATION_DEPLOYMENT_CHECK_COVERAGE_INVALID")
    _require(all(row["status"] == "PASS" for row in checks), "ACTIVATION_DEPLOYMENT_CHECK_FAILED")


def _assert_not_activated(default_catalog: dict[str, Any], default_extension: dict[str, Any], *, jurisdiction_id: str) -> None:
    entries = default_catalog.get("entries") if isinstance(default_catalog, dict) else None
    _require(isinstance(entries, list), "ACTIVATION_DEFAULT_CATALOG_INVALID")
    for row in entries:
        if not isinstance(row, dict):
            continue
        if row.get("package_jurisdiction_id") == jurisdiction_id and (
            row.get("profile") == "state_legislative_representation"
            or (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
        ):
            raise ActivationReadinessError("ACTIVATION_ALREADY_PRESENT_IN_CATALOG")

    groups = default_extension.get("legislative_boundary_overlays", []) if isinstance(default_extension, dict) else None
    _require(isinstance(groups, list), "ACTIVATION_DEFAULT_EXTENSION_INVALID")
    expected_adapters = {"DIST-TX-HOUSE-H2316", "DIST-TX-SENATE-S2168"}
    for group in groups:
        if not isinstance(group, dict):
            continue
        adapters = {str(row.get("adapter_id")) for row in group.get("district_adapters", []) if isinstance(row, dict)}
        if group.get("group_id") == "GEO-TX-LEGISLATIVE-TWO-DISTRICTS" or adapters & expected_adapters:
            raise ActivationReadinessError("ACTIVATION_ALREADY_PRESENT_IN_REGISTRY")


def build_readiness_receipt(*, package: dict[str, Any], acceptance_receipt: dict[str, Any], package_sha256: str,
                            artifact_archive_sha256: str, proposed_catalog_entry: dict[str, Any],
                            proposed_legislative_group: dict[str, Any], deployment_evidence: dict[str, Any],
                            expected_head_sha: str, default_catalog: dict[str, Any],
                            default_extension: dict[str, Any]) -> dict[str, Any]:
    """Prove a complete activation proposal without mutating catalog, registry, package, or deployment."""
    _require(isinstance(package, dict), "ACTIVATION_PACKAGE_INVALID")
    _require(_is_sha256(package_sha256) and package_sha256 == _sha_json(package),
             "ACTIVATION_PACKAGE_HASH_MISMATCH")
    bindings = _validate_catalog_entry(
        proposed_catalog_entry,
        package=package,
        acceptance_receipt=acceptance_receipt,
        package_sha256=package_sha256,
        artifact_archive_sha256=artifact_archive_sha256,
    )
    _validate_production_group(package, bindings, proposed_legislative_group)
    _validate_deployment(deployment_evidence, expected_head_sha=expected_head_sha)
    _assert_not_activated(default_catalog, default_extension, jurisdiction_id=package["jurisdiction"]["jurisdiction_id"])

    receipt = {
        "schema_version": READINESS_SCHEMA,
        "status": "READY_TO_ACTIVATE",
        "profile_id": production_profile.PROFILE_ID,
        "head_sha": expected_head_sha,
        "scope": {
            "coverage": "HOUSE_49_INTERSECTION_SENATE_14",
            "bindings_required": ["tx-house", "tx-senate"],
            "complete_jurisdiction": False,
            "full_essentials": False,
        },
        "inputs": {
            "package_sha256": package_sha256,
            "artifact_archive_sha256": artifact_archive_sha256,
            "acceptance_receipt_sha256": _sha_json(acceptance_receipt),
            "catalog_entry_sha256": _sha_json(proposed_catalog_entry),
            "legislative_group_sha256": _sha_json(proposed_legislative_group),
            "deployment_evidence_sha256": _sha_json(deployment_evidence),
        },
        "gates": {
            "production_profile": "PASS",
            "public_identity": "PASS",
            "geometry_policy_binding": "PASS",
            "production_deployment": "PASS",
            "default_catalog_inactive": "PASS",
            "default_registry_inactive": "PASS",
        },
        "activation_authorized": False,
        "repository_activation": "NOT_ACTIVATED",
        "canonical_writes": 0,
    }
    receipt["deterministic_sha256"] = _sha_json(receipt)
    return receipt


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ActivationReadinessError("ACTIVATION_JSON_OBJECT_REQUIRED", str(path))
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--acceptance-receipt", type=Path, required=True)
    parser.add_argument("--catalog-entry", type=Path, required=True)
    parser.add_argument("--legislative-group", type=Path, required=True)
    parser.add_argument("--deployment-evidence", type=Path, required=True)
    parser.add_argument("--artifact-archive-sha256", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--default-catalog", type=Path, default=package_catalog.DEFAULT_CATALOG)
    parser.add_argument("--default-extension", type=Path, default=Path("civic_gps_extensions/registry_bundles.v0.1.json"))
    args = parser.parse_args()

    package = _read_json(args.package)
    receipt = build_readiness_receipt(
        package=package,
        acceptance_receipt=_read_json(args.acceptance_receipt),
        package_sha256=_sha_bytes(args.package.read_bytes()),
        artifact_archive_sha256=args.artifact_archive_sha256,
        proposed_catalog_entry=_read_json(args.catalog_entry),
        proposed_legislative_group=_read_json(args.legislative_group),
        deployment_evidence=_read_json(args.deployment_evidence),
        expected_head_sha=args.head_sha,
        default_catalog=_read_json(args.default_catalog),
        default_extension=_read_json(args.default_extension),
    )
    print(canonical_json(receipt), end="")


if __name__ == "__main__":
    main()
