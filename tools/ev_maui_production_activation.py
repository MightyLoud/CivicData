#!/usr/bin/env python3
"""Verify Maui's proposed default-catalog activation without external writes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_production as production, representation_catalog
from tools import ev_maui_adapter_candidate as adapter_runner, ev_maui_source_correction as correction
from tools import ev_kauai_countywide_preview as hi_runner, ev_onboarding_materialize as materialize

ARTIFACTS = Path("artifacts/ev-maui-production-activation")
GATE = "EV-MAUI-PROD-ACTIVATION-CANDIDATE-001"
require = correction.require


def run_activation(root, resolver, *, live=False):
    root = root.resolve()
    before = adapter_runner.snapshot(root)
    try:
        spec = production.installed_spec(root)
        require(spec is not None, "MAUI_PRODUCTION_INSTALLATION_MISSING")
        receipt = production.validate_spec(spec, root)
        binding = json.loads((root / correction.CONFIG).read_text())
        _, parity = correction.verify_candidate(root, binding)
        positives = []
        for address in spec["live_addresses"]:
            geographic = resolver.resolve(address, observed_on=None)
            result = representation_catalog.build_representation_from_catalog(address, geographic,
                repo_root=root, catalog_path=root / "consumers/empowered_vote/package_catalog.v0.1.json")
            require(result.get("status") == "PASS" and result.get("package_catalog_entry_id") == production.ENTRY_ID
                and result.get("production_profile_id") == production.PROFILE_ID
                and result.get("preview_only") is False
                and (result["office_count"], result["current_holder_count"], result["residency_area_count"]) == (10, 10, 9)
                and all(result.get(k) is v for k, v in production.FLAGS.items()),
                "MAUI_PRODUCTION_POSITIVE_FAILED:" + str(result.get("error")))
            require(not live or bool(result.get("matched_address")), "MAUI_PRODUCTION_LIVE_MATCH_MISSING")
            denied = representation_catalog.build_representation_from_catalog(address, geographic,
                repo_root=root, catalog_path=root / adapter_runner.CATALOG)
            require(denied.get("error") == "COUNTYWIDE_CANDIDATE_NOT_ENABLED"
                and "applicable_offices" not in denied, "MAUI_CANDIDATE_OPT_IN_BYPASSED")
            positives.append({"address": address, "representation": result, "candidate_without_opt_in": denied})
        require(len(positives) == 2 and positives[0]["representation"]["applicable_offices"]
            == positives[1]["representation"]["applicable_offices"], "MAUI_PRODUCTION_COUNTYWIDE_ROSTER_DRIFT")
        negative = receipt["negative_control"]
        geographic = resolver.resolve(negative["address"], observed_on=None)
        normalized = production.candidate.preview.representation.live_civic_gps.normalize_civic_gps_result(
            negative["address"], geographic)
        require(normalized.get("status") == "PASS"
            and negative["expected_civic_jurisdiction_id"] in normalized["jurisdiction_ids"]
            and (not live or bool(normalized.get("matched_address"))), "MAUI_PRODUCTION_NEGATIVE_GEOGRAPHY_UNRESOLVED")
        rejected = representation_catalog.build_representation_from_catalog(negative["address"], geographic,
            repo_root=root, catalog_path=root / "consumers/empowered_vote/package_catalog.v0.1.json")
        require(rejected.get("error") == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
            and "applicable_offices" not in rejected, "MAUI_PRODUCTION_OUTSIDE_COUNTY_NOT_REJECTED")
        with tempfile.TemporaryDirectory(prefix="maui-activation-noop-") as temp:
            replay = materialize.materialize(root, production.candidate.preview.PACKAGE_ID, Path(temp))
            require(replay.get("changes_required") == 0 and len(replay["changes"]) == 3
                and all(r["action"] == "NOOP" for r in replay["changes"]), "MAUI_PRODUCTION_NOT_IDEMPOTENT")
        dispositions = hi_runner.assert_holds(root)
        require({r["package_jurisdiction_id"]: r["status"] for r in dispositions} == {
            "jurisdiction-hi-kauai-county": "READY", "jurisdiction-hi-maui-county": "READY",
            "jurisdiction-hi-hawaii-county": "REVIEW_REQUIRED", "jurisdiction-hi-honolulu-county": "REVIEW_REQUIRED"},
            "MAUI_OTHER_COUNTY_HOLDS_DRIFT")
        return {"gate": GATE, "status": "PASS", "validation_mode": "LIVE_CIVIC_GPS" if live else "SYNTHETIC_FIXTURE",
            "source_commit": os.environ.get("ACTIVATION_HEAD_SHA") if live else None,
            "entry_id": production.ENTRY_ID, "profile_id": production.PROFILE_ID, **production.FLAGS,
            "archive_sha256": production.candidate.ARTIFACT["archive_sha256"],
            "acceptance_receipt_sha256": spec["countywide_profile"]["acceptance_receipt"]["sha256"],
            "source_review": production.REVIEW_REFERENCE, "source_review_expires_on": "2026-10-12",
            "source_correction_parity": parity, "positive_controls": positives,
            "negative_control": {"control": negative, "geography": normalized, "result": rejected},
            "idempotence": replay, "hi_dispositions": dispositions, "explicit_maui_installations": 1,
            "auto_promoted": 0, "canonical_writes": 0, "publication_authorized": False,
            "deployment_authorized": False, "protected_content_unchanged": True}
    finally:
        require(adapter_runner.snapshot(root) == before, "MAUI_ACTIVATION_MODIFIED_PROTECTED_CONTENT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.repo_root.resolve(), args.output.resolve()
    require(output.is_relative_to(root / ARTIFACTS), "Output must be under artifacts/ev-maui-production-activation")
    from civic_gps_extensions.loader import load_resolver_with_extensions
    report = run_activation(root, load_resolver_with_extensions(root, timeout_seconds=30.0), live=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate": GATE, "status": report["status"], "validation_mode": report["validation_mode"],
        "source_commit": report["source_commit"], "positive_controls": 2, "negative_controls": 1,
        "offices": 10, "holders": 10, "residency_areas": 9, "idempotent_noops": 3,
        "canonical_writes": 0, "auto_promoted": 0, "publication_authorized": False, "deployment_authorized": False}))


if __name__ == "__main__":
    main()
