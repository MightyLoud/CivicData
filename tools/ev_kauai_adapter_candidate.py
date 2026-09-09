#!/usr/bin/env python3
"""Stage and exercise an inactive Kauaʻi catalog candidate; never activate it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import countywide_candidate as adapter, package_catalog, representation_catalog
from tools import ev_jurisdiction_onboarding as onboarding, ev_onboarding_materialize as materialize
from tools import ev_kauai_countywide_preview as preview_runner

SPEC = Path("candidates/ev/kauai_countywide.v0.1.json")
CATALOG = Path("candidates/ev/kauai_catalog.v0.1.json")
ARTIFACTS = Path("artifacts/ev-kauai-adapter-candidate")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def verify_existing_route(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    reference = spec["routing"]
    require(reference.get("strategy") == "REUSE_GOVERNED_ROUTE"
            and reference.get("adapter_id") == "BASE-HI-KAUAI-COUNTY"
            and reference.get("geoid") == "15007", "candidate route reference invalid")
    registry = json.loads((root / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
    matches = [row for row in registry["bundles"] if row.get("adapter_id") == reference["adapter_id"]]
    require(len(matches) == 1, "candidate requires exactly one existing route")
    route = matches[0]
    digest = hashlib.sha256(canonical(route).encode()).hexdigest()
    require(digest == reference["route_sha256"], "existing route hash drift")
    require(route.get("ev_onboarding_status") == "ROUTING_ONLY"
            and route.get("scope_match") == {"all": [
                {"geography": "state", "fields": ["GEOID", "STATE"], "equals": "15"},
                {"geography": "county", "fields": ["GEOID"], "equals": "15007"}]}
            and not route.get("district_adapters")
            and not route.get("applicable_office_rules")
            and not route.get("action_registry_files"), "existing route contract drift")
    require(reference.get("release_path") == "civic_gps_extensions/hi_kauai_county_release_v0.1.json"
            and route.get("release_files") == ["../" + reference["release_path"]],
            "existing route release reference drift")
    raw = (root / reference["release_path"]).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == reference["release_sha256"], "routing release hash drift")
    release = json.loads(raw)["payload"]
    require(release.get("offices") == [] and release.get("officeholders") == []
            and [row.get("jurisdiction_id") for row in release["jurisdictions"]] == [adapter.preview.CIVIC_ID],
            "routing release acquired civic facts")
    return {"action": "VERIFY_EXISTING_ONLY", "adapter_id": reference["adapter_id"],
            "route_sha256": digest, "release_sha256": reference["release_sha256"], "routing_writes": 0}


def build_candidate_catalog(root: Path, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    require(spec.get("spec_version") == "0.1", "unsupported candidate spec")
    entry = onboarding.build_catalog_entry(spec)
    require(entry == materialize.catalog_entry(spec), "candidate onboarding binding roundtrip drift")
    adapter.validate_entry(entry)
    route = verify_existing_route(root, spec)
    catalog = {"catalog_version": "0.1", "entries": [entry]}
    require(catalog == json.loads((root / CATALOG).read_text()), "checked candidate catalog drift")
    review = spec["source_review"]
    require(review.get("review_kind") == "ROSTER_CROSSCHECK_ONLY"
            and review.get("reviewed_on") == "2026-09-09"
            and review.get("package_observed_on") == "2026-08-23"
            and review.get("revalidate_before") == "2026-12-01"
            and review.get("scope") == adapter.SCOPE
            and review.get("known_omitted_offices") == ["Prosecuting Attorney"]
            and review.get("identity_policy") == "PRESERVE_LEGACY_ACTIVE_REJECT_EXPLICIT_PROVISIONAL"
            and review.get("tenure_policy") == "PRESERVE_UNRESOLVED_INTERVALS"
            and review.get("source_urls") == [
                "https://elections.hawaii.gov/cok-mayor/",
                "https://elections.hawaii.gov/cok-councilmembers/",
                "https://elections.hawaii.gov/cok-prosecuting-attorney/",
                "https://elections.hawaii.gov/2026-proclamation/"], "candidate source review drift")
    return catalog, route


def run_candidate(root: Path, resolver: Any, *, live: bool) -> dict[str, Any]:
    root = root.resolve()
    before = preview_runner.snapshot(root)
    spec = json.loads((root / SPEC).read_text())
    catalog, route = build_candidate_catalog(root, spec)
    package = package_catalog.reconstruct_package(catalog["entries"][0], root)
    observed = {
        "office_rows": len(package["records"]["offices"]),
        "current_holders": onboarding.count_current_holders(package),
        "leadership_rows": len(package["records"]["leadership_roles"]),
        "source_evidence_rows": len(package["provenance"]["source_evidence"]),
        "source_assertion_rows": len(package["provenance"]["source_assertions"]),
        "qa_checks": len(package["qa"]["checks"]),
        "parity_ok": package["qa"]["parity_ok"], "qa_fail_count": package["qa"]["qa_fail_count"],
        "blocking_gap_count": package["qa"]["blocking_gap_count"],
    }
    require(observed == spec["expected"], "candidate package counts drift")
    preview_spec = json.loads((root / preview_runner.CONFIG).read_text())
    require(spec["live_addresses"] == preview_spec["live_addresses"]
            and spec["negative_address"] == preview_spec["negative_address"], "certified address controls drift")
    controls = spec["live_addresses"]
    require(len(controls) == 2 and len({row["address"] for row in controls}) == 2
            and all("POINT(" not in row["address"] and row["source_url"].startswith("https://")
                    for row in controls), "two distinct sourced street controls required")
    positives = []
    with tempfile.TemporaryDirectory() as td:
        staged_catalog = Path(td) / "candidate-catalog.json"
        staged_catalog.write_text(canonical(catalog), encoding="utf-8")
        # Exercise actual loading, selection, archive reconstruction and dispatch for every address.
        for control in controls:
            geographic = resolver.resolve(control["address"], observed_on=None)
            model = representation_catalog.build_representation_from_catalog(
                control["address"], geographic, repo_root=root, catalog_path=staged_catalog, allow_candidate=True)
            require(model.get("status") == "PASS", "candidate positive control failed: " + canonical(model))
            require(model.get("package_catalog_entry_id") == adapter.ENTRY_ID
                    and model.get("office_count") == 2 and model.get("current_holder_count") == 8
                    and all(model.get(key) is value for key, value in adapter.FLAGS.items()),
                    "candidate catalog projection contract drift")
            if live:
                require(bool(model.get("matched_address")), "live positive lacks matched address")
            default = representation_catalog.build_representation_from_catalog(
                control["address"], geographic, repo_root=root,
                catalog_path=root / "consumers/empowered_vote/package_catalog.v0.1.json")
            require(default.get("error") == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS",
                    "default production catalog acquired Kauaʻi")
            denied = representation_catalog.build_representation_from_catalog(
                control["address"], geographic, repo_root=root, catalog_path=staged_catalog)
            require(denied.get("error") == "COUNTYWIDE_CANDIDATE_NOT_ENABLED", "candidate opt-in bypassed")
            positives.append({"control": control, "representation": model})
        require(positives[0]["representation"]["applicable_offices"] ==
                positives[1]["representation"]["applicable_offices"], "countywide roster varies by address")
        negative = spec["negative_address"]
        geographic = resolver.resolve(negative["address"], observed_on=None)
        normalized = adapter.preview.representation.live_civic_gps.normalize_civic_gps_result(negative["address"], geographic)
        require(normalized.get("status") == "PASS" and negative["expected_civic_jurisdiction_id"]
                in normalized["jurisdiction_ids"], "negative control did not resolve its expected county")
        if live:
            require(bool(normalized.get("matched_address")), "live negative lacks matched address")
        rejected = representation_catalog.build_representation_from_catalog(
            negative["address"], geographic, repo_root=root, catalog_path=staged_catalog, allow_candidate=True)
        require(rejected.get("error") == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
                and "applicable_offices" not in rejected, "outside-county candidate did not fail closed")
    holds = preview_runner.assert_holds(root)
    require(before == preview_runner.snapshot(root), "protected repository contents changed")
    return {"gate": adapter.GATE, "status": "PASS", **adapter.FLAGS,
            "validation_mode": "LIVE_CIVIC_GPS" if live else "SYNTHETIC_FIXTURE",
            "source_commit": os.environ.get("CANDIDATE_HEAD_SHA") if live else None,
            "scope": adapter.SCOPE, "archive_sha256": adapter.ARCHIVE_SHA256,
            "candidate_catalog": catalog, "candidate_catalog_sha256": hashlib.sha256(canonical(catalog).encode()).hexdigest(),
            "source_review": spec["source_review"], "observed": observed,
            "positive_controls": positives, "negative_control": {"control": negative, "result": rejected},
            "existing_route": route, "routing_holds": holds,
            "auto_promoted": 0, "production_specs_created": 0, "canonical_writes": 0,
            "protected_content_unchanged": True}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root, output = args.repo_root.resolve(), args.output.resolve()
    require(not output.is_relative_to(root) or output.is_relative_to(root / ARTIFACTS),
            "candidate evidence within repository must stay under its artifacts directory")
    from civic_gps_extensions.loader import load_resolver_with_extensions
    result = run_candidate(root, load_resolver_with_extensions(root), live=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(canonical({"status": result["status"], "validation_mode": result["validation_mode"],
                     "source_commit": result["source_commit"], "positive_controls": 2, "negative_controls": 1,
                     "offices_per_positive": 2, "holders_per_positive": 8, "routing_only_counties": 4,
                     "auto_promoted": 0, "canonical_writes": 0, **adapter.FLAGS}).strip())


if __name__ == "__main__":
    main()
