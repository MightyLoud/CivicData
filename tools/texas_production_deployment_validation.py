#!/usr/bin/env python3
"""Exact-head live validation for the bounded Texas production candidate.

This executes the production-bounded geography and governed package/profile route
without changing the default catalog or registry. A GitHub Actions runner is not
a hosted production service, so hosted-runtime-route remains BLOCKED until an
actual production endpoint/deployment target is independently available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from datetime import date
from typing import Any

from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile, representation_catalog
from tools.jurisdiction_package import canonical_json

PROFILE = production_profile.PROFILE_ID
DATA_REL = Path("data/packages/tx/legislative")
META_NAME = "successor-package-metadata-v0.1.json"
RECEIPT_NAME = "acceptance-v0.1.json"
PARTS_GLOB = "Tx_Legislative_Two_Office_v0.1.zip.b64.part*"
PACKAGE_SUBDIR = "Tx_Legislative_Two_Office_v0.1/package"
TEXAS_CAPITOL = "1100 Congress Ave, Austin, TX 78701"
ROUND_ROCK_CITY_HALL = "221 E Main St, Round Rock, TX 78664"
CHECK_IDS = (
    "geometry-governance-preflight",
    "package-profile-reconstruction",
    "positive-both-bindings",
    "outside-slice-negative",
    "no-partial-projection",
    "public-identity-gate",
    "hosted-runtime-route",
)


class DeploymentValidationError(RuntimeError):
    pass


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_json(value: Any) -> str:
    return _sha_bytes(canonical_json(value).encode("utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DeploymentValidationError(f"expected JSON object: {path}")
    return value


def _entry(package: dict[str, Any], receipt: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    jid = package["jurisdiction"]["jurisdiction_id"]
    bindings = []
    for row in receipt["scope"]["bindings"]:
        bindings.append({
            "binding_id": row["binding_id"],
            "adapter_id": row["district_adapter_id"],
            "district_division_map": row["district_division_map"],
        })
    return {
        "entry_id": "tx-legislative-two-office-v0.1-candidate",
        "profile": "state_legislative_representation",
        "civic_gps_jurisdiction_id": jid,
        "package_jurisdiction_id": jid,
        "package_schema_version": "0.1",
        "artifact": {
            "encoding": "base64-parts",
            "parts_glob": str(DATA_REL / PARTS_GLOB),
            "archive_sha256": meta["archive_sha256"],
            "package_subdir": PACKAGE_SUBDIR,
        },
        "district_bindings": bindings,
        "production_profile": {
            "profile_id": PROFILE,
            "acceptance_receipt": {
                "path": str(DATA_REL / RECEIPT_NAME),
                "sha256": meta["acceptance_receipt_sha256"],
            },
        },
    }


def _check(statuses: dict[str, str], details: dict[str, Any], check_id: str, status: str, **detail: Any) -> None:
    statuses[check_id] = status
    details[check_id] = detail


def execute(repo_root: Path, *, head_sha: str, observed_on: str) -> dict[str, Any]:
    if re.fullmatch(r"[a-f0-9]{40}", head_sha) is None:
        raise DeploymentValidationError("head SHA must be an exact 40-character lowercase SHA")
    data = repo_root / DATA_REL
    meta = _read_json(data / META_NAME)
    receipt = _read_json(data / RECEIPT_NAME)

    # Read the successor package through the real production-profile catalog path.
    # The temporary catalog is proposal-only and never overwrites the default file.
    raw_entry_stub = {
        "catalog_version": "0.1",
        "entries": [],
    }
    statuses: dict[str, str] = {}
    details: dict[str, Any] = {}

    # First reconstruct the package using a proposal entry whose artifact and receipt
    # hashes are the committed successor pins.
    # We need the jurisdiction ID for the proposal; recover it from the already
    # hash-verified package by using the committed receipt scope.
    jid = receipt["scope"]["jurisdiction_id"]
    placeholder_package = {"jurisdiction": {"jurisdiction_id": jid}}
    proposal = _entry(placeholder_package, receipt, meta)
    raw_entry_stub["entries"] = [proposal]
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        catalog_path = temp_root / "candidate-catalog.json"
        catalog_path.write_text(canonical_json(raw_entry_stub), encoding="utf-8")
        try:
            catalog = package_catalog.load_catalog(catalog_path)
            selected_entry = catalog["entries"][0]
            package = package_catalog.reconstruct_package(selected_entry, repo_root)
        except Exception as exc:
            _check(statuses, details, "package-profile-reconstruction", "FAIL", error=str(exc))
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)

        package_bytes = canonical_json(package).encode("utf-8")
        if _sha_bytes(package_bytes) != meta["jurisdiction_json_sha256"]:
            _check(statuses, details, "package-profile-reconstruction", "FAIL", error="jurisdiction hash drift")
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        _check(statuses, details, "package-profile-reconstruction", "PASS",
               jurisdiction_json_sha256=meta["jurisdiction_json_sha256"], archive_sha256=meta["archive_sha256"])

        people = package["records"]["people"]
        identity = {
            str(row.get("person_id") or row.get("id")):
            str(row.get("person_status") or row.get("identity_resolution_status") or "").upper()
            for row in people
        }
        if identity != receipt["person_identity_status"] or set(identity.values()) != {"AUTHORITATIVE"}:
            _check(statuses, details, "public-identity-gate", "FAIL", identity=identity)
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        _check(statuses, details, "public-identity-gate", "PASS", identity=identity)

        divisions = {row["division_kind"]: row["division_id"] for row in package["records"]["divisions"]}
        groups, bindings = build_texas_production_configuration(
            package, house_division_id=divisions["SLDL"], senate_division_id=divisions["SLDU"])
        if bindings != receipt["scope"]["bindings"]:
            raise DeploymentValidationError("production binding drift from successor receipt")

        # Loading the resolver performs live geometry marker governance before any
        # address geocode. This is the exact production-bounded runtime contract.
        try:
            resolver = load_resolver_with_extensions(repo_root, legislative_overlays=groups, timeout_seconds=30.0)
        except Exception as exc:
            _check(statuses, details, "geometry-governance-preflight", "FAIL", error=str(exc))
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        _check(statuses, details, "geometry-governance-preflight", "PASS",
               policy_id=groups[0]["geometry_governance"]["policy_id"])

        # Exact positive live route through production-bounded geography + proposed
        # governed catalog/profile. This is a candidate execution, not a deployment.
        try:
            positive_gps = resolver.resolve(TEXAS_CAPITOL, observed_on=observed_on)
            positive = representation_catalog.build_representation_from_catalog(
                TEXAS_CAPITOL,
                positive_gps,
                repo_root=repo_root,
                catalog_path=catalog_path,
                profile="state_legislative_representation",
            )
        except Exception as exc:
            _check(statuses, details, "positive-both-bindings", "FAIL", error=str(exc))
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        if positive.get("status") != "PASS" or len(positive.get("projections", [])) != 2:
            _check(statuses, details, "positive-both-bindings", "FAIL", result=positive)
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        _check(statuses, details, "positive-both-bindings", "PASS",
               address=TEXAS_CAPITOL,
               projection_count=2,
               publication_eligible=positive.get("publication_eligible"),
               complete_jurisdiction=positive.get("complete_jurisdiction"),
               deterministic_sha256=positive.get("deterministic_sha256"))

        try:
            negative_gps = resolver.resolve(ROUND_ROCK_CITY_HALL, observed_on=observed_on)
            negative = representation_catalog.build_representation_from_catalog(
                ROUND_ROCK_CITY_HALL,
                negative_gps,
                repo_root=repo_root,
                catalog_path=catalog_path,
                profile="state_legislative_representation",
            )
        except Exception as exc:
            _check(statuses, details, "outside-slice-negative", "FAIL", error=str(exc))
            _check(statuses, details, "no-partial-projection", "FAIL", error=str(exc))
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        if negative.get("status") != "FAIL-CLOSED":
            _check(statuses, details, "outside-slice-negative", "FAIL", result=negative)
            _check(statuses, details, "no-partial-projection", "FAIL", result=negative)
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        _check(statuses, details, "outside-slice-negative", "PASS",
               address=ROUND_ROCK_CITY_HALL, error=negative.get("error"))
        if "projections" in negative:
            _check(statuses, details, "no-partial-projection", "FAIL", result=negative)
            return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)
        _check(statuses, details, "no-partial-projection", "PASS", projections_returned=0)

    # No deployable HTTP service, deployment workflow, or configured production
    # target exists in this repository. Do not relabel the Actions runner as hosted.
    _check(statuses, details, "hosted-runtime-route", "BLOCKED",
           blocker="NO_HOSTED_PRODUCTION_RUNTIME_TARGET_CONFIGURED",
           note="Live candidate execution passed in CI, but CI is not a hosted production route.")
    return _report(repo_root, head_sha, observed_on, statuses, details, meta, receipt)


def _report(repo_root: Path, head_sha: str, observed_on: str, statuses: dict[str, str],
            details: dict[str, Any], meta: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    for check_id in CHECK_IDS:
        if check_id not in statuses:
            statuses[check_id] = "NOT_RUN"
            details.setdefault(check_id, {})
    non_host_failures = [cid for cid in CHECK_IDS[:-1] if statuses[cid] != "PASS"]
    hosted = statuses["hosted-runtime-route"]
    if non_host_failures:
        status = "FAIL"
    elif hosted == "PASS":
        status = "PASS"
    else:
        status = "BLOCKED_HOSTED_RUNTIME_ROUTE"
    report: dict[str, Any] = {
        "schema_version": "texas-production-deployment-validation/0.1",
        "environment": "EXACT_HEAD_CI_CANDIDATE_NOT_HOSTED_PRODUCTION",
        "head_sha": head_sha,
        "observed_on": observed_on,
        "status": status,
        "profile_id": PROFILE,
        "checks": [{"check_id": cid, "status": statuses[cid]} for cid in CHECK_IDS],
        "details": details,
        "inputs": {
            "jurisdiction_json_sha256": meta["jurisdiction_json_sha256"],
            "archive_sha256": meta["archive_sha256"],
            "acceptance_deterministic_sha256": receipt["deterministic_sha256"],
        },
        "activation_authorized": False,
        "repository_activation": "NOT_ACTIVATED",
        "canonical_writes": 0,
    }
    report["deterministic_sha256"] = _sha_json(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--observed-on", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = execute(args.repo_root.resolve(), head_sha=args.head_sha, observed_on=args.observed_on)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(report), encoding="utf-8")
    print(canonical_json(report), end="")
    # Expected fail-closed blocker is a successful validation run. Any other failure
    # makes CI red.
    if report["status"] == "FAIL":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
