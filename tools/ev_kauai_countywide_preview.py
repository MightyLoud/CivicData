#!/usr/bin/env python3
"""Replay two official Kauaʻi street addresses through an isolated preview."""
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

from consumers.empowered_vote import countywide_preview as preview, package_catalog
from tools import ev_onboarding_proposal as proposal

CONFIG = Path("previews/ev/kauai_countywide.v0.1.json")
HI_IDS = {f"jurisdiction-hi-{name}-county" for name in ("hawaii", "honolulu", "kauai", "maui")}


def snapshot(root: Path) -> dict[str, str]:
    """Protect packages, production configuration, and the Civic GPS runtime."""
    paths = [root / "consumers/empowered_vote/package_catalog.v0.1.json"]
    for folder in ("data/packages", "onboarding/ev", "civic_gps_extensions", "civic_gps_runtime_parts"):
        paths.extend(p for p in (root / folder).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def assert_holds(root: Path) -> list[dict[str, str]]:
    registry = json.loads((root / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
    routes = [row for row in registry["bundles"] if row.get("adapter_id", "").startswith("BASE-HI-")]
    if {row["adapter_id"] for row in routes} != {
        "BASE-HI-HAWAII-COUNTY", "BASE-HI-HONOLULU-COUNTY", "BASE-HI-KAUAI-COUNTY", "BASE-HI-MAUI-COUNTY"
    }:
        raise ValueError("Hawaiʻi route set drift")
    for row in routes:
        if row.get("ev_onboarding_status") != "ROUTING_ONLY" or not (row.get("scope_match") or {}).get("all"):
            raise ValueError("routing-only contract drift")
    catalog = json.loads((root / "consumers/empowered_vote/package_catalog.v0.1.json").read_text())
    if any(row.get("package_jurisdiction_id") in HI_IDS for row in catalog["entries"]):
        raise ValueError("Hawaiʻi production catalog promotion detected")
    for path in (root / "onboarding/ev").glob("*.json"):
        if json.loads(path.read_text()).get("package_jurisdiction_id") in HI_IDS:
            raise ValueError("Hawaiʻi production onboarding spec detected")
    results = []
    for jid in sorted(HI_IDS):
        row = proposal.propose(root, jid)
        if row["status"] != "REVIEW_REQUIRED" or row["production_spec"] is not None:
            raise ValueError("Hawaiʻi proposal hold changed")
        results.append({"package_jurisdiction_id": jid, "status": row["status"]})
    return results


def run_preview(root: Path, resolver: Any, *, live: bool) -> dict[str, Any]:
    root = root.resolve()
    before = snapshot(root)
    binding = json.loads((root / CONFIG).read_text())
    package = package_catalog.reconstruct_package(binding, root)
    controls = binding["live_addresses"]
    if (len(controls) != 2 or len({r["address"] for r in controls}) != 2
            or any("POINT(" in r["address"] or not r.get("source_url", "").startswith("https://") for r in controls)):
        raise ValueError("Two distinct sourced street addresses required")
    positives = []
    for control in controls:
        geographic = resolver.resolve(control["address"], observed_on=None)
        result = preview.preview_countywide_representation(package, control["address"], geographic, binding=binding)
        if result["status"] != "PASS" or result["office_count"] != 2 or result["current_holder_count"] != 8:
            raise ValueError("Kauaʻi positive control failed: " + json.dumps(result))
        if live and not result.get("matched_address"):
            raise ValueError("Live control lacks a geocoder matched address")
        positives.append({"control": control, "representation": result})
    first, second = [r["representation"]["applicable_offices"] for r in positives]
    if first != second:
        raise ValueError("Countywide representation differs between address controls")
    negative = binding["negative_address"]
    geographic = resolver.resolve(negative["address"], observed_on=None)
    normalized = preview.representation.live_civic_gps.normalize_civic_gps_result(negative["address"], geographic)
    if normalized.get("status") != "PASS" or negative["expected_civic_jurisdiction_id"] not in normalized["jurisdiction_ids"]:
        raise ValueError("Negative control did not successfully resolve its expected county")
    rejected = preview.preview_countywide_representation(package, negative["address"], geographic, binding=binding)
    if rejected.get("error") != "CIVIC_GPS_JURISDICTION_NOT_ACTIVE" or "applicable_offices" in rejected:
        raise ValueError("Outside-county preview did not fail closed")
    holds = assert_holds(root)
    if snapshot(root) != before:
        raise ValueError("Protected repository contents changed during preview")
    return {"gate": "EV-KAUAI-PREVIEW-001", "status": "PASS",
            "validation_mode": "LIVE_CIVIC_GPS" if live else "SYNTHETIC_FIXTURE",
            "preview_only": True, "publication_eligible": False, "complete_jurisdiction": False,
            "canonical_writes": 0, "auto_promoted": 0, "production_specs_created": 0,
            "protected_content_unchanged": True, "artifact_sha256": binding["artifact"]["archive_sha256"],
            "positive_controls": positives, "negative_control": {"control": negative, "result": rejected},
            "routing_holds": holds}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()
    output = args.output.resolve()
    # Evidence output may not overwrite sources or application code.
    if output.is_relative_to(root) and not output.is_relative_to(root / "artifacts/ev-kauai-preview"):
        raise SystemExit("Preview output within the repository must be under artifacts/ev-kauai-preview")
    from civic_gps_extensions.loader import load_resolver_with_extensions
    resolver = load_resolver_with_extensions(root, timeout_seconds=30.0)
    result = run_preview(root, resolver, live=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "validation_mode": result["validation_mode"],
                      "positive_controls": len(result["positive_controls"]), "negative_controls": 1,
                      "offices_per_positive": 2, "holders_per_positive": 8,
                      "routing_only_counties": len(result["routing_holds"]), "auto_promoted": 0,
                      "canonical_writes": 0, "publication_eligible": False}, sort_keys=True))


if __name__ == "__main__":
    main()
