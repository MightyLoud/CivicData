#!/usr/bin/env python3
"""Prepare the bounded Texas runtime publication manifest only after explicit execution authorization."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tools.jurisdiction_package import canonical_json
from tools.texas_release_authorization import AUTH_SHA, verify as verify_release_authorization

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_SCHEMA = "texas-bounded-publication-execution/0.1"
MANIFEST_SCHEMA = "texas-bounded-runtime-release-manifest/0.1"


class PublicationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationError(message)


def read_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"PUBLICATION_EXECUTION_AUTHORIZATION_MISSING: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def verify_digest(value: dict[str, Any]) -> str:
    recorded = value.get("deterministic_sha256")
    core = dict(value)
    core.pop("deterministic_sha256", None)
    actual = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
    require(recorded == actual, f"execution authorization digest drift: {actual}")
    return actual


def prepare_manifest(*, repo_root: Path, execution_authorization_path: Path,
                     head_sha: str) -> dict[str, Any]:
    require(re.fullmatch(r"[a-f0-9]{40}", head_sha) is not None, "PUBLICATION_HEAD_SHA_INVALID")
    verify_release_authorization(repo_root)
    release_auth = json.loads((repo_root / "data/packages/tx/legislative/release-authorization-v0.1.json").read_text(encoding="utf-8"))
    execution = read_json(execution_authorization_path)
    execution_sha = verify_digest(execution)

    required = {
        "schema_version", "status", "profile_id", "release_authorization_sha256",
        "publication_main_sha", "proposed_tag", "execution_authorized",
        "github_release_creation_authorized", "railway_redeploy_authorized",
        "canonical_writes", "deterministic_sha256",
    }
    require(set(execution) == required, "PUBLICATION_EXECUTION_AUTHORIZATION_FIELDS_INVALID")
    require(execution.get("schema_version") == EXECUTION_SCHEMA, "PUBLICATION_EXECUTION_SCHEMA_INVALID")
    require(execution.get("status") == "PUBLICATION_EXECUTION_AUTHORIZED", "PUBLICATION_EXECUTION_NOT_AUTHORIZED")
    require(execution.get("profile_id") == release_auth.get("profile_id"), "PUBLICATION_PROFILE_DRIFT")
    require(execution.get("release_authorization_sha256") == AUTH_SHA, "PUBLICATION_RELEASE_AUTHORIZATION_DRIFT")
    require(execution.get("publication_main_sha") == head_sha, "PUBLICATION_MAIN_SHA_DRIFT")
    require(execution.get("proposed_tag") == release_auth["publication_contract"]["proposed_tag"], "PUBLICATION_TAG_DRIFT")
    require(execution.get("execution_authorized") is True, "PUBLICATION_EXECUTION_NOT_AUTHORIZED")
    require(execution.get("github_release_creation_authorized") is True, "GITHUB_RELEASE_CREATION_NOT_AUTHORIZED")
    require(execution.get("railway_redeploy_authorized") is False, "PUBLICATION_MUST_NOT_REDEPLOY_RAILWAY")
    require(execution.get("canonical_writes") == 0, "PUBLICATION_CANONICAL_WRITES_FORBIDDEN")

    publication = release_auth["publication_contract"]
    basis = release_auth["authorization_basis"]
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "PUBLICATION_MANIFEST_READY",
        "profile_id": release_auth["profile_id"],
        "target_sha": head_sha,
        "tag": publication["proposed_tag"],
        "title": publication["proposed_title"],
        "public_runtime_endpoint": publication["public_runtime_endpoint"],
        "scope": release_auth["scope"],
        "authorization": {
            "release_authorization_sha256": AUTH_SHA,
            "publication_execution_authorization_sha256": execution_sha,
        },
        "inputs": {
            "package_sha256": basis["package_sha256"],
            "catalog_entry_sha256": basis["catalog_entry_sha256"],
            "legislative_group_sha256": basis["legislative_group_sha256"],
            "post_activation_hosted_evidence_sha256": basis["post_activation_hosted_evidence_sha256"],
            "release_readiness_sha256": basis["release_readiness_sha256"],
            "service_contract_sha256": basis["service_contract_sha256"],
        },
        "publication_boundaries": {
            "raw_package_bytes_published": False,
            "source_package_publication_eligible": False,
            "registry_publication_eligible": False,
            "railway_redeploy": False,
            "canonical_writes": 0,
        },
    }
    manifest["deterministic_sha256"] = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--execution-authorization", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare_manifest(
        repo_root=args.repo_root.resolve(),
        execution_authorization_path=args.execution_authorization,
        head_sha=args.head_sha.strip().lower(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(manifest), encoding="utf-8")
    print(canonical_json(manifest), end="")


if __name__ == "__main__":
    main()
