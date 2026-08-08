#!/usr/bin/env python3
"""Offline acceptance tests for County Onboarding Pipeline v0.1."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "civic_gps_county_onboarding.py"
FIXTURES = ROOT / "tests" / "fixtures" / "civic_gps_county_onboarding"
SCHEMA = ROOT / "schemas" / "civic_gps_county_onboarding_v0.1.schema.json"


def load_tool():
    spec = importlib.util.spec_from_file_location("civic_gps_county_onboarding", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def directory_snapshot(path: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(path.glob("*.json"))}


def main() -> int:
    tool = load_tool()
    schema = load_json(SCHEMA)
    assert_equal(schema.get("$id"), tool.SCHEMA_VERSION, "schema/tool version mismatch")

    williamson = load_json(FIXTURES / "williamson_supported_v0.1.json")
    hays = load_json(FIXTURES / "hays_multi_office_stop_v0.1.json")

    # Positive fixture: deterministic GO + existing builder artifacts.
    with tempfile.TemporaryDirectory(prefix="county-onboarding-a-") as first_tmp, tempfile.TemporaryDirectory(prefix="county-onboarding-b-") as second_tmp:
        first = Path(first_tmp)
        second = Path(second_tmp)
        first_result = tool.run_onboarding(copy.deepcopy(williamson), first)
        second_result = tool.run_onboarding(copy.deepcopy(williamson), second)
        report = first_result["fit_report"]
        assert_equal(report["result"], "SUPPORTED_V0_1", "Williamson fit result")
        assert_equal(report["stop_class"], "NONE", "Williamson stop class")
        assert_equal(report["architecture_change"], "NO", "Williamson architecture change")
        assert_equal(directory_snapshot(first), directory_snapshot(second), "deterministic output bytes")

        release = load_json(first / "canonical-release-preview.json")
        bundle = load_json(first / "base-bundle-plan.json")
        assert_equal(len(release["payload"]["offices"]), 18, "Williamson release office count")
        assert_equal(len(release["payload"]["officeholders"]), 18, "Williamson release holder count")
        assert_equal(len({row["office_id"] for row in release["payload"]["offices"]}), 18, "Williamson unique office IDs")
        assert_equal(len(bundle["district_adapters"]), 3, "Williamson district adapter count")
        assert_true(all(row["failure_scope"] == "ADAPTER" for row in bundle["district_adapters"]), "ADAPTER failure scope")
        assert_true(all(row["officeholder_identity_source"] == "CANONICAL_RELEASE_ONLY" for row in bundle["district_adapters"]), "canonical identity only")
        assert_true(all(row["boundary_policy"] == tool.BOUNDARY_POLICY for row in bundle["district_adapters"]), "fail-closed boundary policy")
        proof = first_result["proof_plan"]
        assert_equal(len(proof["proof_matrix"]["interiors"]), 4, "Williamson interior control count")
        assert_equal(proof["promotion_plan"]["required_status_context"], "Civic GPS release gate", "protected promotion status")
        assert_true((first / "builder-spec.json").exists(), "supported fixture emits builder spec")

    # Negative fixture: named STOP is a successful classification, not an error.
    with tempfile.TemporaryDirectory(prefix="county-onboarding-hays-") as hays_tmp:
        out = Path(hays_tmp)
        result = tool.run_onboarding(copy.deepcopy(hays), out)
        report = result["fit_report"]
        assert_equal(report["decision"], "STOP", "Hays decision")
        assert_equal(report["result"], "MULTI_OFFICE_PER_DISTRICT", "Hays primary stop")
        assert_equal(report["tracker_fit_result"], "UNSUPPORTED_PATTERN", "Hays tracker fit result")
        assert_true("MULTI_OFFICE_PER_DISTRICT" in report["stop_classes"], "Hays stop list")
        assert_true(not (out / "builder-spec.json").exists(), "stopped fixture must not emit builder spec")
        assert_true(not (out / "canonical-release-preview.json").exists(), "stopped fixture must not emit release preview")
        gate_map = {row["gate"]: row["status"] for row in result["proof_plan"]["gates"]}
        assert_equal(gate_map["CG-03"], "STOP", "Hays CG-03")
        assert_equal(gate_map["CG-04"], "BLOCKED", "Hays downstream block")

    # Every named STOP class in issue #9 has an executable detector.
    mutations = {}
    case = copy.deepcopy(williamson)
    case["district_families"][1]["offices_per_key"]["1"] = 2
    case["district_families"][1]["holders"]["1"] = ["Judge A", "Judge B"]
    mutations["MULTI_OFFICE_PER_DISTRICT"] = case

    case = copy.deepcopy(williamson)
    case["district_families"][0]["geometry"]["official"] = False
    mutations["MISSING_OFFICIAL_GIS"] = case

    case = copy.deepcopy(williamson)
    family = case["district_families"][0]
    family["district_keys"][0] = "A"
    family["offices_per_key"]["A"] = family["offices_per_key"].pop("1")
    family["holders"]["A"] = family["holders"].pop("1")
    mutations["NON_NUMERIC_DISTRICT_KEY"] = case

    case = copy.deepcopy(williamson)
    case["sources"]["identity_conflicts"].append({"subject": "Synthetic unresolved identity", "resolution_status": "UNRESOLVED"})
    mutations["SOURCE_IDENTITY_CONFLICT"] = case

    case = copy.deepcopy(williamson)
    case["scope"]["bounded"] = False
    mutations["COUNTYWIDE_SCOPE_UNBOUNDED"] = case

    case = copy.deepcopy(williamson)
    case["sources"]["source_health"] = [{"source_id": "synthetic", "status": "TRANSIENT_UPSTREAM_FAILURE"}]
    mutations["TRANSIENT_UPSTREAM_FAILURE"] = case

    case = copy.deepcopy(williamson)
    case["architecture"]["requires_custom_resolver_logic"] = True
    mutations["ARCHITECTURE_CHANGE_REQUIRED"] = case

    for expected, mutated in mutations.items():
        report = tool.fit_screen(mutated)
        assert_equal(report["result"], expected, f"primary detector for {expected}")

    print(json.dumps({
        "status": "PASS",
        "supported_fixture": "Williamson County → SUPPORTED_V0_1 / NONE",
        "stop_fixture": "Hays County → MULTI_OFFICE_PER_DISTRICT",
        "stop_classes_tested": tool.STOP_CLASSES,
        "determinism": "PASS",
    }, sort_keys=True))
    print("COUNTY ONBOARDING PIPELINE v0.1 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
