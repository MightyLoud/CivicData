#!/usr/bin/env python3
"""Validate the independently hosted post-activation bounded Texas runtime over HTTPS."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from tools.jurisdiction_package import canonical_json

PROFILE = "tx_legislative_two_office_v0.1"
CONTRACT = Path("services/texas_bounded_api/service_contract.v0.2.json")
CHECK_IDS = (
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
)


class PostActivationHostedValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PostActivationHostedValidationError(message)


def sha_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def validate_public_https(base_url: str) -> None:
    parsed = urlsplit(base_url)
    require(parsed.scheme == "https", "POST_ACTIVATION_HOSTED_HTTPS_REQUIRED")
    require(bool(parsed.hostname), "POST_ACTIVATION_HOSTED_HOST_REQUIRED")
    host = str(parsed.hostname).lower()
    require(host not in {"localhost", "localhost.localdomain"}, "POST_ACTIVATION_HOSTED_PUBLIC_HOST_REQUIRED")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    require(not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved),
            "POST_ACTIVATION_HOSTED_PUBLIC_HOST_REQUIRED")


def get_json(base_url: str, path: str, *, params=None) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    response = requests.get(url, params=params, timeout=45)
    require(response.status_code == 200, f"POST_ACTIVATION_HOSTED_HTTP_{response.status_code}:{path}")
    try:
        value = response.json()
    except ValueError as exc:
        raise PostActivationHostedValidationError(f"POST_ACTIVATION_HOSTED_NON_JSON:{path}") from exc
    require(isinstance(value, dict), f"POST_ACTIVATION_HOSTED_JSON_OBJECT_REQUIRED:{path}")
    return value


def service_matches(service: dict[str, Any], *, head_sha: str, contract: dict[str, Any]) -> None:
    expected = contract["expected"]
    require(service.get("service_id") == contract["service_id"], "POST_ACTIVATION_SERVICE_ID_DRIFT")
    require(service.get("schema_version") == contract["schema_version"], "POST_ACTIVATION_SERVICE_SCHEMA_DRIFT")
    require(service.get("environment") == "production", "POST_ACTIVATION_ENVIRONMENT_NOT_PRODUCTION")
    require(service.get("head_sha") == head_sha, "POST_ACTIVATION_HEAD_DRIFT")
    require(service.get("profile_id") == PROFILE, "POST_ACTIVATION_PROFILE_DRIFT")
    for key in (
        "jurisdiction_json_sha256",
        "archive_sha256",
        "acceptance_receipt_sha256",
        "acceptance_deterministic_sha256",
        "runtime_zip_sha256",
        "catalog_entry_sha256",
        "legislative_group_sha256",
        "activation_receipt_deterministic_sha256",
    ):
        require(service.get(key) == expected[key], f"POST_ACTIVATION_PIN_DRIFT:{key}")
    require(service.get("repository_activation") == "ACTIVATED_BOUNDED",
            "POST_ACTIVATION_REPOSITORY_STATE_DRIFT")
    require(service.get("activation_authorized") is True, "POST_ACTIVATION_AUTHORIZATION_DRIFT")
    require(service.get("release_authorized") is False, "POST_ACTIVATION_RELEASE_MUST_REMAIN_UNAUTHORIZED")
    require(service.get("publication_workflow_authorized") is False,
            "POST_ACTIVATION_PUBLICATION_MUST_REMAIN_UNAUTHORIZED")
    require(service.get("canonical_writes") == 0, "POST_ACTIVATION_CANONICAL_WRITE_DRIFT")


def authoritative_holders(result: dict[str, Any]) -> list[dict[str, Any]]:
    holders: list[dict[str, Any]] = []
    for projection in result.get("projections", []):
        for office in projection.get("representation", {}).get("applicable_offices", []):
            holders.extend(row for row in office.get("holders", []) if isinstance(row, dict))
    return holders


def validate(base_url: str, *, head_sha: str, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_public_https(base_url)
    require(re.fullmatch(r"[a-f0-9]{40}", head_sha) is not None, "POST_ACTIVATION_EXPECTED_HEAD_INVALID")
    contract = read_json(repo_root / CONTRACT)
    require(contract.get("schema_version") == "texas-hosted-runtime-service/0.2", "POST_ACTIVATION_CONTRACT_INVALID")
    routes = contract["routes"]
    positive_address = contract["hosted_validation"]["positive_address"]
    negative_address = contract["hosted_validation"]["negative_address"]

    health = get_json(base_url, routes["health"])
    require(health.get("status") == "PASS", "POST_ACTIVATION_HEALTH_FAILED")
    health_service = health.get("service", {})
    require(health_service.get("environment") == "production", "POST_ACTIVATION_HEALTH_NOT_PRODUCTION")
    require(health_service.get("head_sha") == head_sha, "POST_ACTIVATION_HEALTH_HEAD_DRIFT")
    require(health_service.get("repository_activation") == "ACTIVATED_BOUNDED",
            "POST_ACTIVATION_HEALTH_REPOSITORY_STATE_DRIFT")

    ready = get_json(base_url, routes["readiness"])
    require(ready.get("status") == "PASS", "POST_ACTIVATION_READINESS_FAILED")
    service = ready.get("service", {})
    require(isinstance(service, dict), "POST_ACTIVATION_SERVICE_METADATA_MISSING")
    service_matches(service, head_sha=head_sha, contract=contract)
    ready_checks = ready.get("checks", {})
    for check in (
        "activation-receipt",
        "activated-default-catalog",
        "activated-default-registry",
        "geometry-governance-preflight",
        "package-profile-reconstruction",
        "public-identity-gate",
    ):
        require(ready_checks.get(check) == "PASS", f"POST_ACTIVATION_READINESS_CHECK_FAILED:{check}")

    positive = get_json(base_url, routes["representation"], params={"address": positive_address})
    require(positive.get("service") == service, "POST_ACTIVATION_POSITIVE_SERVICE_METADATA_DRIFT")
    result = positive.get("result", {})
    require(result.get("status") == "PASS", "POST_ACTIVATION_POSITIVE_FAILED")
    require(result.get("publication_eligible") is True, "POST_ACTIVATION_POSITIVE_PUBLICATION_GATE_FAILED")
    require(result.get("complete_jurisdiction") is False, "POST_ACTIVATION_POSITIVE_COMPLETENESS_DRIFT")
    require(result.get("canonical_writes") == 0, "POST_ACTIVATION_POSITIVE_CANONICAL_WRITE")
    require(len(result.get("projections", [])) == 2, "POST_ACTIVATION_POSITIVE_TWO_BINDINGS_REQUIRED")
    holders = authoritative_holders(result)
    require(len(holders) == 2, "POST_ACTIVATION_POSITIVE_HOLDER_COUNT_DRIFT")
    require({str(row.get("person_status") or "").upper() for row in holders} == {"AUTHORITATIVE"},
            "POST_ACTIVATION_PUBLIC_IDENTITY_FAILED")
    require({row.get("term_start") for row in holders} == {"2025-01-14"}, "POST_ACTIVATION_TERM_START_DRIFT")
    require({row.get("term_end") for row in holders} == {None}, "POST_ACTIVATION_TERM_END_INFERRED")

    negative = get_json(base_url, routes["representation"], params={"address": negative_address})
    require(negative.get("service") == service, "POST_ACTIVATION_NEGATIVE_SERVICE_METADATA_DRIFT")
    rejected = negative.get("result", {})
    require(rejected.get("status") == "FAIL-CLOSED", "POST_ACTIVATION_OUTSIDE_SLICE_NOT_FAIL_CLOSED")
    require("projections" not in rejected, "POST_ACTIVATION_PARTIAL_PROJECTION_LEAK")
    require(rejected.get("canonical_writes") == 0, "POST_ACTIVATION_NEGATIVE_CANONICAL_WRITE")

    checks = [{"check_id": check_id, "status": "PASS"} for check_id in CHECK_IDS]
    evidence = {
        "schema_version": "texas-post-activation-hosted-evidence/0.1",
        "environment": "production",
        "head_sha": head_sha,
        "status": "PASS",
        "profile_id": PROFILE,
        "repository_activation": "ACTIVATED_BOUNDED",
        "checks": checks,
        "service_contract_sha256": service["service_contract_sha256"],
        "catalog_entry_sha256": service["catalog_entry_sha256"],
        "legislative_group_sha256": service["legislative_group_sha256"],
        "activation_receipt_deterministic_sha256": service["activation_receipt_deterministic_sha256"],
        "release_authorized": False,
        "publication_workflow_authorized": False,
        "canonical_writes": 0,
    }
    evidence["deterministic_sha256"] = sha_json(evidence)
    audit = {
        "schema_version": "texas-post-activation-hosted-validation/0.1",
        "status": "PASS",
        "base_url": base_url.rstrip("/"),
        "head_sha": head_sha,
        "profile_id": PROFILE,
        "repository_activation": "ACTIVATED_BOUNDED",
        "service": service,
        "checks": checks,
        "positive": {
            "address": positive_address,
            "projection_count": 2,
            "holder_count": 2,
            "deterministic_sha256": result.get("deterministic_sha256"),
        },
        "negative": {
            "address": negative_address,
            "status": rejected.get("status"),
            "error": rejected.get("error"),
            "projections_returned": 0,
        },
        "release_authorized": False,
        "publication_workflow_authorized": False,
        "canonical_writes": 0,
    }
    audit["deterministic_sha256"] = sha_json(audit)
    return audit, evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--release-evidence-output", type=Path, required=True)
    args = parser.parse_args()

    audit, evidence = validate(
        args.base_url,
        head_sha=args.expected_head_sha.strip().lower(),
        repo_root=args.repo_root.resolve(),
    )
    for path, value in ((args.audit_output, audit), (args.release_evidence_output, evidence)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical_json(value), encoding="utf-8")
    print(canonical_json(audit), end="")


if __name__ == "__main__":
    main()
