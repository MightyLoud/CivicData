#!/usr/bin/env python3
"""Validate the held correction and run Maui countywide address controls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_preview as preview, countywide_production
from tools import ev_maui_source_correction as correction, ev_onboarding_proposal as proposal

CONFIG = correction.CONFIG
RUNTIME_SHA256 = "32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797"


def snapshot(root):
    paths = [root / "consumers/empowered_vote/package_catalog.v0.1.json"]
    for folder in ("data/packages/hi/maui-county", "onboarding/ev", "acceptance/ev",
                   "consumers/empowered_vote", "civic_gps_extensions", "civic_gps_runtime_parts"):
        paths.extend(p for p in (root / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc")
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


def assert_holds(root):
    require = correction.require
    catalog = json.loads((root / "consumers/empowered_vote/package_catalog.v0.1.json").read_text())
    require(not any(r.get("package_jurisdiction_id") == preview.PACKAGE_ID
                    or r.get("civic_gps_jurisdiction_id") == preview.CIVIC_ID
                    for r in catalog["entries"]), "MAUI_PRODUCTION_CATALOG_PROMOTION")
    for path in (root / "onboarding/ev").glob("*.json"):
        require(json.loads(path.read_text()).get("package_jurisdiction_id") != preview.PACKAGE_ID,
                "MAUI_PRODUCTION_SPEC_CREATED")
    require(countywide_production.installed_spec(root) is not None, "KAUAI_EXISTING_INSTALLATION_MISSING")
    registry_path = Path("civic_gps_extensions/registry_bundles.v0.1.json")
    registry = json.loads((root / registry_path).read_text())
    matches = [r for r in registry["bundles"] if r.get("adapter_id") == "BASE-HI-MAUI-COUNTY"]
    require(len(matches) == 1, "MAUI_ROUTE_MISSING_OR_DUPLICATED")
    route = matches[0]
    require(route.get("ev_onboarding_status") == "ROUTING_ONLY"
            and route.get("district_adapters") == [] and route.get("applicable_office_rules") == []
            and route.get("scope_match") == {"all": [
                {"geography": "state", "fields": ["GEOID", "STATE"], "equals": "15"},
                {"geography": "county", "fields": ["GEOID"], "equals": "15009"}]},
            "MAUI_ROUTING_ONLY_CONTRACT_DRIFT")
    release_path = "../civic_gps_extensions/hi_maui_county_release_v0.1.json"
    require(route.get("release_files") == [release_path], "MAUI_ROUTING_RELEASE_DRIFT")
    release = json.loads((root / "civic_gps_extensions/hi_maui_county_release_v0.1.json").read_text())
    require(release["payload"]["offices"] == [] and release["payload"]["officeholders"] == []
            and [r["jurisdiction_id"] for r in release["payload"]["jurisdictions"]] == [preview.CIVIC_ID],
            "MAUI_ROUTING_RELEASE_CONTAINS_CIVIC_FACTS")
    # Run the unchanged proposal on Maui alone; no all-county discovery or Kalawao reads.
    with tempfile.TemporaryDirectory(prefix="maui-proposal-hold-") as temp:
        isolated = Path(temp)
        (isolated / registry_path).parent.mkdir(parents=True)
        shutil.copyfile(root / registry_path, isolated / registry_path)
        package_path = Path("data/packages/hi/maui-county")
        shutil.copytree(root / package_path, isolated / package_path)
        held = proposal.propose(isolated, preview.PACKAGE_ID)
    require(held["status"] == "REVIEW_REQUIRED" and held["production_spec"] is None,
            "MAUI_PROPOSAL_HOLD_CHANGED")
    runtime = b"".join(p.read_bytes() for p in sorted((root / "civic_gps_runtime_parts").glob("part.*")))
    require(hashlib.sha256(runtime).hexdigest() == RUNTIME_SHA256, "CORE_RUNTIME_SHA256_DRIFT")
    return {"package_jurisdiction_id": preview.PACKAGE_ID, "status": held["status"],
            "production_spec": None, "ev_onboarding_status": "ROUTING_ONLY",
            "kauai_existing_installation": "PRESERVED", "runtime_sha256": RUNTIME_SHA256}


def run_preview(root, resolver, *, live=False):
    root = root.resolve()
    before = snapshot(root)
    try:
        binding = json.loads((root / CONFIG).read_text())
        package, source_report = correction.verify_candidate(root, binding)
        controls = binding["live_addresses"]
        correction.require(len(controls) == 2 and len({c["address"] for c in controls}) == 2
            and all(c["source_url"].startswith("https://") and "POINT(" not in c["address"]
                    for c in controls), "MAUI_TWO_SOURCED_STREETS_REQUIRED")
        positives = []
        for control in controls:
            geographic = resolver.resolve(control["address"], observed_on=None)
            result = preview.preview_maui_representation(package, control["address"], geographic, binding=binding)
            correction.require(result["status"] == "PASS"
                and (result["office_count"], result["current_holder_count"], result["residency_area_count"]) == (10, 10, 9),
                "MAUI_POSITIVE_CONTROL_FAILED:" + str(result.get("error")))
            correction.require(not live or bool(result.get("matched_address")), "MAUI_LIVE_MATCHED_ADDRESS_MISSING")
            positives.append({"control": control, "representation": result})
        correction.require(positives[0]["representation"]["applicable_offices"]
            == positives[1]["representation"]["applicable_offices"], "MAUI_COUNTYWIDE_ROSTER_DIFFERS_BY_ADDRESS")
        negative = binding["negative_address"]
        geographic = resolver.resolve(negative["address"], observed_on=None)
        normalized = preview.representation.live_civic_gps.normalize_civic_gps_result(negative["address"], geographic)
        correction.require(normalized.get("status") == "PASS"
            and negative["expected_civic_jurisdiction_id"] == "jur-us-hi-hawaii-county"
            and negative["expected_civic_jurisdiction_id"] in normalized["jurisdiction_ids"],
            "MAUI_NEGATIVE_GEOGRAPHY_UNRESOLVED")
        rejected = preview.preview_maui_representation(package, negative["address"], geographic, binding=binding)
        correction.require(rejected.get("error") == "CIVIC_GPS_JURISDICTION_NOT_ACTIVE"
            and "applicable_offices" not in rejected, "MAUI_OUTSIDE_COUNTY_NOT_REJECTED")
        holds = assert_holds(root)
        return {"gate": preview.GATE, "status": "PASS",
            "validation_mode": "LIVE_CIVIC_GPS" if live else "SYNTHETIC_FIXTURE",
            "preview_only": True, "publication_eligible": False, "complete_jurisdiction": False,
            "canonical_writes": 0, "auto_promoted": 0, "production_specs_created": 0,
            "protected_content_unchanged": True, "source_correction": source_report,
            "positive_controls": positives, "negative_control": {"control": negative, "result": rejected},
            "production_hold": holds}
    finally:
        correction.require(snapshot(root) == before, "MAUI_PREVIEW_MODIFIED_PROTECTED_CONTENT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.repo_root.resolve(), args.output.resolve()
    if not output.is_relative_to(root / "artifacts/ev-maui-preview"):
        raise SystemExit("Output must be under artifacts/ev-maui-preview")
    from civic_gps_extensions.loader import load_resolver_with_extensions
    resolver = load_resolver_with_extensions(root, timeout_seconds=30.0)
    result = run_preview(root, resolver, live=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"gate": preview.GATE, "status": result["status"], "validation_mode": result["validation_mode"],
        "positive_controls": 2, "negative_controls": 1, "offices_per_positive": 10,
        "holders_per_positive": 10, "residency_areas": 9, "source_correction": "PASS",
        "canonical_writes": 0, "auto_promoted": 0, "publication_eligible": False}, sort_keys=True))


if __name__ == "__main__":
    main()
