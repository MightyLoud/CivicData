#!/usr/bin/env python3
"""Verify the governed bounded-Texas release authorization chain without publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.jurisdiction_package import canonical_json

DATA = Path("data/packages/tx/legislative")
HOSTED_SHA = "ed079fdfade76c06271f4b6be57fc669db7586b2ad66dc56ec13e3694f2abfb6"
READINESS_SHA = "abeacad639da187818748c5af70e9df05fab27bf52101d270b7cd9c133f0c031"
AUTH_SHA = "7bf9a8ecf9c101e9faee4389f925f469fd1d37934cc1d3dc9bfd6a890989d6de"
RUNTIME_MAIN_SHA = "2570cba11d218ab32588a30ef6c43a7fce5c2f7c"
PROFILE = "tx_legislative_two_office_v0.1"


class AuthorizationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def verify_digest(value: dict[str, Any], expected: str) -> None:
    recorded = value.get("deterministic_sha256")
    core = dict(value)
    core.pop("deterministic_sha256", None)
    actual = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
    require(recorded == expected == actual, f"deterministic digest drift: {actual}")


def verify(repo_root: Path) -> dict[str, Any]:
    data = repo_root / DATA
    hosted = read_json(data / "post-activation-hosted-evidence-v0.1.json")
    readiness = read_json(data / "release-readiness-v0.1.json")
    authorization = read_json(data / "release-authorization-v0.1.json")
    activation = read_json(data / "activation-v0.1.json")
    contract = read_json(repo_root / "services/texas_bounded_api/service_contract.v0.2.json")

    verify_digest(hosted, HOSTED_SHA)
    verify_digest(readiness, READINESS_SHA)
    verify_digest(authorization, AUTH_SHA)

    require(hosted.get("status") == "PASS", "post-activation hosted evidence must PASS")
    require(hosted.get("repository_activation") == "ACTIVATED_BOUNDED", "hosted activation drift")
    require(hosted.get("release_authorized") is False, "hosted proof must predate release authorization")
    require(hosted.get("publication_workflow_authorized") is False, "hosted proof must predate publication workflow authorization")
    require(hosted.get("canonical_writes") == 0, "hosted proof performed canonical writes")

    require(readiness.get("status") == "READY_FOR_RELEASE_AUTHORIZATION", "release readiness not satisfied")
    require(readiness.get("runtime_merged") is True, "runtime merge not satisfied")
    require(readiness.get("release_authorized") is False, "readiness receipt must not self-authorize release")
    require(readiness.get("publication_workflow_authorized") is False, "readiness receipt must not self-authorize publication")
    require(readiness.get("canonical_writes") == 0, "readiness receipt performed canonical writes")
    require(readiness.get("inputs", {}).get("post_activation_hosted_evidence_sha256") == HOSTED_SHA,
            "readiness hosted evidence pointer drift")

    require(activation.get("status") == "ACTIVATED_BOUNDED", "repository activation missing")
    require(activation.get("deterministic_sha256") == authorization["authorization_basis"]["activation_receipt_sha256"],
            "activation receipt pointer drift")
    require(contract.get("schema_version") == "texas-hosted-runtime-service/0.2", "runtime contract version drift")
    require(contract.get("release_authorized") is False and contract.get("publication_workflow_authorized") is False,
            "runtime contract must remain non-self-authorizing")

    require(authorization.get("schema_version") == "texas-bounded-release-authorization/0.1",
            "release authorization schema drift")
    require(authorization.get("status") == "RELEASE_AUTHORIZED__PUBLICATION_NOT_EXECUTED",
            "release authorization status drift")
    require(authorization.get("profile_id") == PROFILE, "profile drift")
    basis = authorization.get("authorization_basis") or {}
    require(basis.get("runtime_main_sha") == RUNTIME_MAIN_SHA, "runtime main SHA drift")
    require(basis.get("release_readiness_sha256") == READINESS_SHA, "readiness pointer drift")
    require(basis.get("post_activation_hosted_evidence_sha256") == HOSTED_SHA, "hosted pointer drift")
    require(basis.get("service_contract_sha256") == hosted.get("service_contract_sha256"), "service contract pointer drift")

    scope = authorization.get("scope") or {}
    require(scope == {
        "coverage": "HOUSE_49_INTERSECTION_SENATE_14",
        "bindings_required": ["tx-house", "tx-senate"],
        "complete_jurisdiction": False,
        "full_essentials": False,
        "elections": False,
    }, "bounded scope drift")

    auth = authorization.get("authorization") or {}
    require(auth.get("release_authorized") is True, "release not authorized")
    require(auth.get("publication_workflow_authorized") is True, "publication workflow not authorized")
    require(auth.get("publication_execution_authorized") is False, "publication execution prematurely authorized")
    require(auth.get("github_release_creation_authorized") is False, "GitHub Release creation prematurely authorized")
    require(auth.get("railway_redeploy_authorized") is False, "Railway redeploy prematurely authorized")
    require(auth.get("canonical_writes") == 0, "canonical writes authorized")

    publication = authorization.get("publication_contract") or {}
    require(publication.get("surface") == "BOUNDED_RUNTIME_RELEASE", "publication surface drift")
    require(publication.get("raw_package_bytes_publishable") is False, "raw package bytes must remain unpublished")
    require(publication.get("source_package_publication_eligible") is False, "source package eligibility was widened")
    require(publication.get("registry_publication_eligible") is False, "registry eligibility was widened")
    require(publication.get("release_assets") == ["texas-bounded-runtime-release-manifest-v0.1.json"],
            "release asset scope drift")

    return {
        "status": "PASS",
        "schema_version": authorization["schema_version"],
        "deterministic_sha256": AUTH_SHA,
        "release_authorized": True,
        "publication_workflow_authorized": True,
        "publication_execution_authorized": False,
        "github_release_creation_authorized": False,
        "railway_redeploy_authorized": False,
        "canonical_writes": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(canonical_json(verify(args.repo_root.resolve())), end="")


if __name__ == "__main__":
    main()
