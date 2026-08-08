#!/usr/bin/env python3
"""Deterministic Civic GPS County Onboarding Pipeline v0.1.

Consumes a *frozen* county onboarding JSON spec. It does not scrape live sources
or mutate the packaged runtime. The tool classifies the v0.1 archetype fit,
records source-precedence decisions, and emits deterministic build/proof plans.
For supported specs it delegates release/bundle preview generation to the
existing ``civic_gps_tx_county_archetype`` build helper.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "civic-gps-county-onboarding/0.1.0"
ARCHETYPE = "TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1"
BOUNDARY_POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
TRACKER_SUPPORTED = "SUPPORTED_V0_1"
TRACKER_UNSUPPORTED = "UNSUPPORTED_PATTERN"
STOP_CLASSES = [
    "MULTI_OFFICE_PER_DISTRICT",
    "MISSING_OFFICIAL_GIS",
    "NON_NUMERIC_DISTRICT_KEY",
    "SOURCE_IDENTITY_CONFLICT",
    "COUNTYWIDE_SCOPE_UNBOUNDED",
    "TRANSIENT_UPSTREAM_FAILURE",
    "ARCHITECTURE_CHANGE_REQUIRED",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require(mapping: dict[str, Any], key: str, path: str, errors: list[str]) -> Any:
    value = mapping.get(key)
    if value in (None, "", []):
        errors.append(f"{path}.{key} is required")
    return value


def _numeric_key(value: Any) -> bool:
    try:
        text = str(value).strip()
        if not re.fullmatch(r"[0-9]+", text):
            return False
        int(text)
        return True
    except (TypeError, ValueError):
        return False


def validate_frozen_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if spec.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if spec.get("archetype") != ARCHETYPE:
        errors.append(f"archetype must be {ARCHETYPE}")

    county = spec.get("county") or {}
    for key in (
        "name", "state", "geoid", "jurisdiction_id", "division_id", "adapter_id",
        "response_id_prefix", "release_filename", "observed_on",
    ):
        _require(county, key, "county", errors)
    geoid = str(county.get("geoid") or "")
    if geoid and not re.fullmatch(r"48[0-9]{3}", geoid):
        errors.append("county.geoid must be a 5-digit Texas county GEOID beginning with 48")

    scope = spec.get("scope") or {}
    if "bounded" not in scope:
        errors.append("scope.bounded is required")
    if not isinstance(scope.get("countywide_offices"), list):
        errors.append("scope.countywide_offices must be a list")
    else:
        wide_ids: list[str] = []
        for idx, row in enumerate(scope.get("countywide_offices") or []):
            for key in ("office_id", "title", "holder", "official_url"):
                _require(row, key, f"scope.countywide_offices[{idx}]", errors)
            if row.get("office_id"):
                wide_ids.append(str(row["office_id"]))
        if len(wide_ids) != len(set(wide_ids)):
            errors.append("scope.countywide_offices contains duplicate office_id values")
    if not isinstance(scope.get("expected_total_offices"), int):
        errors.append("scope.expected_total_offices must be an integer")

    sources = spec.get("sources") or {}
    _require(sources, "snapshot_ref", "sources", errors)
    _require(sources, "source_repository", "sources", errors)
    if not isinstance(sources.get("manifest"), dict):
        errors.append("sources.manifest must be an object")
    if not isinstance(sources.get("identity_conflicts", []), list):
        errors.append("sources.identity_conflicts must be a list")
    if not isinstance(sources.get("source_health", []), list):
        errors.append("sources.source_health must be a list")

    architecture = spec.get("architecture") or {}
    for key in ("requires_custom_resolver_logic", "requires_consumer_schema_change"):
        if key not in architecture:
            errors.append(f"architecture.{key} is required")

    families = spec.get("district_families")
    if not isinstance(families, list) or not families:
        errors.append("district_families must be a non-empty list")
    else:
        for idx, family in enumerate(families):
            path = f"district_families[{idx}]"
            for key in (
                "family", "adapter_id", "layer", "district_keys", "offices_per_key", "holders",
                "district_name_template", "division_id_template", "division_type",
                "office_id_template", "office_title_template", "official_url", "coverage_reason",
            ):
                _require(family, key, path, errors)
            geometry = family.get("geometry") or {}
            for key in (
                "official", "service_url", "district_field", "district_field_type", "numeric",
                "endpoint_authority_class", "endpoint_provenance_url", "endpoint_publisher",
            ):
                if key not in geometry or geometry.get(key) in (None, ""):
                    errors.append(f"{path}.geometry.{key} is required")
            if not isinstance(family.get("district_keys"), list):
                errors.append(f"{path}.district_keys must be a list")
            if not isinstance(family.get("offices_per_key"), dict):
                errors.append(f"{path}.offices_per_key must be an object")
            if not isinstance(family.get("holders"), dict):
                errors.append(f"{path}.holders must be an object")
            if isinstance(family.get("district_keys"), list) and isinstance(family.get("offices_per_key"), dict) and isinstance(family.get("holders"), dict):
                district_keys = {str(key) for key in family["district_keys"]}
                office_keys = {str(key) for key in family["offices_per_key"]}
                holder_keys = {str(key) for key in family["holders"]}
                if district_keys != office_keys or district_keys != holder_keys:
                    errors.append(f"{path} district_keys, offices_per_key, and holders must use identical key sets")
                for key, count in family["offices_per_key"].items():
                    if not isinstance(count, int) or count < 1:
                        errors.append(f"{path}.offices_per_key[{key}] must be a positive integer")

    if isinstance(families, list):
        adapter_ids = [str(row.get("adapter_id")) for row in families if row.get("adapter_id")]
        if len(adapter_ids) != len(set(adapter_ids)):
            errors.append("district_families contains duplicate adapter_id values")

    controls = spec.get("controls") or {}
    if not isinstance(controls.get("interiors"), list) or not controls.get("interiors"):
        errors.append("controls.interiors must contain at least one candidate address")
    if not isinstance(controls.get("outside_negative"), dict) or not controls.get("outside_negative", {}).get("address"):
        errors.append("controls.outside_negative.address is required")
    boundary = controls.get("boundary") or {}
    if boundary.get("required") is not True:
        errors.append("controls.boundary.required must be true")
    if boundary.get("policy") != BOUNDARY_POLICY:
        errors.append(f"controls.boundary.policy must be {BOUNDARY_POLICY}")

    return sorted(set(errors))


def _collect_stop_classes(spec: dict[str, Any]) -> tuple[list[str], dict[str, list[str]]]:
    reasons: dict[str, list[str]] = {name: [] for name in STOP_CLASSES}
    scope = spec.get("scope") or {}
    sources = spec.get("sources") or {}
    architecture = spec.get("architecture") or {}
    families = spec.get("district_families") or []

    # v0.1 contract: exactly one applicable office for each resolved key/family.
    for family in families:
        family_name = family.get("family") or family.get("adapter_id") or "unknown"
        for key, count in sorted((family.get("offices_per_key") or {}).items(), key=lambda item: str(item[0])):
            if int(count) != 1:
                reasons["MULTI_OFFICE_PER_DISTRICT"].append(
                    f"{family_name} key {key} maps to {count} offices; v0.1 requires exactly one"
                )
        for key, holder in sorted((family.get("holders") or {}).items(), key=lambda item: str(item[0])):
            if isinstance(holder, list) and len(holder) != 1:
                reasons["MULTI_OFFICE_PER_DISTRICT"].append(
                    f"{family_name} key {key} has {len(holder)} canonical holders/offices"
                )

    for family in families:
        family_name = family.get("family") or family.get("adapter_id") or "unknown"
        geometry = family.get("geometry") or {}
        if geometry.get("official") is not True or not geometry.get("service_url") or not geometry.get("district_field"):
            reasons["MISSING_OFFICIAL_GIS"].append(
                f"{family_name} lacks a frozen official GIS endpoint + district field"
            )

    for family in families:
        family_name = family.get("family") or family.get("adapter_id") or "unknown"
        geometry = family.get("geometry") or {}
        keys = family.get("district_keys") or []
        holder_keys = list((family.get("holders") or {}).keys())
        office_keys = list((family.get("offices_per_key") or {}).keys())
        all_keys = keys + holder_keys + office_keys
        bad = sorted({str(key) for key in all_keys if not _numeric_key(key)})
        if geometry.get("numeric") is not True or bad:
            detail = f"{family_name} must use numeric district keys"
            if bad:
                detail += f"; non-numeric keys={bad}"
            reasons["NON_NUMERIC_DISTRICT_KEY"].append(detail)

    for conflict in sources.get("identity_conflicts") or []:
        if conflict.get("resolution_status") != "RESOLVED":
            subject = conflict.get("subject") or "identity conflict"
            reasons["SOURCE_IDENTITY_CONFLICT"].append(f"{subject} is unresolved")

    if scope.get("bounded") is not True:
        reasons["COUNTYWIDE_SCOPE_UNBOUNDED"].append("scope.bounded must be true")
    if scope.get("countywide_complete") is False and scope.get("unmodeled_status") != "BOUNDED_V0_1_SCOPE":
        reasons["COUNTYWIDE_SCOPE_UNBOUNDED"].append(
            "incomplete countywide coverage must explicitly declare BOUNDED_V0_1_SCOPE"
        )

    for source in sources.get("source_health") or []:
        if source.get("status") == "TRANSIENT_UPSTREAM_FAILURE":
            reasons["TRANSIENT_UPSTREAM_FAILURE"].append(
                f"{source.get('source_id') or 'source'} has a transient upstream failure"
            )

    if architecture.get("requires_custom_resolver_logic") is True:
        reasons["ARCHITECTURE_CHANGE_REQUIRED"].append("custom resolver logic is required")
    if architecture.get("requires_consumer_schema_change") is True:
        reasons["ARCHITECTURE_CHANGE_REQUIRED"].append("consumer schema change is required")
    for family in families:
        resolver_kind = family.get("resolver_kind", "ARCGIS_POINT_INTERSECT")
        if resolver_kind != "ARCGIS_POINT_INTERSECT":
            reasons["ARCHITECTURE_CHANGE_REQUIRED"].append(
                f"{family.get('family') or family.get('adapter_id')} resolver_kind={resolver_kind}"
            )

    stop_classes = [name for name in STOP_CLASSES if reasons[name]]
    return stop_classes, {name: reasons[name] for name in stop_classes}


def fit_screen(spec: dict[str, Any]) -> dict[str, Any]:
    errors = validate_frozen_spec(spec)
    if errors:
        raise ValueError("Invalid frozen onboarding spec:\n- " + "\n- ".join(errors))

    stops, stop_reasons = _collect_stop_classes(spec)
    primary = stops[0] if stops else "NONE"
    supported = not stops
    return {
        "archetype": ARCHETYPE,
        "county": spec["county"]["name"],
        "county_geoid": str(spec["county"]["geoid"]),
        "decision": "GO" if supported else "STOP",
        "result": TRACKER_SUPPORTED if supported else primary,
        "tracker_fit_result": TRACKER_SUPPORTED if supported else TRACKER_UNSUPPORTED,
        "stop_class": primary,
        "stop_classes": stops,
        "stop_reasons": stop_reasons,
        "architecture_change": "NO" if not _collect_stop_classes(spec)[1].get("ARCHITECTURE_CHANGE_REQUIRED") else "YES",
        "boundary_policy": BOUNDARY_POLICY,
        "spec_sha256": sha256_value(spec),
        "schema_version": SCHEMA_VERSION,
    }


def build_builder_spec(spec: dict[str, Any]) -> dict[str, Any]:
    county = spec["county"]
    sources = spec["sources"]
    scope = spec["scope"]
    families = []
    for family in spec["district_families"]:
        geometry = family["geometry"]
        holders: dict[str, str] = {}
        for key, value in family["holders"].items():
            if isinstance(value, list):
                if len(value) != 1:
                    raise ValueError("Cannot emit builder spec for multi-office-per-district family")
                holders[str(key)] = str(value[0])
            else:
                holders[str(key)] = str(value)
        families.append({
            "adapter_id": family["adapter_id"],
            "layer": family["layer"],
            "service_url": geometry["service_url"],
            "district_field": geometry["district_field"],
            "district_name_template": family["district_name_template"],
            "division_id_template": family["division_id_template"],
            "division_type": family["division_type"],
            "office_id_template": family["office_id_template"],
            "office_title_template": family["office_title_template"],
            "official_url": family["official_url"],
            "endpoint_authority_class": geometry["endpoint_authority_class"],
            "endpoint_provenance_url": geometry["endpoint_provenance_url"],
            "endpoint_publisher": geometry["endpoint_publisher"],
            "coverage_reason": family["coverage_reason"],
            "holders": holders,
            "selection_type": family.get("selection_type", "election"),
        })

    return {
        "county_name": county["name"],
        "county_geoid": str(county["geoid"]),
        "jurisdiction_id": county["jurisdiction_id"],
        "division_id": county["division_id"],
        "adapter_id": county["adapter_id"],
        "response_id_prefix": county["response_id_prefix"],
        "release_filename": county["release_filename"],
        "snapshot_ref": sources["snapshot_ref"],
        "source_repository": sources["source_repository"],
        "source_manifest": copy.deepcopy(sources["manifest"]),
        "observed_on": county["observed_on"],
        "release_status": spec.get("release_status", "PROBE_CURRENT"),
        "source_status": spec.get("source_status", "FROZEN_SPEC_VALIDATED"),
        "release_note": spec.get("release_note") or (
            f"{county['name']} frozen county onboarding spec generated through {ARCHETYPE}."
        ),
        "countywide_offices": copy.deepcopy(scope["countywide_offices"]),
        "district_families": families,
        "known_gaps": copy.deepcopy(spec.get("known_gaps") or []),
    }


def _load_builder(builder_path: Path):
    module_spec = importlib.util.spec_from_file_location("civic_gps_tx_county_archetype", builder_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


def _expected_office_count(spec: dict[str, Any]) -> int:
    count = len(spec["scope"]["countywide_offices"])
    for family in spec["district_families"]:
        count += sum(int(value) for value in family["offices_per_key"].values())
    return count


def build_proof_plan(spec: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    supported = report["decision"] == "GO"
    controls = spec["controls"]
    gates = [
        {"gate": "CG-01", "name": "Scope & intake", "status": "PASS"},
        {"gate": "CG-02", "name": "Authority sources", "status": "PASS"},
        {
            "gate": "CG-03",
            "name": "Archetype fit screen",
            "status": "PASS" if supported else "STOP",
            "result": report["result"],
        },
    ]
    for gate, name in (
        ("CG-04", "Canonical roster"),
        ("CG-05", "GIS / adapter proof"),
        ("CG-06", "Interior controls"),
        ("CG-07", "Outside negative"),
        ("CG-08", "Exact-boundary controls"),
        ("CG-09", "Package + full regression"),
        ("CG-10", "Protected promotion"),
    ):
        gates.append({"gate": gate, "name": name, "status": "READY" if supported else "BLOCKED"})

    proof_matrix = {
        "canonical_roster": {
            "expected_total_offices": spec["scope"]["expected_total_offices"],
            "expected_generated_offices": _expected_office_count(spec),
            "identity_source_rule": "CANONICAL_RELEASE_ONLY",
            "source_precedence_records": copy.deepcopy(spec["sources"].get("identity_conflicts") or []),
        },
        "gis_adapters": [
            {
                "family": family["family"],
                "adapter_id": family["adapter_id"],
                "service_url": family["geometry"]["service_url"],
                "district_field": family["geometry"]["district_field"],
                "district_keys": [str(key) for key in family["district_keys"]],
                "failure_scope": "ADAPTER",
                "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
                "boundary_policy": BOUNDARY_POLICY,
            }
            for family in spec["district_families"]
        ],
        "interiors": copy.deepcopy(controls["interiors"]),
        "outside_negative": copy.deepcopy(controls["outside_negative"]),
        "boundary": copy.deepcopy(controls["boundary"]),
    }
    return {
        "county": spec["county"]["name"],
        "decision": report["decision"],
        "stop_class": report["stop_class"],
        "gates": gates,
        "proof_matrix": proof_matrix,
        "package_plan": {
            "status": "READY" if supported else "BLOCKED",
            "deterministic_runtime_required": True,
            "engine_change_allowed": False,
            "consumer_schema_change_allowed": False,
            "full_existing_release_matrix_required": True,
        },
        "promotion_plan": {
            "status": "READY" if supported else "BLOCKED",
            "clean_branch_from_current_main": True,
            "single_intentional_release_commit": True,
            "pull_request_required": True,
            "required_status_context": "Civic GPS release gate",
            "post_merge_main_run_required": True,
            "temporary_onboarding_or_write_capable_packager_workflows_forbidden": True,
        },
        "schema_version": SCHEMA_VERSION,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def run_onboarding(spec: dict[str, Any], output_dir: Path, builder_path: Path | None = None) -> dict[str, Any]:
    report = fit_screen(spec)
    proof_plan = build_proof_plan(spec, report)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "fit-report.json", report)
    _write_json(output_dir / "source-precedence.json", {
        "county": spec["county"]["name"],
        "records": copy.deepcopy(spec["sources"].get("identity_conflicts") or []),
        "status": "RESOLVED" if all(
            row.get("resolution_status") == "RESOLVED"
            for row in spec["sources"].get("identity_conflicts") or []
        ) else "UNRESOLVED",
        "schema_version": SCHEMA_VERSION,
    })
    _write_json(output_dir / "proof-plan.json", proof_plan)

    if report["decision"] == "GO":
        builder_spec = build_builder_spec(spec)
        _write_json(output_dir / "builder-spec.json", builder_spec)
        resolved_builder = builder_path or Path(__file__).with_name("civic_gps_tx_county_archetype.py")
        builder = _load_builder(resolved_builder)
        release, bundle = builder.build_texas_county_precinct_artifacts(builder_spec)

        action_plan = spec.get("actions") or {}
        if action_plan.get("status") == "NOT_YET_RELEASED" and action_plan.get("layer"):
            bundle["coverage_rules"].insert(-1, {
                "layer": action_plan["layer"],
                "reason": action_plan.get("reason") or "Civic-action routing is explicitly not yet released.",
                "status": "NOT_YET_RELEASED",
                "when": {"jurisdiction_active": spec["county"]["jurisdiction_id"]},
            })

        release_offices = release.get("payload", {}).get("offices", [])
        release_holders = release.get("payload", {}).get("officeholders", [])
        office_count = len(release_offices)
        holder_count = len(release_holders)
        expected = spec["scope"]["expected_total_offices"]
        if (office_count, holder_count) != (expected, expected):
            raise ValueError(
                f"generated release count mismatch: expected {expected}/{expected}, got {office_count}/{holder_count}"
            )
        office_ids = [row.get("office_id") for row in release_offices]
        holder_office_ids = [row.get("office_id") for row in release_holders]
        if len(set(office_ids)) != expected or None in office_ids:
            raise ValueError("generated release office IDs are not unique and complete")
        if set(holder_office_ids) != set(office_ids) or len(holder_office_ids) != expected:
            raise ValueError("generated officeholder joins do not match the canonical office ID set")
        if len(bundle.get("district_adapters", [])) != len(spec["district_families"]):
            raise ValueError("generated district adapter count does not match the frozen spec")
        if any(row.get("failure_scope") != "ADAPTER" for row in bundle.get("district_adapters", [])):
            raise ValueError("generated district adapter does not preserve failure_scope=ADAPTER")
        if any(row.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY" for row in bundle.get("district_adapters", [])):
            raise ValueError("generated district adapter does not preserve CANONICAL_RELEASE_ONLY identity")
        if any(row.get("boundary_policy") != BOUNDARY_POLICY for row in bundle.get("district_adapters", [])):
            raise ValueError("generated district adapter does not preserve fail-closed boundary policy")

        _write_json(output_dir / "canonical-release-preview.json", release)
        _write_json(output_dir / "base-bundle-plan.json", bundle)

    manifest_files: dict[str, str] = {}
    for path in sorted(output_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        manifest_files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "county": spec["county"]["name"],
        "decision": report["decision"],
        "result": report["result"],
        "spec_sha256": report["spec_sha256"],
        "files": manifest_files,
        "schema_version": SCHEMA_VERSION,
        "tool": "civic_gps_county_onboarding.py",
        "tool_version": "0.1.0",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return {"fit_report": report, "proof_plan": proof_plan, "manifest": manifest}


def load_spec(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("onboarding spec root must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="Frozen county onboarding JSON spec")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for deterministic outputs")
    parser.add_argument(
        "--expect",
        choices=[TRACKER_SUPPORTED, *STOP_CLASSES],
        help="Fail if the deterministic result does not equal this expected result",
    )
    args = parser.parse_args(argv)
    try:
        spec = load_spec(args.spec)
        result = run_onboarding(spec, args.output_dir)
        report = result["fit_report"]
        summary = {
            "county": report["county"],
            "decision": report["decision"],
            "result": report["result"],
            "stop_class": report["stop_class"],
            "spec_sha256": report["spec_sha256"],
            "output_dir": str(args.output_dir),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        if args.expect and report["result"] != args.expect:
            print(f"Expected result {args.expect}, got {report['result']}", file=sys.stderr)
            return 1
        return 0
    except Exception as exc:  # CLI boundary: make invalid frozen specs obvious in CI.
        print(f"COUNTY_ONBOARDING_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
