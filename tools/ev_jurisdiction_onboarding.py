#!/usr/bin/env python3
"""Build/verify deterministic Empowered.Vote jurisdiction onboarding artifacts.

This tool does not create civic facts. It consumes an already governed
Jurisdiction Package artifact and produces only consumer routing metadata:
a package-catalog entry, a routing-only Civic GPS extension bundle, and an
acceptance report. The package remains authoritative for civic facts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import package_catalog, package_source

SPEC_VERSION = "0.1"


class OnboardingError(ValueError):
    pass


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise OnboardingError(f"expected object: {path}")
    return data


def build_catalog_entry(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": spec["entry_id"],
        "profile": spec["profile"],
        "civic_gps_jurisdiction_id": spec["civic_gps_jurisdiction_id"],
        "package_jurisdiction_id": spec["package_jurisdiction_id"],
        "package_schema_version": spec["package_schema_version"],
        "artifact": spec["artifact"],
        **({"district_binding": spec["district_binding"]} if spec.get("district_binding") else {}),
    }


def build_routing_bundle(spec: dict[str, Any]) -> dict[str, Any]:
    routing = spec["routing"]
    geoid = str(routing["geoid"])
    geography = str(routing.get("geography", "place"))
    return {
        "adapter_id": routing["adapter_id"],
        "mode": "BASE",
        "priority": int(routing.get("priority", 80)),
        "scope_match": {"geography": geography, "fields": ["GEOID"], "equals": geoid},
        "division_rules": [{
            "division_id": routing["division_id"],
            "name": routing["division_name"],
            "type": routing.get("division_type", "municipality"),
            "when": {"geography": geography, "fields": ["GEOID"], "equals": geoid},
        }],
        "jurisdictions": [{
            "jurisdiction_id": spec["civic_gps_jurisdiction_id"],
            "activation": {"geography": geography, "fields": ["GEOID"], "equals": geoid},
        }],
        "release_files": list(routing.get("release_files", [])),
        "district_adapters": list(routing.get("district_adapters", [])),
        "applicable_office_rules": [],
        "action_registry_files": [],
        "known_gaps": list(routing.get("known_gaps", [])),
    }


def count_current_holders(package: dict[str, Any]) -> int:
    return sum(
        1
        for row in package["records"]["role_terms"]
        if str(row.get("status") or row.get("currentness_status", "")).upper().startswith("CURRENT")
    )


def find_existing(repo_root: Path, entry: dict[str, Any], bundle: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    catalog = load_json(repo_root / "consumers/empowered_vote/package_catalog.v0.1.json")
    existing_entry = next((x for x in catalog.get("entries", []) if x.get("entry_id") == entry["entry_id"]), None)
    registry = load_json(repo_root / "civic_gps_extensions/registry_bundles.v0.1.json")
    existing_bundle = next((x for x in registry.get("bundles", []) if x.get("adapter_id") == bundle["adapter_id"]), None)
    return existing_entry, existing_bundle


def run(spec_path: Path, repo_root: Path, out: Path, verify_current: bool) -> dict[str, Any]:
    spec = load_json(spec_path)
    if str(spec.get("spec_version")) != SPEC_VERSION:
        raise OnboardingError("unsupported spec_version")
    for key in ("entry_id", "profile", "civic_gps_jurisdiction_id", "package_jurisdiction_id", "package_schema_version", "artifact", "routing"):
        if not spec.get(key):
            raise OnboardingError(f"missing field: {key}")

    entry = build_catalog_entry(spec)
    bundle = build_routing_bundle(spec)
    package = package_catalog.reconstruct_package(entry, repo_root)
    capabilities = package_source.package_capabilities(package)
    if spec["profile"] == "municipal_essentials" and not capabilities["full_essentials"]:
        raise OnboardingError("profile requires full_essentials package capability")
    if spec["profile"] == "municipal_representation" and not capabilities["representation"]:
        raise OnboardingError("profile requires representation package capability")
    if spec["profile"] not in {"municipal_essentials", "municipal_representation"}:
        raise OnboardingError("unsupported consumer profile")
    if package["jurisdiction"]["jurisdiction_id"] != spec["package_jurisdiction_id"]:
        raise OnboardingError("package jurisdiction drift")
    if str(package["schema_version"]) != str(spec["package_schema_version"]):
        raise OnboardingError("package schema drift")
    if str(package["jurisdiction"].get("geoid")) != str(spec["routing"]["geoid"]):
        raise OnboardingError("routing GEOID does not match governed package")
    if bundle["applicable_office_rules"] or bundle["action_registry_files"]:
        raise OnboardingError("routing bundle attempted to acquire civic-fact authority")

    expected = spec.get("expected", {})
    observed = {
        "office_rows": len(package["records"]["offices"]),
        "current_holders": count_current_holders(package),
        "address_controls": len(package["qa"]["address_tests"]),
        "qa_fail_count": package["qa"]["qa_fail_count"],
        "blocking_gap_count": package["qa"]["blocking_gap_count"],
        "parity_ok": package["qa"]["parity_ok"],
    }
    for key, value in expected.items():
        if key in observed and observed[key] != value:
            raise OnboardingError(f"expected {key}={value!r}, observed {observed[key]!r}")

    existing_match = None
    if verify_current:
        existing_entry, existing_bundle = find_existing(repo_root, entry, bundle)
        if existing_entry is None or canonical(existing_entry) != canonical(entry):
            raise OnboardingError("generated catalog entry does not match current governed entry")
        if existing_bundle is None or canonical(existing_bundle) != canonical(bundle):
            raise OnboardingError("generated routing bundle does not match current governed bundle")
        existing_match = True

    out.mkdir(parents=True, exist_ok=True)
    (out / "package_catalog_entry.json").write_text(canonical(entry), encoding="utf-8")
    (out / "civic_gps_routing_bundle.json").write_text(canonical(bundle), encoding="utf-8")
    report = {
        "gate": "EV-IMP-006",
        "status": "PASS",
        "spec_version": SPEC_VERSION,
        "entry_id": entry["entry_id"],
        "profile": entry["profile"],
        "package_schema_version": package["schema_version"],
        "package_jurisdiction_id": package["jurisdiction"]["jurisdiction_id"],
        "civic_gps_jurisdiction_id": spec["civic_gps_jurisdiction_id"],
        "observed": observed,
        "capabilities": capabilities,
        "routing_only": True,
        "civic_gps_civic_fact_rows": 0,
        "canonical_writes": 0,
        "matches_current_governed_artifacts": existing_match,
    }
    (out / "acceptance.json").write_text(canonical(report), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--verify-current", action="store_true")
    args = ap.parse_args()
    print(canonical(run(args.spec, args.repo_root, args.output, args.verify_current)).strip())


if __name__ == "__main__":
    main()
