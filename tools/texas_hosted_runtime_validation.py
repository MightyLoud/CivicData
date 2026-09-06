#!/usr/bin/env python3
"""Validate an independently hosted bounded Texas production service over HTTPS."""
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
CONTRACT = Path("services/texas_bounded_api/service_contract.v0.1.json")
CHECK_IDS = (
    "geometry-governance-preflight",
    "package-profile-reconstruction",
    "positive-both-bindings",
    "outside-slice-negative",
    "no-partial-projection",
    "public-identity-gate",
    "hosted-runtime-route",
)


class HostedValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HostedValidationError(message)


def sha_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def validate_public_https(base_url: str) -> None:
    parsed = urlsplit(base_url)
    require(parsed.scheme == "https", "HOSTED_RUNTIME_HTTPS_REQUIRED")
    require(bool(parsed.hostname), "HOSTED_RUNTIME_HOST_REQUIRED")
    host = str(parsed.hostname).lower()
    require(host not in {"localhost", "localhost.localdomain"}, "HOSTED_RUNTIME_PUBLIC_HOST_REQUIRED")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    require(not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved),
            "HOSTED_RUNTIME_PUBLIC_HOST_REQUIRED")


def get_json(base_url: str, path: str, *, params=None) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    response = requests.get(url, params=params, timeout=45)
    require(response.status_code == 200, f"HOSTED_RUNTIME_HTTP_{response.status_code}:{path}")
    try:
        value = response.json()
    except ValueError as exc:
        raise HostedValidationError(f"HOSTED_RUNTIME_NON_JSON:{path}") from exc
    require(isinstance(value, dict), f"HOSTED_RUNTIME_JSON_OBJECT_REQUIRED:{path}")
    return value


def service_matches(service: dict[str, Any], *, head_sha: str, contract: dict[str, Any]) -> None:
    expected = contract["expected"]
    require(service.get("service_id") == contract["service_id"], "HOSTED_RUNTIME_SERVICE_ID_DRIFT")
    require(service.get("environment") == "production", "HOSTED_RUNTIME_ENVIRONMENT_NOT_PRODUCTION")
    require(service.get("head_sha") == head_sha, "HOSTED_RUNTIME_HEAD_DRIFT")
    require(service.get("profile_id") == PROFILE, "HOSTED_RUNTIME_PROFILE_DRIFT")
    require(service.get("jurisdiction_json_sha256") == expected["jurisdiction_json_sha256"],
            "HOSTED_RUNTIME_PACKAGE_HASH_DRIFT")
    require(service.get("archive_sha256") == expected["archive_sha256"], "HOSTED_RUNTIME_ARCHIVE_HASH_DRIFT")
    require(service.get("acceptance_receipt_sha256") == expected["acceptance_receipt_sha256"],
            "HOSTED_RUNTIME_ACCEPTANCE_FILE_HASH_DRIFT")
    require(service.get("acceptance_deterministic_sha256") == expected["acceptance_deterministic_sha256"],
            "HOSTED_RUNTIME_ACCEPTANCE_DIGEST_DRIFT")
    require(service.get("runtime_zip_sha256") == expected["runtime_zip_sha256"], "HOSTED_RUNTIME_ENGINE_HASH_DRIFT")
    require(service.get("repository_activation") == "NOT_ACTIVATED", "HOSTED_RUNTIME_UNEXPECTED_REPOSITORY_ACTIVATION")
    require(service.get("activation_authorized") is False, "HOSTED_RUNTIME_UNEXPECTED_ACTIVATION_AUTHORIZATION")
    require(service.get("canonical_writes") == 0, "HOSTED_RUNTIME_CANONICAL_WRITE_DRIFT")


def authoritative_holders(result: dict[str, Any]) -> list[dict[str, Any]]:
    holders: list[dict[str, Any]] = []
    for projection in result.get("projections", []):
        for office in projection.get("representation", {}).get("applicable_offices", []):
            holders.extend(row for row in office.get("holders", []) if isinstance(row, dict))
    return holders


def validate(base_url: str, *, head_sha: str, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_public_https(base_url)
    require(re.fullmatch(r"[a-f0-9]{40}", head_sha) is not None, "HOSTED_RUNTIME_EXPECTED_HEAD_INVALID")
    contract = read_json(repo_root / CONTRACT)
    routes = contract["routes"]
    positive_address = contract["hosted_validation"]["positive_address"]
    negative_address = contract["hosted_validation"]["negative_address"]

    health = get_json(base_url, routes["health"])
    require(health.get("status") == "PASS", "HOSTED_RUNTIME_HEALTH_FAILED")
    health_service = health.get("service", {})
    require(health_service.get("environment") == "production", "HOSTED_RUNTIME_HEALTH_NOT_PRODUCTION")
    require(health_service.get("head_sha") == head_sha, "HOSTED_RUNTIME_HEALTH_HEAD_DRIFT")

    ready = get_json(base_url, routes["readiness"])
    require(ready.get("status") == "PASS", "HOSTED_RUNTIME_READINESS_FAILED")
    service = ready.get("service", {})
    require(isinstance(service, dict), "HOSTED_RUNTIME_SERVICE_METADATA_MISSING")
    service_matches(service, head_sha=head_sha, contract=contract)
    ready_checks = ready.get("checks", {})
    for check in ("geometry-governance-preflight", "package-profile-reconstruction", "public-identity-gate"):
        require(ready_checks.get(check) == "PASS", f"HOSTED_RUNTIME_READINESS_CHECK_FAILED:{check}")

    positive = get_json(base_url, routes["representation"], params={"address": positive_address})
    require(positive.get("service") == service, "HOSTED_RUNTIME_POSITIVE_SERVICE_METADATA_DRIFT")
    result = positive.get("result", {})
    require(result.get("status") == "PASS", "HOSTED_RUNTIME_POSITIVE_FAILED")
    require(result.get("publication_eligible") is True, "HOSTED_RUNTIME_POSITIVE_PUBLICATION_GATE_FAILED")
    require(result.get("complete_jurisdiction") is False, "HOSTED_RUNTIME_POSITIVE_COMPLETENESS_DRIFT")
    require(result.get("canonical_writes") == 0, "HOSTED_RUNTIME_POSITIVE_CANONICAL_WRITE")
    require(len(result.get("projections", [])) == 2, "HOSTED_RUNTIME_POSITIVE_TWO_BINDINGS_REQUIRED")
    holders = authoritative_holders(result)
    require(len(holders) == 2, "HOSTED_RUNTIME_POSITIVE_HOLDER_COUNT_DRIFT")
    require({str(row.get("person_status") or "").upper() for row in holders} == {"AUTHORITATIVE"},
            "HOSTED_RUNTIME_PUBLIC_IDENTITY_FAILED")
    require({row.get("term_start") for row in holders} == {"2025-01-14"}, "HOSTED_RUNTIME_TERM_START_DRIFT")
    require({row.get("term_end") for row in holders} == {None}, "HOSTED_RUNTIME_TERM_END_INFERRED")

    negative = get_json(base_url, routes["representation"], params={"address": negative_address})
    require(negative.get("service") == service, "HOSTED_RUNTIME_NEGATIVE_SERVICE_METADATA_DRIFT")
    rejected = negative.get("result", {})
    require(rejected.get("status") == "FAIL-CLOSED", "HOSTED_RUNTIME_OUTSIDE_SLICE_NOT_FAIL_CLOSED")
    require("projections" not in rejected, "HOSTED_RUNTIME_PARTIAL_PROJECTION_LEAK")
    require(rejected.get("canonical_writes") == 0, "HOSTED_RUNTIME_NEGATIVE_CANONICAL_WRITE")

    checks = [{"check_id": check_id, "status": "PASS"} for check_id in CHECK_IDS]
    activation_evidence = {
        "environment": "production",
        "head_sha": head_sha,
        "status": "PASS",
        "profile_id": PROFILE,
        "checks": checks,
    }
    audit = {
        "schema_version": "texas-hosted-runtime-validation/0.1",
        "status": "PASS",
        "base_url": base_url.rstrip("/"),
        "head_sha": head_sha,
        "profile_id": PROFILE,
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
        "activation_authorized": False,
        "repository_activation": "NOT_ACTIVATED",
        "canonical_writes": 0,
    }
    audit["deterministic_sha256"] = sha_json(audit)
    return audit, activation_evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--activation-evidence-output", type=Path, required=True)
    args = parser.parse_args()

    audit, evidence = validate(
        args.base_url,
        head_sha=args.expected_head_sha.strip().lower(),
        repo_root=args.repo_root.resolve(),
    )
    for path, value in ((args.audit_output, audit), (args.activation_evidence_output, evidence)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical_json(value), encoding="utf-8")
    print(canonical_json(audit), end="")


if __name__ == "__main__":
    main()
