#!/usr/bin/env python3
"""Verify the proposed default-catalog activation; never publish or deploy."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import countywide_production as production, representation_catalog
from tools import ev_onboarding_materialize as materialize, ev_kauai_countywide_preview as preview_runner

ARTIFACTS = Path("artifacts/ev-kauai-production-activation")


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def run_activation(root: Path, resolver: Any, *, live: bool) -> dict[str, Any]:
    root = root.resolve()
    before = preview_runner.snapshot(root)
    spec = production.installed_spec(root)
    require(spec is not None, "Kauaʻi production catalog/spec pair missing")
    receipt = production.validate_spec(spec, root)
    positives = []
    for address in spec["live_addresses"]:
        geographic = resolver.resolve(address, observed_on=None)
        model = representation_catalog.build_representation_from_catalog(
            address, geographic, repo_root=root,
            catalog_path=root / "consumers/empowered_vote/package_catalog.v0.1.json")
        require(model.get("status") == "PASS", "production positive failed: " + json.dumps(model))
        require(model.get("package_catalog_entry_id") == production.ENTRY_ID
                and model.get("production_profile_id") == production.PROFILE_ID
                and model.get("office_count") == 2 and model.get("current_holder_count") == 8
                and model.get("preview_only") is False
                and all(model.get(k) is v for k, v in production.FLAGS.items()), "production projection drift")
        if live:
            require(bool(model.get("matched_address")), "live positive lacks matched address")
        positives.append({"address": address, "representation": model})
    require(len(positives) == 2 and positives[0]["representation"]["applicable_offices"] ==
            positives[1]["representation"]["applicable_offices"], "countywide roster differs by address")
    negative = receipt["negative_control"]
    geographic = resolver.resolve(negative["address"], observed_on=None)
    normalized = production.candidate.preview.representation.live_civic_gps.normalize_civic_gps_result(negative["address"], geographic)
    require(normalized.get("status") == "PASS" and negative["expected_civic_jurisdiction_id"] in normalized["jurisdiction_ids"],
            "outside-county negative did not successfully resolve")
    if live:
        require(bool(normalized.get("matched_address")), "live negative lacks matched address")
    rejected = representation_catalog.build_representation_from_catalog(
        negative["address"], geographic, repo_root=root,
        catalog_path=root / "consumers/empowered_vote/package_catalog.v0.1.json")
    require(rejected.get("error") == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
            and "applicable_offices" not in rejected, "outside-county production selection did not reject")
    with tempfile.TemporaryDirectory() as td:
        replay = materialize.materialize(root, production.candidate.preview.PACKAGE_ID, Path(td))
        require(replay.get("changes_required") == 0 and all(row["action"] == "NOOP" for row in replay["changes"]),
                "production onboarding is not idempotent")
    holds = preview_runner.assert_holds(root)
    require(sum(row["status"] == "READY" for row in holds) == 1
            and sum(row["status"] == "REVIEW_REQUIRED" for row in holds) == 3, "other Hawaiʻi production holds drift")
    require(before == preview_runner.snapshot(root), "protected repository contents changed")
    return {"gate": "EV-KAUAI-PROD-ACTIVATION-CANDIDATE-001", "status": "PASS",
            "validation_mode": "LIVE_CIVIC_GPS" if live else "SYNTHETIC_FIXTURE",
            "source_commit": os.environ.get("ACTIVATION_HEAD_SHA") if live else None,
            "entry_id": production.ENTRY_ID, "scope": production.candidate.SCOPE,
            "archive_sha256": production.candidate.ARCHIVE_SHA256,
            "acceptance_receipt_sha256": spec["countywide_profile"]["acceptance_receipt"]["sha256"],
            "source_review": receipt["source_review"], "positive_controls": positives,
            "negative_control": {"control": negative, "result": rejected}, "idempotence": replay,
            "hi_dispositions": holds, "explicit_kauai_entries": 1, "other_hi_production_holds": 3,
            "routing_release_offices": 0, "routing_release_holders": 0,
            "auto_promoted": 0, "canonical_writes": 0, "publication_authorized": False,
            "deployment_authorized": False, "protected_content_unchanged": True}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root, output = args.repo_root.resolve(), args.output.resolve()
    require(not output.is_relative_to(root) or output.is_relative_to(root / ARTIFACTS),
            "activation evidence within repository must stay under its artifacts directory")
    from civic_gps_extensions.loader import load_resolver_with_extensions
    result = run_activation(root, load_resolver_with_extensions(root), live=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "validation_mode": result["validation_mode"],
        "source_commit": result["source_commit"], "positive_controls": 2, "negative_controls": 1,
        "office_count": 2, "current_holder_count": 8, "other_hi_production_holds": 3,
        "auto_promoted": 0, "canonical_writes": 0, "publication_authorized": False, "deployment_authorized": False}))


if __name__ == "__main__":
    main()
