#!/usr/bin/env python3
"""Build an offline, metadata-only Maui release candidate. No release writes."""
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

from consumers.empowered_vote import maui_countywide_production as production, package_catalog
from tools import ev_maui_adapter_candidate as preview_runner, jurisdiction_package
from tools import ev_kauai_countywide_preview as hi_runner, ev_maui_source_correction as correction

GATE = "EV-MAUI-PUBLICATION-CANDIDATE-001"
REPOSITORY = "MightyLoud/CivicData"
TARGET = "2b3e8d5df11ed4f4b19f7579c9bd1663131070bf"
TARGET_TREE = "f44d953d2e31d04cebce20368627b5938c83d140"
CERTIFIED_ACTIVATION = "fe15b3c6a61a4f46851a52992369428ab9ef413b"
RUNTIME_SHA = "32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797"
PACKAGE_SHA = "7ddaf33b2184f9a465128cac581e75b5b6a3a5601ca052d5ff9403b2ffc006e3"
RECEIPT_SHA = "7b5e0ba92020b59bacb3959b17fa7735e62d92c9b75f5f697ea4406e598ba8c8"
ZIP_SHA = "96f16d92b8bbdabe13b12260d5de61183e63cf1771cc4c319fafe48ca0c175f1"
LIVE_SHA = "5fed9c6740d1fa9d3f76c86ab3d2a6fb8b7d35c8f4feba9336588a0d143f7a67"
TAG = "maui-mayor-council-integration-v0.1"
ASSET = "maui-mayor-council-integration-manifest-v0.1.json"
CANDIDATE = Path("candidates/ev/maui_publication.v0.1")
MANIFEST = CANDIDATE / "manifest.json"
RETENTION = CANDIDATE / "evidence/retention.v0.1.json"
EVIDENCE = CANDIDATE / "evidence/activation-fe15b3c.zip.b64"
SCHEMA = Path("schemas/maui_integration_manifest_v0.1.schema.json")
ARTIFACTS = Path("artifacts/ev-maui-publication-candidate")
ALLOWED_PATHS = {
    str(MANIFEST), str(RETENTION), str(EVIDENCE), str(SCHEMA),
    "tools/ev_maui_activation_diff.py",
    "tools/ev_maui_publication_candidate.py", "tests/ev_maui_publication_candidate_test.py",
    "docs/ev-maui-publication-candidate-001.md", ".github/workflows/ev-maui-publication-candidate.yml",
}
INPUT_HASHES = {
    "acceptance/ev/maui_countywide.v0.1.json": "7b5e0ba92020b59bacb3959b17fa7735e62d92c9b75f5f697ea4406e598ba8c8",
    "acceptance/ev/maui_source_review.v0.1.json": "b85827b4056d70e70ebb8e1e69bb02a60da3009854d5d80840a2edfe00c4b6b2",
    "onboarding/ev/maui-county.v0.1.json": "39ea46639bd3c45872198801e251184bbe5812bc28a22cf109cf7acd4357ee5d",
    "consumers/empowered_vote/package_catalog.v0.1.json": "51ff1a52efaeef42dc65524f5bac0a53ac0500e0f989c74b8241914594c1a388",
    "civic_gps_extensions/registry_bundles.v0.1.json": "4b6aad7a6cc835c59c3013a40f57326d59af2b4e7af23a9b36ff2f6e71a176e9",
    "civic_gps_extensions/hi_maui_county_release_v0.1.json": "9ae1e0872ee347e0bbbe7a57721ecc67ac39cebc2c2d4b29cf06c04c8d3fe781",
    "previews/ev/maui_source_correction.v0.1.json": "1155e5ba2128cd6d85daf212d8e1b0acd01ac39df791db941b40cd7d70dbc262"
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
        "retention_schema": "maui-activation-evidence-retention/0.1",
        "repository": REPOSITORY, "source_commit": CERTIFIED_ACTIVATION,
        "integration_target": TARGET, "identical_source_and_target_tree": TARGET_TREE,
        "workflow_run_id": 34717704026, "job_id": 103617800188, "artifact_id": 10305356930,
        "artifact_url": "https://github.com/MightyLoud/CivicData/actions/runs/34717704026/artifacts/10305356930",
        "original_created_at": "2026-09-12T20:44:19Z",
        "original_expires_at": "2026-10-12T20:44:19Z", "retained_on": "2026-09-13",
        "encoding": "BASE64_ORIGINAL_GITHUB_ACTIONS_ZIP", "path": str(EVIDENCE),
        "zip_bytes": 11581, "zip_sha256": ZIP_SHA,
        "members": [{"path": "live.json", "bytes": 137349, "sha256": LIVE_SHA}],
        "validation_mode": "RETAINED_LIVE_CIVIC_GPS",
        "negative_geography_basis": "RETAINED_MATCHED_HAWAII_COUNTY_GEOGRAPHY_AND_REJECTED_CONSUMER_RESULT",
        "release_asset": False, "fresh_live_run": False, "hosted_delivery_evidence": False,
        "publication_authorized": False, "deployment_authorized": False,
    }


def read_evidence(root: Path) -> dict[str, Any]:
    require(encoded(load_json((root / RETENTION).read_bytes())) == encoded(retention_contract()),
            "EVIDENCE_RETENTION_CONTRACT_DRIFT")
    try:
        text = (root / EVIDENCE).read_text(encoding="ascii")
        raw = base64.b64decode(text.strip(), validate=True)
        require(len(raw) == 11581 and sha(raw) == ZIP_SHA, "ORIGINAL_LIVE_ZIP_DRIFT")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(archive.namelist() == ["live.json"], "LIVE_ZIP_MEMBERS_INVALID")
            payload = archive.read("live.json")
        require(len(payload) == 137349 and sha(payload) == LIVE_SHA, "LIVE_PAYLOAD_DRIFT")
        return load_json(payload)
    except (binascii.Error, UnicodeError, zipfile.BadZipFile) as exc:
        raise ValueError("LIVE_EVIDENCE_ENCODING_INVALID") from exc


def validate_review(review: dict[str, Any], today: date | None = None) -> None:
    current = datetime.now(timezone.utc).date() if today is None else today
    reviewed = date.fromisoformat(review["reviewed_on"])
    expires = date.fromisoformat(review["expires_on"])
    require(reviewed == date(2026, 9, 12) and expires == date(2026, 10, 12)
            and reviewed <= current < expires, "SOURCE_REVIEW_EXPIRED_FUTURE_OR_DRIFTED")


def validate_package(package: dict[str, Any]) -> None:
    require(not jurisdiction_package.validate_public_identity_disposition(package), "PUBLIC_IDENTITY_REJECTED")
    require(production.digest(package) == PACKAGE_SHA, "CANONICAL_PACKAGE_DRIFT")


def validate_live(live: dict[str, Any], receipt: dict[str, Any]) -> None:
    expected = {"gate": "EV-MAUI-PROD-ACTIVATION-CANDIDATE-001", "status": "PASS",
                "source_commit": CERTIFIED_ACTIVATION, "validation_mode": "LIVE_CIVIC_GPS",
                "entry_id": production.ENTRY_ID, "profile_id": production.PROFILE_ID,
                "acceptance_receipt_sha256": RECEIPT_SHA,
                "archive_sha256": production.candidate.ARTIFACT["archive_sha256"],
                "source_review": production.REVIEW_REFERENCE, "source_review_expires_on": "2026-10-12",
                "canonical_writes": 0, "auto_promoted": 0, "publication_authorized": False,
                "deployment_authorized": False, "protected_content_unchanged": True, **production.FLAGS}
    require(encoded({k: live.get(k) for k in expected}) == encoded(expected), "RETAINED_LIVE_CONTRACT_DRIFT")
    positives = live["positive_controls"]
    require([row["address"] for row in positives] == receipt["positive_addresses"], "LIVE_CONTROLS_DRIFT")
    for row in positives:
        model = row["representation"]
        require(model["status"] == "PASS" and model["matched_address"] and model["county_geoid"] == "15009"
                and (model["office_count"], model["current_holder_count"], model["residency_area_count"]) == (10, 10, 9)
                and model["production_profile_id"] == production.PROFILE_ID and model["preview_only"] is False
                and all(model.get(k) is v for k, v in production.FLAGS.items()), "LIVE_PROJECTION_DRIFT")
        require(production.digest({k: v for k, v in model.items() if k != "deterministic_sha256"})
                == model["deterministic_sha256"], "LIVE_PROJECTION_DIGEST_DRIFT")
        require(row["candidate_without_opt_in"]["error"] == "COUNTYWIDE_CANDIDATE_NOT_ENABLED"
                and "applicable_offices" not in row["candidate_without_opt_in"], "LIVE_CANDIDATE_ISOLATION_DRIFT")
        require([r["type"] for r in model["warnings"]] ==
                ["COUNTYWIDE_AT_LARGE_WITH_RESIDENCY", "TENURE_INTERVAL_UNRESOLVED"], "LIVE_WARNINGS_DRIFT")
    require(positives[0]["representation"]["applicable_offices"] ==
            positives[1]["representation"]["applicable_offices"], "LIVE_COUNTYWIDE_PARITY_DRIFT")
    negative = live["negative_control"]
    geography = negative["geography"]
    require(negative["control"] == receipt["negative_control"] and geography["status"] == "PASS"
            and geography["matched_address"] and geography["jurisdiction_ids"] == ["jur-us-hi-hawaii-county"]
            and negative["result"]["status"] == "FAIL-CLOSED"
            and negative["result"]["error"] == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
            and "applicable_offices" not in negative["result"], "LIVE_NEGATIVE_DRIFT")
    replay = live["idempotence"]
    require(replay["status"] == "PASS" and replay["changes_required"] == 0 and replay["canonical_writes"] == 0
            and replay["repository_mutated"] is False
            and replay["changes"] == [{"action": "NOOP", "path": p} for p in
                [str(production.SPEC_PATH), "consumers/empowered_vote/package_catalog.v0.1.json",
                 "civic_gps_extensions/registry_bundles.v0.1.json"]], "LIVE_IDEMPOTENCE_DRIFT")


def verify_inputs(root: Path, today: date | None = None) -> dict[str, Any]:
    before = preview_runner.snapshot(root)
    for path, expected in INPUT_HASHES.items():
        require(sha((root / path).read_bytes()) == expected, "INPUT_HASH_DRIFT: " + path)
    review = load_json((root / production.REVIEW_REFERENCE["path"]).read_bytes())
    validate_review(review, today)
    spec = production.installed_spec(root)
    require(spec is not None, "PRODUCTION_INSTALLATION_MISSING")
    catalog = package_catalog.load_catalog(root / "consumers/empowered_vote/package_catalog.v0.1.json")
    entry = next(row for row in catalog["entries"] if row["entry_id"] == production.ENTRY_ID)
    receipt = production.load_receipt(entry, root, today=today)
    validate_package(package_catalog.reconstruct_package(entry, root))
    parts = sorted((root / "civic_gps_runtime_parts").glob("part.*"))
    require([p.name for p in parts] == [f"part.{i:02d}" for i in range(9)], "RUNTIME_PART_SET_DRIFT")
    require(sha(b"".join(p.read_bytes() for p in parts)) == RUNTIME_SHA, "RUNTIME_HASH_DRIFT")
    live = read_evidence(root)
    validate_live(live, receipt)
    _, parity = correction.verify_candidate(root, load_json((root / correction.CONFIG).read_bytes()))
    require(parity == live["source_correction_parity"] and parity["parity_ok"] is True
            and parity["csv_tables_checked"] == 7, "CORRECTION_PARITY_DRIFT")
    require(hi_runner.assert_holds(root) == live["hi_dispositions"], "OTHER_HI_HOLDS_DRIFT")
    require(before == preview_runner.snapshot(root), "PROTECTED_INPUTS_MUTATED")
    return receipt


def manifest_contract(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_schema": "maui-mayor-council-integration/0.1", "candidate_gate": GATE,
        "artifact_kind": "METADATA_ONLY_INTEGRATION_MANIFEST", "status": "CANDIDATE_PUBLICATION_HELD",
        "repository": REPOSITORY, "integration_target_commit": TARGET, "integration_target_tree": TARGET_TREE,
        "integration_pr": "https://github.com/MightyLoud/CivicData/pull/65",
        "profile_id": production.PROFILE_ID, "entry_id": production.ENTRY_ID,
        "package_jurisdiction_id": "jurisdiction-hi-maui-county",
        "civic_gps_jurisdiction_id": "jur-us-hi-maui-county", "county_geoid": "15009",
        "scope": production.candidate.SCOPE,
        "counts": {"office_rows": 10, "seat_capacity": 10, "current_holders": 10,
                   "leadership_overlays": 2, "residency_areas": 9},
        "capabilities": {"countywide_mayor_council_representation": True, "full_essentials": False,
                         "election_results": False, "complete_jurisdiction": False,
                         "hosted_delivery_certified": False},
        "preserved_production_flags": production.FLAGS.copy(), "input_hashes": INPUT_HASHES.copy(),
        "archive_sha256": production.candidate.ARTIFACT["archive_sha256"], "package_sha256": PACKAGE_SHA,
        "binding_sha256": receipt["binding_sha256"],
        "route_sha256": receipt["routing"]["route_sha256"], "runtime_archive_sha256": RUNTIME_SHA,
        "source_review": {
            "reference": production.REVIEW_REFERENCE.copy(),
            "reviewed_on": "2026-09-12", "expires_on": "2026-10-12", "expiry_timezone": "UTC",
            "expiry_basis": "CONSERVATIVE_30_DAY_REVALIDATION_NOT_TERM_END",
            "raw_observations": 13, "normalized_assertions": 25,
            "qa": {"holder_parity": 10, "residency_parity": 9, "leadership_parity": 2,
                   "source_joins_valid": True, "parity_ok": True, "blocking_gap_count": 0},
            "identity_policy": "PRESERVE_LEGACY_ACTIVE_REJECT_EXPLICIT_PROVISIONAL",
            "tenure_policy": "PRESERVE_UNRESOLVED_INTERVALS",
            "residency_policy": "COUNTYWIDE_ELECTORATE_RESIDENCY_IS_NOT_VOTER_FILTER",
            "selection_policy": "PRESERVE_APPOINTED_HOLDER_AND_ELECTED_OFFICE_METHOD",
            "retrieval_limitations": "THREE_COUNTY_PAGES_HTTP_502_REQUIRED_FACTS_COVERED_BY_RETAINED_OFFICIAL_ALTERNATIVES",
            "recheck_required_before_release": True,
        },
        "retained_warnings": ["COUNTYWIDE_AT_LARGE_WITH_RESIDENCY", "TENURE_INTERVAL_UNRESOLVED"],
        "correction": {"reference": production.candidate.SOURCE_CORRECTION.copy(),
                       "csv_tables_checked": 7, "parity_ok": True,
                       "original_canonical_archive_replaced": False, "exact_intervals_added": 0},
        "activation_evidence": {
            "certified_head": CERTIFIED_ACTIVATION, "workflow_run_id": 34717704026,
            "workflow_url": "https://github.com/MightyLoud/CivicData/actions/runs/34717704026",
            "retention_receipt": str(RETENTION), "original_zip_sha256": ZIP_SHA,
            "live_json_sha256": LIVE_SHA, "mode": "RETAINED_LIVE_CIVIC_GPS",
            "positive_controls": 2, "negative_controls": 1, "idempotent_noops": 3,
            "negative_geography_basis": "RETAINED_MATCHED_HAWAII_COUNTY_GEOGRAPHY_AND_REJECTED_CONSUMER_RESULT",
            "fresh_live_run": False, "hosted_delivery_evidence": False,
        },
        "proposed_release": {"tag": TAG, "target_commit": TARGET, "assets": [ASSET],
                             "asset_type": "application/json", "raw_package_assets": False,
                             "officeholder_payload_assets": False, "tag_reserved": False},
        "holds": {"merge_authorized": False, "publication_authorized": False, "deployment_authorized": False,
                  "other_hi_production_counties": ["15001", "15003"],
                  "existing_kauai_installation_preserved": True,
                  "kalawao_work_authorized": False, "canonical_writes": 0},
    }


def schema_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    # This release version fixes every value. Nested const values also reject added payload fields.
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Immutable Maui metadata-only integration manifest v0.1",
            "type": "object", "additionalProperties": False, "required": sorted(manifest),
            "properties": {key: {"const": value} for key, value in manifest.items()}}


def validate_manifest(manifest: Any, receipt: dict[str, Any], today: date | None = None) -> None:
    validate_review(manifest_contract(receipt)["source_review"], today)
    require(encoded(manifest) == encoded(manifest_contract(receipt)), "MANIFEST_CONTRACT_DRIFT")


def verify_git(root: Path, head: str, base: str) -> dict[str, Any]:
    require(re.fullmatch(r"[a-f0-9]{40}", head) is not None and base == TARGET, "GIT_BASE_OR_HEAD_INVALID")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    require(git("rev-parse", "HEAD") == head, "CHECKOUT_HEAD_DRIFT")
    require(git("rev-parse", TARGET + "^{tree}") == TARGET_TREE
            and git("rev-parse", CERTIFIED_ACTIVATION + "^{tree}") == TARGET_TREE, "INTEGRATION_TREE_DRIFT")
    changed = git("diff", "--name-only", base, head).splitlines()
    require(set(changed) == ALLOWED_PATHS and len(changed) == len(ALLOWED_PATHS), "CANDIDATE_PATH_SCOPE_DRIFT")
    statuses = git("diff", "--name-status", "--no-renames", base, head).splitlines()
    expected_statuses = {("M" if path == "tools/ev_maui_activation_diff.py" else "A") + "\t" + path
                         for path in ALLOWED_PATHS}
    require(set(statuses) == expected_statuses, "CANDIDATE_CHANGE_TYPES_DRIFT")
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
              "source_review_expires_on": "2026-10-12", "release_asset_count": 1,
              "retained_zip_sha256": ZIP_SHA, "canonical_writes": 0,
              "merge_authorized": False, "publication_authorized": False, "deployment_authorized": False}
    if args.output_dir:
        write_bundle(root, args.output_dir, manifest, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
