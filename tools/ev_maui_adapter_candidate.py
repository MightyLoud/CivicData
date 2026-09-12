#!/usr/bin/env python3
"""Exercise Maui's inactive catalog path while retaining production holds."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_candidate as adapter, package_catalog, representation_catalog
from tools import ev_jurisdiction_onboarding as onboarding, ev_onboarding_materialize as materialize
from tools import ev_maui_countywide_preview as preview_runner, ev_maui_source_correction as correction

SPEC = Path("candidates/ev/maui_countywide.v0.1.json")
CATALOG = Path("candidates/ev/maui_catalog.v0.1.json")
ARTIFACTS = Path("artifacts/ev-maui-adapter-candidate")
require = correction.require


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def snapshot(root):
    result = preview_runner.snapshot(root)
    for folder in ("previews/ev/maui",):
        result.update({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (root / folder).rglob("*") if p.is_file()})
    for path in (SPEC, CATALOG, correction.CONFIG, correction.CORRECTION):
        result[str(path)] = hashlib.sha256((root / path).read_bytes()).hexdigest()
    return result


def verify_existing_route(root, spec):
    reference = spec["routing"]
    require(reference == {
        "strategy": "REUSE_GOVERNED_ROUTE", "adapter_id": "BASE-HI-MAUI-COUNTY", "geoid": "15009",
        "route_sha256": "695d2f3c0b7cb5d84bf4328c0cdc735ad8623101bd66b01032361a56d65359d2",
        "release_path": "civic_gps_extensions/hi_maui_county_release_v0.1.json",
        "release_sha256": "9ae1e0872ee347e0bbbe7a57721ecc67ac39cebc2c2d4b29cf06c04c8d3fe781",
    }, "MAUI_CANDIDATE_ROUTE_REFERENCE_DRIFT")
    holds = preview_runner.assert_holds(root)
    registry = json.loads((root / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
    route = next(r for r in registry["bundles"] if r.get("adapter_id") == reference["adapter_id"])
    require(hashlib.sha256(canonical(route).encode()).hexdigest() == reference["route_sha256"],
            "MAUI_CANDIDATE_ROUTE_HASH_DRIFT")
    require(hashlib.sha256((root / reference["release_path"]).read_bytes()).hexdigest()
            == reference["release_sha256"], "MAUI_CANDIDATE_RELEASE_HASH_DRIFT")
    return {"action": "VERIFY_EXISTING_ONLY", **reference, "routing_writes": 0, "production_hold": holds}


def build_candidate_catalog(root, spec):
    require(spec.get("spec_version") == "0.1", "MAUI_CANDIDATE_SPEC_VERSION_INVALID")
    entry = onboarding.build_catalog_entry(spec)
    require(entry == materialize.catalog_entry(spec), "MAUI_CANDIDATE_ONBOARDING_ROUNDTRIP_DRIFT")
    adapter.validate_entry(entry)
    catalog = {"catalog_version": "0.1", "entries": [entry]}
    require(catalog == json.loads((root / CATALOG).read_text()), "MAUI_CANDIDATE_CATALOG_DRIFT")
    preview = json.loads((root / correction.CONFIG).read_text())
    require(spec["source_review"] == {
        "review_kind": "REUSE_CERTIFIED_PREVIEW_REVIEW", "reviewed_on": "2026-09-12",
        "preview_merge_sha": "a6261b5baf9d95a16fa84e39f4f64fb6e50337d7",
        "scope": adapter.SCOPE, "references": preview["source_references"],
        "tenure_policy": "PRESERVE_UNRESOLVED_INTERVALS", "complete_jurisdiction": False,
    }, "MAUI_CANDIDATE_SOURCE_REVIEW_DRIFT")
    require(spec["live_addresses"] == preview["live_addresses"]
            and spec["negative_address"] == preview["negative_address"], "MAUI_CANDIDATE_CONTROLS_DRIFT")
    return catalog, verify_existing_route(root, spec)


def run_candidate(root, resolver, *, live=False):
    root = root.resolve()
    before = snapshot(root)
    try:
        spec = json.loads((root / SPEC).read_text())
        catalog, route = build_candidate_catalog(root, spec)
        preview = json.loads((root / correction.CONFIG).read_text())
        corrected, source_report = correction.verify_candidate(root, preview)
        package = package_catalog.reconstruct_package(catalog["entries"][0], root)
        require(package == corrected, "MAUI_CANDIDATE_CORRECTED_PACKAGE_DRIFT")
        observed = {
            "office_rows": len(package["records"]["offices"]),
            "current_holders": onboarding.count_current_holders(package),
            "leadership_rows": len(package["records"]["leadership_roles"]),
            "residency_areas": len(package["records"]["divisions"]),
            "source_evidence_rows": len(package["provenance"]["source_evidence"]),
            "source_assertion_rows": len(package["provenance"]["source_assertions"]),
            "qa_checks": len(package["qa"]["checks"]), "parity_ok": package["qa"]["parity_ok"],
            "qa_fail_count": package["qa"]["qa_fail_count"],
            "blocking_gap_count": package["qa"]["blocking_gap_count"],
        }
        require(observed == spec["expected"], "MAUI_CANDIDATE_PACKAGE_COUNTS_DRIFT")
        positives = []
        with tempfile.TemporaryDirectory(prefix="maui-catalog-candidate-") as temp:
            path = Path(temp) / "catalog.json"
            path.write_text(canonical(catalog), encoding="utf-8")
            for control in spec["live_addresses"]:
                address = control["address"]
                geographic = resolver.resolve(address, observed_on=None)
                result = representation_catalog.build_representation_from_catalog(
                    address, geographic, repo_root=root, catalog_path=path, allow_candidate=True)
                require(result.get("status") == "PASS" and result.get("package_catalog_entry_id") == adapter.ENTRY_ID
                    and (result["office_count"], result["current_holder_count"], result["residency_area_count"])
                        == (10, 10, 9) and all(result.get(k) is v for k, v in adapter.FLAGS.items()),
                    "MAUI_CANDIDATE_POSITIVE_FAILED:" + str(result.get("error")))
                require(not live or bool(result.get("matched_address")), "MAUI_CANDIDATE_LIVE_MATCH_MISSING")
                default = representation_catalog.build_representation_from_catalog(address, geographic,
                    repo_root=root, catalog_path=root / "consumers/empowered_vote/package_catalog.v0.1.json")
                denied = representation_catalog.build_representation_from_catalog(
                    address, geographic, repo_root=root, catalog_path=path)
                essentials = package_catalog.build_essentials_from_catalog(
                    address, geographic, repo_root=root, catalog_path=path)
                require(default.get("error") == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
                    and denied.get("error") == essentials.get("error") == "COUNTYWIDE_CANDIDATE_NOT_ENABLED"
                    and all("applicable_offices" not in r for r in (default, denied, essentials)),
                    "MAUI_CANDIDATE_PRODUCTION_ISOLATION_FAILED")
                positives.append({"control": control, "representation": result,
                    "default_catalog": default, "without_opt_in": denied, "full_essentials": essentials})
            require(len(positives) == 2 and positives[0]["representation"]["applicable_offices"]
                == positives[1]["representation"]["applicable_offices"], "MAUI_CANDIDATE_COUNTYWIDE_ROSTER_DRIFT")
            negative = spec["negative_address"]
            geographic = resolver.resolve(negative["address"], observed_on=None)
            normalized = adapter.preview.representation.live_civic_gps.normalize_civic_gps_result(
                negative["address"], geographic)
            require(normalized.get("status") == "PASS"
                and negative["expected_civic_jurisdiction_id"] in normalized["jurisdiction_ids"],
                "MAUI_CANDIDATE_NEGATIVE_GEOGRAPHY_UNRESOLVED")
            rejected = representation_catalog.build_representation_from_catalog(
                negative["address"], geographic, repo_root=root, catalog_path=path, allow_candidate=True)
            require(rejected.get("error") == "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS"
                and "applicable_offices" not in rejected, "MAUI_CANDIDATE_OUTSIDE_COUNTY_NOT_REJECTED")
        return {"gate": adapter.GATE, "status": "PASS", **adapter.FLAGS, "preview_only": True,
            "validation_mode": "LIVE_CIVIC_GPS" if live else "SYNTHETIC_FIXTURE",
            "source_commit": os.environ.get("CANDIDATE_HEAD_SHA") if live else None,
            "candidate_catalog": catalog, "catalog_sha256": hashlib.sha256(canonical(catalog).encode()).hexdigest(),
            "source_review": spec["source_review"], "source_correction": source_report,
            "package_counts": observed, "positive_controls": positives,
            "negative_control": {"control": negative, "geography": normalized, "result": rejected},
            "route_verification": route, "canonical_writes": 0, "auto_promoted": 0,
            "production_specs_created": 0, "protected_content_unchanged": True}
    finally:
        require(snapshot(root) == before, "MAUI_CANDIDATE_MODIFIED_PROTECTED_CONTENT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.repo_root.resolve(), args.output.resolve()
    if not output.is_relative_to(root / ARTIFACTS):
        raise SystemExit("Output must be under artifacts/ev-maui-adapter-candidate")
    from civic_gps_extensions.loader import load_resolver_with_extensions
    result = run_candidate(root, load_resolver_with_extensions(root, timeout_seconds=30.0), live=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate": adapter.GATE, "status": result["status"], "validation_mode": result["validation_mode"],
        "positive_controls": 2, "negative_controls": 1, "package_counts": result["package_counts"],
        "canonical_writes": 0, "auto_promoted": 0, **adapter.FLAGS}, sort_keys=True))


if __name__ == "__main__":
    main()
