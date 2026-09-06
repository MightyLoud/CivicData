#!/usr/bin/env python3
"""Verify the bounded Texas publication closeout without mutating the release."""
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
from tools.texas_bounded_publication import prepare_manifest

SNAPSHOT_SHA = "7ccba5503099d5292b4f7cfd4b46c4dd64d331b9e854ed6f9f1d50015581b9ed"
CLOSEOUT_SHA = "fb82a0831ae9c8eb24af66543f8b2db49820ded2b5145b9e5ff5b3f907e67bb3"
EXECUTION_HEAD_SHA = "d9045f5ae176d13b6226a4e7159e63702be5bdd8"
TARGET_SHA = "defefa6d31987187839fa90434b201a287518e34"
ASSET_SHA = "80bcb6f3d4d668ce62af84450b1db726156c0beaf7bc24b053b8c6291704cffe"
ASSET_BYTES = 1766
MANIFEST_SHA = "4d04488a9f191c048cc647737f3bea2e3631dd2159ee43a3df36a6445bcf40a1"


class CloseoutError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CloseoutError(message)


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
    data = repo_root / "data/packages/tx/legislative"
    snapshot = read_json(data / "publication-release-snapshot-v0.1.json")
    closeout = read_json(data / "publication-closeout-v0.1.json")
    execution_path = data / "publication-execution-authorization-v0.1.json"

    verify_digest(snapshot, SNAPSHOT_SHA)
    verify_digest(closeout, CLOSEOUT_SHA)

    require(snapshot.get("schema_version") == "texas-bounded-publication-release-snapshot/0.1",
            "release snapshot schema drift")
    require(snapshot.get("status") == "OBSERVED_PUBLISHED", "release snapshot status drift")
    release = snapshot.get("release") or {}
    require(release.get("release_id") == 383744766, "release id drift")
    require(release.get("tag") == "tx-legislative-two-office-v0.1", "release tag drift")
    require(release.get("target_sha") == TARGET_SHA, "release target drift")
    require(release.get("draft") is False and release.get("prerelease") is False,
            "release publication state drift")
    assets = snapshot.get("assets") or []
    require(len(assets) == 1, "release asset cardinality drift")
    asset = assets[0]
    require(asset.get("name") == "texas-bounded-runtime-release-manifest-v0.1.json",
            "release asset name drift")
    require(asset.get("bytes") == ASSET_BYTES, "release asset size drift")
    require(asset.get("sha256") == ASSET_SHA, "release asset digest drift")
    require(asset.get("state") == "uploaded", "release asset state drift")

    manifest = prepare_manifest(
        repo_root=repo_root,
        execution_authorization_path=execution_path,
        execution_head_sha=EXECUTION_HEAD_SHA,
    )
    manifest_bytes = canonical_json(manifest).encode("utf-8")
    reconstructed_sha = hashlib.sha256(manifest_bytes).hexdigest()
    require(len(manifest_bytes) == ASSET_BYTES, "reconstructed manifest size drift")
    require(reconstructed_sha == ASSET_SHA, "reconstructed asset digest drift")
    require(manifest.get("deterministic_sha256") == MANIFEST_SHA, "manifest deterministic digest drift")
    require(manifest.get("target_sha") == TARGET_SHA, "manifest target drift")
    require(manifest.get("execution_head_sha") == EXECUTION_HEAD_SHA, "manifest execution head drift")

    require(closeout.get("schema_version") == "texas-bounded-publication-closeout/0.1",
            "closeout schema drift")
    require(closeout.get("status") == "PUBLISHED_CERTIFIED", "closeout status drift")
    require(closeout.get("certification_mutates_release") is False, "closeout must not mutate release")
    require(closeout.get("publication", {}).get("release_snapshot_sha256") == SNAPSHOT_SHA,
            "closeout snapshot pointer drift")
    require(closeout.get("publication", {}).get("release_id") == release.get("release_id"),
            "closeout release id drift")
    require(closeout.get("publication", {}).get("tag") == release.get("tag"), "closeout tag drift")
    require(closeout.get("publication", {}).get("target_sha") == TARGET_SHA, "closeout target drift")
    closeout_asset = closeout.get("asset") or {}
    require(closeout_asset.get("count") == 1, "closeout asset count drift")
    require(closeout_asset.get("github_sha256") == ASSET_SHA, "closeout GitHub digest drift")
    require(closeout_asset.get("reconstructed_sha256") == ASSET_SHA, "closeout reconstructed digest drift")
    require(closeout_asset.get("bytes") == ASSET_BYTES, "closeout asset size drift")
    require(closeout_asset.get("manifest_deterministic_sha256") == MANIFEST_SHA,
            "closeout manifest digest drift")
    require(closeout_asset.get("reconstruction_status") == "MATCH", "closeout reconstruction status drift")

    scope = closeout.get("scope") or {}
    require(scope == {
        "coverage": "HOUSE_49_INTERSECTION_SENATE_14",
        "bindings_required": ["tx-house", "tx-senate"],
        "complete_jurisdiction": False,
        "full_essentials": False,
        "elections": False,
    }, "closeout bounded scope drift")
    boundaries = closeout.get("boundaries") or {}
    require(boundaries == {
        "raw_package_bytes_published": False,
        "source_package_publication_eligible": False,
        "registry_publication_eligible": False,
        "railway_redeploy": False,
        "canonical_writes": 0,
    }, "closeout publication boundary drift")
    railway = closeout.get("railway") or {}
    require(railway.get("deployment_head_sha") == "bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67",
            "Railway deployment head drift")
    require(railway.get("unchanged") is True and railway.get("redeploy_authorized") is False,
            "Railway closeout boundary drift")

    return {
        "status": "PASS",
        "schema_version": closeout["schema_version"],
        "deterministic_sha256": CLOSEOUT_SHA,
        "release_snapshot_sha256": SNAPSHOT_SHA,
        "asset_sha256": ASSET_SHA,
        "asset_bytes": ASSET_BYTES,
        "manifest_deterministic_sha256": MANIFEST_SHA,
        "release_mutated": False,
        "railway_redeploy": False,
        "canonical_writes": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(canonical_json(verify(args.repo_root.resolve())), end="")


if __name__ == "__main__":
    main()
