#!/usr/bin/env python3
"""Non-mutating release-readiness gate for the activated bounded Texas runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile
from tools.jurisdiction_package import canonical_json

SCHEMA = "texas-release-readiness/0.1"
PROFILE = "tx_legislative_two_office_v0.1"
GROUP_ID = "GEO-TX-LEGISLATIVE-TWO-DISTRICTS"
EXPECTED_CHECKS = {
    "activation-receipt",
    "activated-default-catalog",
    "activated-default-registry",
    "geometry-governance-preflight",
    "package-profile-reconstruction",
    "positive-both-bindings",
    "outside-slice-negative",
    "no-partial-projection",
    "public-identity-gate",
    "hosted-runtime-route",
}


class ReleaseReadinessError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def require(condition: bool, code: str, detail: str | None = None) -> None:
    if not condition:
        raise ReleaseReadinessError(code, detail)


def sha_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "RELEASE_READINESS_JSON_OBJECT_REQUIRED", str(path))
    return value


def validate_hosted_evidence(evidence: dict[str, Any], *, expected_head_sha: str,
                             contract: dict[str, Any]) -> None:
    require(re.fullmatch(r"[a-f0-9]{40}", expected_head_sha) is not None, "RELEASE_READINESS_HEAD_INVALID")
    required = {
        "schema_version", "environment", "head_sha", "status", "profile_id",
        "repository_activation", "checks", "service_contract_sha256",
        "catalog_entry_sha256", "legislative_group_sha256",
        "activation_receipt_deterministic_sha256", "release_authorized",
        "publication_workflow_authorized", "canonical_writes", "deterministic_sha256",
    }
    require(set(evidence) == required, "RELEASE_READINESS_HOSTED_EVIDENCE_FIELDS_INVALID")
    recorded = evidence["deterministic_sha256"]
    core = dict(evidence)
    core.pop("deterministic_sha256")
    require(sha_json(core) == recorded, "RELEASE_READINESS_HOSTED_EVIDENCE_DIGEST_INVALID")
    require(evidence.get("schema_version") == "texas-post-activation-hosted-evidence/0.1",
            "RELEASE_READINESS_HOSTED_EVIDENCE_SCHEMA_INVALID")
    require(evidence.get("environment") == "production" and evidence.get("status") == "PASS",
            "RELEASE_READINESS_HOSTED_RUNTIME_NOT_PASSED")
    require(evidence.get("head_sha") == expected_head_sha, "RELEASE_READINESS_HOSTED_HEAD_DRIFT")
    require(evidence.get("profile_id") == PROFILE, "RELEASE_READINESS_PROFILE_DRIFT")
    require(evidence.get("repository_activation") == "ACTIVATED_BOUNDED",
            "RELEASE_READINESS_REPOSITORY_STATE_DRIFT")
    require(evidence.get("release_authorized") is False
            and evidence.get("publication_workflow_authorized") is False
            and evidence.get("canonical_writes") == 0,
            "RELEASE_READINESS_PREMATURE_RELEASE_STATE")
    checks = evidence.get("checks")
    require(isinstance(checks, list) and all(
        isinstance(row, dict) and set(row) == {"check_id", "status"} for row in checks
    ), "RELEASE_READINESS_HOSTED_CHECKS_INVALID")
    ids = [row["check_id"] for row in checks]
    require(len(ids) == len(set(ids)) and set(ids) == EXPECTED_CHECKS,
            "RELEASE_READINESS_HOSTED_CHECK_COVERAGE_INVALID")
    require(all(row["status"] == "PASS" for row in checks), "RELEASE_READINESS_HOSTED_CHECK_FAILED")
    expected = contract["expected"]
    require(evidence.get("catalog_entry_sha256") == expected["catalog_entry_sha256"],
            "RELEASE_READINESS_CATALOG_HASH_DRIFT")
    require(evidence.get("legislative_group_sha256") == expected["legislative_group_sha256"],
            "RELEASE_READINESS_REGISTRY_HASH_DRIFT")
    require(evidence.get("activation_receipt_deterministic_sha256")
            == expected["activation_receipt_deterministic_sha256"],
            "RELEASE_READINESS_ACTIVATION_RECEIPT_DRIFT")


def build_release_readiness(*, repo_root: Path, hosted_evidence: dict[str, Any],
                            expected_head_sha: str, runtime_merged: bool) -> dict[str, Any]:
    contract = read_json(repo_root / "services/texas_bounded_api/service_contract.v0.2.json")
    require(contract.get("schema_version") == "texas-hosted-runtime-service/0.2",
            "RELEASE_READINESS_SERVICE_CONTRACT_INVALID")
    require(contract.get("repository_activation") == "ACTIVATED_BOUNDED"
            and contract.get("release_authorized") is False
            and contract.get("publication_workflow_authorized") is False,
            "RELEASE_READINESS_SERVICE_BOUNDARY_INVALID")

    activation = read_json(repo_root / "data/packages/tx/legislative/activation-v0.1.json")
    require(activation.get("status") == "ACTIVATED_BOUNDED"
            and activation.get("repository_activation") == "ACTIVATED_BOUNDED"
            and activation.get("activation_authorized") is True,
            "RELEASE_READINESS_ACTIVATION_INVALID")
    boundaries = activation.get("boundaries") or {}
    require(boundaries.get("release_authorized") is False
            and boundaries.get("publication_workflow_authorized") is False
            and boundaries.get("canonical_writes") == 0,
            "RELEASE_READINESS_ACTIVATION_BOUNDARY_INVALID")
    require(activation.get("deterministic_sha256") == contract["expected"]["activation_receipt_deterministic_sha256"],
            "RELEASE_READINESS_ACTIVATION_DIGEST_DRIFT")

    catalog = package_catalog.load_catalog(repo_root / "consumers/empowered_vote/package_catalog.v0.1.json")
    matches = [
        row for row in catalog["entries"]
        if row.get("profile") == "state_legislative_representation"
        and (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
    ]
    require(len(matches) == 1, "RELEASE_READINESS_CATALOG_CARDINALITY_INVALID", str(len(matches)))
    entry = matches[0]
    require(entry == contract["catalog_entry"], "RELEASE_READINESS_CATALOG_DRIFT")
    require(sha_json(entry) == contract["expected"]["catalog_entry_sha256"],
            "RELEASE_READINESS_CATALOG_HASH_DRIFT")

    package = package_catalog.reconstruct_package(entry, repo_root)
    require(sha_json(package) == contract["expected"]["jurisdiction_json_sha256"],
            "RELEASE_READINESS_PACKAGE_HASH_DRIFT")
    identities = {
        str(row.get("person_status") or row.get("identity_resolution_status") or "").upper()
        for row in package["records"]["people"]
    }
    require(identities == {"AUTHORITATIVE"}, "RELEASE_READINESS_PUBLIC_IDENTITY_INVALID")
    divisions = {row["division_kind"]: row["division_id"] for row in package["records"]["divisions"]}
    groups, _ = build_texas_production_configuration(
        package,
        house_division_id=divisions["SLDL"],
        senate_division_id=divisions["SLDU"],
    )
    registry = read_json(repo_root / "civic_gps_extensions/registry_bundles.v0.1.json")
    active = [row for row in registry.get("legislative_boundary_overlays", []) if row.get("group_id") == GROUP_ID]
    require(len(active) == 1 and active[0] == groups[0], "RELEASE_READINESS_REGISTRY_DRIFT")
    require(sha_json(active[0]) == contract["expected"]["legislative_group_sha256"],
            "RELEASE_READINESS_REGISTRY_HASH_DRIFT")

    validate_hosted_evidence(hosted_evidence, expected_head_sha=expected_head_sha, contract=contract)

    status = "READY_FOR_RELEASE_AUTHORIZATION" if runtime_merged else "READY_FOR_RUNTIME_MERGE"
    receipt = {
        "schema_version": SCHEMA,
        "status": status,
        "profile_id": PROFILE,
        "head_sha": expected_head_sha,
        "repository_activation": "ACTIVATED_BOUNDED",
        "runtime_merged": bool(runtime_merged),
        "scope": {
            "coverage": "HOUSE_49_INTERSECTION_SENATE_14",
            "bindings_required": ["tx-house", "tx-senate"],
            "complete_jurisdiction": False,
            "full_essentials": False,
            "elections": False,
        },
        "gates": {
            "activation_receipt": "PASS",
            "activated_default_catalog": "PASS",
            "activated_default_registry": "PASS",
            "post_activation_hosted_runtime": "PASS",
            "public_identity": "PASS",
            "geometry_governance": "PASS",
            "runtime_merge": "PASS" if runtime_merged else "REQUIRED",
        },
        "inputs": {
            "package_sha256": contract["expected"]["jurisdiction_json_sha256"],
            "catalog_entry_sha256": contract["expected"]["catalog_entry_sha256"],
            "legislative_group_sha256": contract["expected"]["legislative_group_sha256"],
            "activation_receipt_sha256": contract["expected"]["activation_receipt_deterministic_sha256"],
            "post_activation_hosted_evidence_sha256": hosted_evidence["deterministic_sha256"],
            "service_contract_sha256": hosted_evidence["service_contract_sha256"],
        },
        "release_authorized": False,
        "publication_workflow_authorized": False,
        "canonical_writes": 0,
    }
    receipt["deterministic_sha256"] = sha_json(receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--hosted-evidence", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--runtime-merged", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = build_release_readiness(
        repo_root=args.repo_root.resolve(),
        hosted_evidence=read_json(args.hosted_evidence),
        expected_head_sha=args.head_sha.strip().lower(),
        runtime_merged=args.runtime_merged,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(canonical_json(receipt), encoding="utf-8")
    print(canonical_json(receipt), end="")


if __name__ == "__main__":
    main()
