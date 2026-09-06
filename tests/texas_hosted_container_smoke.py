#!/usr/bin/env python3
"""Live HTTP smoke controls for the activated bounded Texas service container."""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urljoin

import requests

POSITIVE = "1100 Congress Ave, Austin, TX 78701"
NEGATIVE = "221 E Main St, Round Rock, TX 78664"
PROFILE = "tx_legislative_two_office_v0.1"
ENTRY_SHA = "1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189"
GROUP_SHA = "826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a"
ACTIVATION_SHA = "8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def get_json(base_url: str, path: str, *, params=None):
    response = requests.get(urljoin(base_url.rstrip("/") + "/", path.lstrip("/")), params=params, timeout=45)
    response.raise_for_status()
    body = response.json()
    require(isinstance(body, dict), f"non-object JSON from {path}")
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-environment", default="container-ci")
    args = parser.parse_args()

    health = get_json(args.base_url, "/healthz")
    require(health.get("status") == "PASS", "health gate failed")
    health_service = health.get("service", {})
    require(health_service.get("head_sha") == args.expected_head_sha, "health head drift")
    require(health_service.get("environment") == args.expected_environment, "health environment drift")
    require(health_service.get("repository_activation") == "ACTIVATED_BOUNDED", "health activation drift")

    ready = get_json(args.base_url, "/readyz")
    require(ready.get("status") == "PASS", "readiness gate failed")
    service = ready.get("service", {})
    require(service.get("head_sha") == args.expected_head_sha, "readiness head drift")
    require(service.get("environment") == args.expected_environment, "readiness environment drift")
    require(service.get("profile_id") == PROFILE, "readiness profile drift")
    require(service.get("service_id") == "civicdata-tx-legislative-two-office-v0.2", "service id drift")
    require(service.get("schema_version") == "texas-hosted-runtime-service/0.2", "service schema drift")
    require(service.get("repository_activation") == "ACTIVATED_BOUNDED", "repository activation drift")
    require(service.get("activation_authorized") is True, "activation authorization drift")
    require(service.get("release_authorized") is False, "release must remain unauthorized")
    require(service.get("publication_workflow_authorized") is False, "publication must remain unauthorized")
    require(service.get("catalog_entry_sha256") == ENTRY_SHA, "catalog hash drift")
    require(service.get("legislative_group_sha256") == GROUP_SHA, "registry hash drift")
    require(service.get("activation_receipt_deterministic_sha256") == ACTIVATION_SHA, "activation receipt drift")
    require(service.get("canonical_writes") == 0, "unexpected canonical writes")
    checks = ready.get("checks", {})
    for check in (
        "activation-receipt",
        "activated-default-catalog",
        "activated-default-registry",
        "geometry-governance-preflight",
        "package-profile-reconstruction",
        "public-identity-gate",
    ):
        require(checks.get(check) == "PASS", f"missing readiness check: {check}")

    positive = get_json(args.base_url, "/v1/representation", params={"address": POSITIVE})
    require(positive.get("service") == service, "positive service metadata drift")
    result = positive.get("result", {})
    require(result.get("status") == "PASS", "positive representation failed")
    require(result.get("publication_eligible") is True, "positive bounded publication gate failed")
    require(result.get("complete_jurisdiction") is False, "positive incorrectly claims complete jurisdiction")
    require(result.get("canonical_writes") == 0, "positive performed canonical writes")
    projections = result.get("projections", [])
    require(len(projections) == 2, "positive did not return both bindings")
    holders = []
    for projection in projections:
        offices = projection.get("representation", {}).get("applicable_offices", [])
        for office in offices:
            holders.extend(office.get("holders", []))
    require(len(holders) == 2, "positive holder count drift")
    require({str(row.get("person_status") or "").upper() for row in holders} == {"AUTHORITATIVE"},
            "positive identity status drift")
    require({row.get("term_start") for row in holders} == {"2025-01-14"}, "positive term start drift")
    require({row.get("term_end") for row in holders} == {None}, "positive actual end must remain unknown")

    negative = get_json(args.base_url, "/v1/representation", params={"address": NEGATIVE})
    require(negative.get("service") == service, "negative service metadata drift")
    rejected = negative.get("result", {})
    require(rejected.get("status") == "FAIL-CLOSED", "outside-slice address did not fail closed")
    require("projections" not in rejected, "outside-slice response leaked a partial projection")
    require(rejected.get("canonical_writes") == 0, "negative performed canonical writes")

    print("Texas activated hosted container smoke: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Texas activated hosted container smoke: FAIL: {exc}", file=sys.stderr)
        raise
