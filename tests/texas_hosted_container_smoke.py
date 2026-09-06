#!/usr/bin/env python3
"""Live HTTP smoke controls for a locally running bounded Texas service container."""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urljoin

import requests

POSITIVE = "1100 Congress Ave, Austin, TX 78701"
NEGATIVE = "221 E Main St, Round Rock, TX 78664"
PROFILE = "tx_legislative_two_office_v0.1"


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
    require(health.get("service", {}).get("head_sha") == args.expected_head_sha, "health head drift")
    require(health.get("service", {}).get("environment") == args.expected_environment, "health environment drift")

    ready = get_json(args.base_url, "/readyz")
    require(ready.get("status") == "PASS", "readiness gate failed")
    service = ready.get("service", {})
    require(service.get("head_sha") == args.expected_head_sha, "readiness head drift")
    require(service.get("environment") == args.expected_environment, "readiness environment drift")
    require(service.get("profile_id") == PROFILE, "readiness profile drift")
    require(service.get("repository_activation") == "NOT_ACTIVATED", "unexpected repository activation")
    require(service.get("activation_authorized") is False, "unexpected activation authorization")
    require(service.get("canonical_writes") == 0, "unexpected canonical writes")
    checks = ready.get("checks", {})
    for check in ("geometry-governance-preflight", "package-profile-reconstruction", "public-identity-gate"):
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

    print("Texas hosted container smoke: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Texas hosted container smoke: FAIL: {exc}", file=sys.stderr)
        raise
