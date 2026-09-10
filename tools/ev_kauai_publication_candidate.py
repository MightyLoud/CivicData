#!/usr/bin/env python3
"""Build an offline, metadata-only Kauaʻi release candidate. No release writes."""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import countywide_production as production, package_catalog
from tools import ev_kauai_countywide_preview as preview_runner, jurisdiction_package

GATE = "EV-KAUAI-PUBLICATION-CANDIDATE-001"
REPOSITORY = "MightyLoud/CivicData"
TARGET = "a24dd03a9958ffe7bc7a5ba2d0808ef9d1d81eed"
TARGET_TREE = "71c9f04666fff5789d2d52f41a4284b9570a29bb"
CERTIFIED_ACTIVATION = "c277080bc401b07943d6833def9fb23ecab448ff"
RUNTIME_SHA = "32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797"
PACKAGE_SHA = "b9627bbf6cbe5a03e9ee449cb23738af73d7002f257c73b1f2c2a82f4c4c90bd"
RECEIPT_SHA = "19813da27e25d3bc1e3792c1e73e81ac9b6b2f58be98a3535b664cb26787062e"
ZIP_SHA = "c3c5be135e146a3a066107b3d72f2c918286e6ac8b548cbd98367bb0653973ef"
LIVE_SHA = "c82480a4511922abfce54dfb0d9cb5804a72abee1731da123ec8aa112c3fec54"
TAG = "kauai-mayor-council-integration-v0.1"
ASSET = "kauai-mayor-council-integration-manifest-v0.1.json"
CANDIDATE = Path("candidates/ev/kauai_publication.v0.1")
MANIFEST = CANDIDATE / "manifest.json"
RETENTION = CANDIDATE / "evidence/retention.v0.1.json"
EVIDENCE = CANDIDATE / "evidence/activation-c277080.zip.b64"
SCHEMA = Path("schemas/kauai_integration_manifest_v0.1.schema.json")
ARTIFACTS = Path("artifacts/ev-kauai-publication-candidate")
ALLOWED_PATHS = {
    str(MANIFEST), str(RETENTION), str(EVIDENCE), str(SCHEMA),
    "tools/ev_kauai_publication_candidate.py", "tests/ev_kauai_publication_candidate_test.py",
    "docs/ev-kauai-publication-candidate-001.md", ".github/workflows/ev-kauai-publication-candidate.yml",
}
INPUT_HASHES = {
    production.RECEIPT_PATH: RECEIPT_SHA,
    str(production.SPEC_PATH): "9ea237c4db6a23a832192c9f67200a1cd15d3cdc97aaf9961648b181baf23fc3",
    "consumers/empowered_vote/package_catalog.v0.1.json":
        "6f38f5ebf24dfee8a7c6dc5ab93f562602fc41d865dbca6dd29290e8d3ee312f",
    "civic_gps_extensions/registry_bundles.v0.1.json":
        "4b6aad7a6cc835c59c3013a40f57326d59af2b4e7af23a9b36ff2f6e71a176e9",
    "civic_gps_extensions/hi_kauai_county_release_v0.1.json":
        "195a1ef070d9718135bc7e7929e0cf037f78953f2ab5874377cddd4530f2693d",
}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_json(raw: bytes) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def retention_contract() -> dict[str, Any]:
    return {
        "retention_schema": "kauai-activation-evidence-retention/0.1",
        "repository": REPOSITORY, "source_commit": CERTIFIED_ACTIVATION,
        "integration_target": TARGET, "identical_source_and_target_tree": TARGET_TREE,
        "workflow_run_id": 34305859296, "job_id": 102322283047, "artifact_id": 10086608935,
        "artifact_url": "https://github.com/MightyLoud/CivicData/actions/runs/34305859296/artifacts/10086608935",
        "original_created_at": "2026-09-09T03:07:10Z",
        "original_expires_at": "2026-10-09T03:07:09Z", "retained_on": "2026-09-09",
        "encoding": "BASE64_ORIGINAL_GITHUB_ACTIONS_ZIP", "path": str(EVIDENCE),
        "zip_bytes": 4905, "zip_sha256": ZIP_SHA,
        "members": [{"path": "live.json", "bytes": 65052, "sha256": LIVE_SHA}],
        "validation_mode": "RETAINED_LIVE_CIVIC_GPS",
        "negative_geography_basis": "CERTIFIED_RUN_ASSERTION; RAW_NEGATIVE_GEOGRAPHY_NOT_IN_ARTIFACT",
        "release_asset": False, "fresh_live_run": False, "hosted_delivery_evidence": False,
        "publication_authorized": False, "deployment_authorized": False,
    }


def read_evidence(root: Path) -> dict[str, Any]:
    require(encoded(load_json((root / RETENTION).read_bytes())) == encoded(retention_contract()),
            "EVIDENCE_RETENTION_CONTRACT_DRIFT")
    try:
        text = (root / EVIDENCE).read_text(encoding="ascii")
        raw = base64.b64decode(text.strip(), validate=True)
        require(len(raw) == 4905 and sha(raw) == ZIP_SHA, "ORIGINAL_LIVE_ZIP_DRIFT")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(archive.namelist() == ["live.json"], "LIVE_ZIP_MEMBERS_INVALID")
            payload = archive.read("live.json")
        require(len(payload) == 65052 and sha(payload) == LIVE_SHA, "LIVE_PAYLOAD_DRIFT")
        return load_json(payload)
    except (binascii.Error, UnicodeError, zipfile.BadZipFile) as exc:
        raise ValueError("LIVE_EVIDENCE_ENCODING_INVALID") from exc


def validate_review(review: dict[str, Any], today: date | None = None) -> None:
    current = datetime.now(timezone.utc).date() if today is None else today
    reviewed = date.fromisoformat(review["reviewed_on"])
    expires = date.fromisoformat(review["expires_on"])
    require(reviewed == date(2026, 9, 9) and expires == date(2026, 12, 1)
            and reviewed <= current < expires, "SOURCE_REVIEW_EXPIRED_FUTURE_OR_DRIFTED")


def validate_package(package: dict[str, Any]) -> None:
    require(not jurisdiction_package.validate_public_identity_disposition(package), "PUBLIC_IDENTITY_REJECTED")
    require(production.digest(package) == PACKAGE_SHA, "CANONICAL_PACKAGE_DRIFT")


def verify_inputs(root: Path, today: date | None = None) -> dict[str, Any]:
    before = preview_runner.snapshot(root)
    for path, expected in INPUT_HASHES.items():
        require(sha((root / path).read_bytes()) == expected, "INPUT_HASH_DRIFT: " + path)
    receipt = load_json((root / production.RECEIPT_PATH).read_bytes())
    validate_review(receipt["source_review"], today)
    spec = production.installed_spec(root)
    require(spec is not None, "PRODUCTION_INSTALLATION_MISSING")
    catalog = package_catalog.load_catalog(root / "consumers/empowered_vote/package_catalog.v0.1.json")
    entry = next(row for row in catalog["entries"] if row["entry_id"] == production.ENTRY_ID)
    validate_package(package_catalog.reconstruct_package(entry, root))
    parts = sorted((root / "civic_gps_runtime_parts").glob("part.*"))
    require([p.name for p in parts] == [f"part.{i:02d}" for i in range(9)], "RUNTIME_PART_SET_DRIFT")
    require(sha(b"".join(p.read_bytes() for p in parts)) == RUNTIME_SHA, "RUNTIME_HASH_DRIFT")
    live = read_evidence(root)
    expected = {"gate": "EV-KAUAI-PROD-ACTIVATION-CANDIDATE-001", "status": "PASS",
                "source_commit": CERTIFIED_ACTIVATION, "validation_mode": "LIVE_CIVIC_GPS",
                "entry_id": production.ENTRY_ID, "scope": production.candidate.SCOPE,
                "acceptance_receipt_sha256": RECEIPT_SHA,
                "archive_sha256": production.candidate.ARCHIVE_SHA256,
                "canonical_writes": 0, "auto_promoted": 0, "publication_authorized": False,
                "deployment_authorized": False, "protected_content_unchanged": True}
    require(encoded({k: live.get(k) for k in expected}) == encoded(expected), "RETAINED_LIVE_CONTRACT_DRIFT")
    require(live["source_review"] == receipt["source_review"], "LIVE_SOURCE_REVIEW_DRIFT")
    positives = live["positive_controls"]
    require([row["address"] for row in positives] == receipt["positive_addresses"], "LIVE_CONTROLS_DRIFT")
    for row in positives:
        model = row["representation"]
        require(model["status"] == "PASS" and model["matched_address"]
                and model["county_geoid"] == "15007"
                and model["office_count"] == 2 and model["current_holder_count"] == 8
                and model["production_profile_id"] == production.PROFILE_ID
                and all(model.get(k) is v for k, v in production.FLAGS.items()), "LIVE_PROJECTION_DRIFT")
        require(production.digest({k: v for k, v in model.items() if k != "deterministic_sha256"})
                == model["deterministic_sha256"], "LIVE_PROJECTION_DIGEST_DRIFT")
    require(positives[0]["representation"]["applicable_offices"] ==
            positives[1]["representation"]["applicable_offices"], "LIVE_COUNTYWIDE_PARITY_DRIFT")
    negative = live["negative_control"]
    require(negative["control"] == receipt["negative_control"]
            and negative["result"]["status"] == "FAIL-CLOSED"
            and negative["result"]["error"] == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
            and "applicable_offices" not in negative["result"], "LIVE_NEGATIVE_DRIFT")
    holds = preview_runner.assert_holds(root)
    require(holds == live["hi_dispositions"], "OTHER_HI_HOLDS_DRIFT")
    require(before == preview_runner.snapshot(root), "PROTECTED_INPUTS_MUTATED")
    return receipt


def manifest_contract(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_schema": "kauai-mayor-council-integration/0.1", "candidate_gate": GATE,
        "artifact_kind": "METADATA_ONLY_INTEGRATION_MANIFEST", "status": "CANDIDATE_PUBLICATION_HELD",
        "repository": REPOSITORY, "integration_target_commit": TARGET, "integration_target_tree": TARGET_TREE,
        "integration_pr": "https://github.com/MightyLoud/CivicData/pull/60",
        "profile_id": production.PROFILE_ID, "entry_id": production.ENTRY_ID,
        "package_jurisdiction_id": "jurisdiction-hi-kauai-county",
        "civic_gps_jurisdiction_id": "jur-us-hi-kauai-county", "county_geoid": "15007",
        "scope": production.candidate.SCOPE,
        "counts": {"office_rows": 2, "seat_capacity": 8, "current_holders": 8,
                   "leadership_overlays": 2, "divisions": 0},
        "capabilities": {"countywide_mayor_council_representation": True, "full_essentials": False,
                         "election_results": False, "complete_jurisdiction": False,
                         "hosted_delivery_certified": False},
        "preserved_production_flags": production.FLAGS.copy(),
        "input_hashes": INPUT_HASHES.copy(),
        "archive_sha256": production.candidate.ARCHIVE_SHA256, "package_sha256": PACKAGE_SHA,
        "binding_sha256": receipt["binding_sha256"],
        "route_sha256": receipt["routing"]["route_sha256"], "runtime_archive_sha256": RUNTIME_SHA,
        "source_review": {
            "reviewed_on": receipt["source_review"]["reviewed_on"],
            "expires_on": receipt["source_review"]["expires_on"], "expiry_timezone": "UTC",
            "identity_policy": "PRESERVE_LEGACY_ACTIVE_REJECT_EXPLICIT_PROVISIONAL",
            "tenure_policy": "PRESERVE_UNRESOLVED_INTERVALS",
            "known_omitted_offices": ["Prosecuting Attorney"],
            "sources": [row["url"] for row in receipt["source_review"]["sources"]],
            "recheck_required_before_release": True,
        },
        "retained_warnings": ["UNNUMBERED_MULTI_SEAT_COUNCIL", "EXACT_TENURE_INTERVALS_UNRESOLVED"],
        "activation_evidence": {
            "certified_head": CERTIFIED_ACTIVATION, "workflow_run_id": 34305859296,
            "workflow_url": "https://github.com/MightyLoud/CivicData/actions/runs/34305859296",
            "retention_receipt": str(RETENTION), "original_zip_sha256": ZIP_SHA,
            "live_json_sha256": LIVE_SHA, "mode": "RETAINED_LIVE_CIVIC_GPS",
            "positive_controls": 2, "negative_controls": 1,
            "negative_geography_basis": "CERTIFIED_RUN_ASSERTION; RAW_NEGATIVE_GEOGRAPHY_NOT_IN_ARTIFACT",
            "fresh_live_run": False, "hosted_delivery_evidence": False,
        },
        "proposed_release": {"tag": TAG, "target_commit": TARGET, "assets": [ASSET],
                             "asset_type": "application/json", "raw_package_assets": False,
                             "officeholder_payload_assets": False, "tag_reserved": False},
        "holds": {"merge_authorized": False, "publication_authorized": False, "deployment_authorized": False,
                  "other_hi_production_counties": ["15001", "15003", "15009"],
                  "kalawao_work_authorized": False, "canonical_writes": 0},
    }


def schema_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    # This release version fixes every value. Nested const values also reject added payload fields.
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Immutable Kauai metadata-only integration manifest v0.1",
            "type": "object", "additionalProperties": False, "required": sorted(manifest),
            "properties": {key: {"const": value} for key, value in manifest.items()}}


def validate_manifest(manifest: Any, receipt: dict[str, Any], today: date | None = None) -> None:
    validate_review(receipt["source_review"], today)
    require(encoded(manifest) == encoded(manifest_contract(receipt)), "MANIFEST_CONTRACT_DRIFT")


def verify_git(root: Path, head: str, base: str) -> dict[str, Any]:
    require(re.fullmatch(r"[a-f0-9]{40}", head) is not None and base == TARGET, "GIT_BASE_OR_HEAD_INVALID")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    require(git("rev-parse", "HEAD") == head, "CHECKOUT_HEAD_DRIFT")
    require(git("rev-parse", TARGET + "^{tree}") == TARGET_TREE
            and git("rev-parse", CERTIFIED_ACTIVATION + "^{tree}") == TARGET_TREE, "INTEGRATION_TREE_DRIFT")
    changed = git("diff", "--name-only", base, head).splitlines()
    require(bool(changed) and set(changed) <= ALLOWED_PATHS, "CANDIDATE_PATH_SCOPE_DRIFT")
    # A clean checkout ensures the files tested are the files at the claimed head.
    require(not git("status", "--porcelain", "--untracked-files=no"), "TRACKED_WORKTREE_DIRTY")
    return {"status": "PASS", "head": head, "base": base, "changed_paths": changed}


def validate_destination(snapshot: dict[str, Any], now: datetime | None = None) -> None:
    current = datetime.now(timezone.utc) if now is None else now
    checked = datetime.fromisoformat(snapshot["checked_at_utc"].replace("Z", "+00:00"))
    require(checked.utcoffset() == timedelta(0) and timedelta(0) <= current - checked <= timedelta(hours=1),
            "DESTINATION_SNAPSHOT_STALE_OR_FUTURE")
    require(snapshot.get("repository") == REPOSITORY and snapshot.get("complete") is True
            and snapshot.get("proposed_tag") == TAG and snapshot.get("target_commit") == TARGET
            and snapshot.get("target_tree") == TARGET_TREE, "DESTINATION_CONTRACT_DRIFT")
    require(isinstance(snapshot.get("tag_refs"), list) and isinstance(snapshot.get("release_tags"), list)
            and all(isinstance(v, str) for v in snapshot["tag_refs"] + snapshot["release_tags"]),
            "DESTINATION_INVENTORY_INVALID")
    require("refs/tags/" + TAG not in snapshot["tag_refs"] and TAG not in snapshot["release_tags"],
            "PROPOSED_TAG_OR_RELEASE_COLLISION")


def write_bundle(root: Path, output: Path, manifest: dict[str, Any], report: dict[str, Any]) -> None:
    root, output = root.resolve(), output.resolve()
    allowed = root / ARTIFACTS
    require(output != allowed and output.is_relative_to(allowed), "OUTPUT_MUST_BE_NEW_CANDIDATE_ARTIFACT_DIRECTORY")
    require(not output.exists(), "OUTPUT_DESTINATION_COLLISION")
    output.mkdir(parents=True, exist_ok=False)
    # Only this subdirectory is a potential future release asset set. Report/evidence stay outside it.
    assets = output / "release-assets"
    assets.mkdir()
    (assets / ASSET).write_bytes(encoded(manifest))
    (output / "verification.json").write_bytes(encoded(report))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--remote-snapshot", type=Path)
    ap.add_argument("--head")
    ap.add_argument("--base")
    args = ap.parse_args()
    root = args.repo_root.resolve()
    git_result = verify_git(root, args.head, args.base) if args.head and args.base else None
    require(bool(args.head) == bool(args.base), "BOTH_HEAD_AND_BASE_REQUIRED")
    receipt = verify_inputs(root)
    manifest = load_json((root / MANIFEST).read_bytes())
    validate_manifest(manifest, receipt)
    require((root / MANIFEST).read_bytes() == encoded(manifest), "MANIFEST_SERIALIZATION_DRIFT")
    require(load_json((root / SCHEMA).read_bytes()) == schema_contract(manifest), "MANIFEST_SCHEMA_DRIFT")
    if args.remote_snapshot:
        validate_destination(load_json(args.remote_snapshot.read_bytes()))
    report = {"gate": GATE, "status": "PASS", "validation_mode": "OFFLINE_WITH_RETAINED_LIVE_EVIDENCE",
              "manifest_sha256": sha(encoded(manifest)), "manifest_bytes": len(encoded(manifest)),
              "integration_target": TARGET, "git_verification": git_result,
              "remote_collision_check": "PASS" if args.remote_snapshot else "NOT_REQUESTED",
              "source_review_expires_on": "2026-12-01", "release_asset_count": 1,
              "retained_zip_sha256": ZIP_SHA, "canonical_writes": 0,
              "merge_authorized": False, "publication_authorized": False, "deployment_authorized": False}
    if args.output_dir:
        write_bundle(root, args.output_dir, manifest, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
