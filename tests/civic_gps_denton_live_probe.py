#!/usr/bin/env python3
"""Packaged Denton County live controls for Civic GPS v0.6.1 / registry v0.5.3."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"

spec = importlib.util.spec_from_file_location("civic_gps_engine_denton", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)

J_DENTON = "jur-us-tx-denton-county"
A_COMM = "DIST-TX-DENTON-COMMISSIONER"
A_JP = "DIST-TX-DENTON-JP"
A_CONST = "DIST-TX-DENTON-CONSTABLE"

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("engine_version") != "0.6.1":
    raise AssertionError(f"Expected engine 0.6.1 registry contract, got {registry.get('engine_version')}")
if registry.get("registry_artifact_version") != "0.5.3":
    raise AssertionError(f"Expected packaged registry 0.5.3, got {registry.get('registry_artifact_version')}")
denton_bundle = next((b for b in registry.get("bundles", []) if b.get("adapter_id") == "ADAPTER-TX-DENTON"), None)
if not denton_bundle:
    raise AssertionError("Packaged Denton bundle is missing")
if denton_bundle.get("release_files") != ["civic_gps_denton_county_v0.1.json"]:
    raise AssertionError(f"Unexpected Denton release files: {denton_bundle.get('release_files')}")
if denton_bundle.get("action_registry_files") != ["civic_gps_action_registry_denton_v0.1.json"]:
    raise AssertionError(f"Unexpected Denton action registry files: {denton_bundle.get('action_registry_files')}")

release = json.loads((GPS / "civic_gps_denton_county_v0.1.json").read_text(encoding="utf-8"))
if len(release.get("payload", {}).get("offices", [])) != 22:
    raise AssertionError("Packaged Denton release must contain exactly 22 offices")
if len(release.get("payload", {}).get("officeholders", [])) != 22:
    raise AssertionError("Packaged Denton release must contain exactly 22 current officeholders")

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)

CASES = [
    {
        "id": "denton-frisco-p2",
        "address": "5533 FM 423, Frisco, TX 75036",
        "expected": {A_COMM: "2", A_JP: "2", A_CONST: "2"},
        "representatives": {
            A_COMM: "Kevin Falconer",
            A_JP: "James R. DePiazza",
            A_CONST: "Michael A. Truitt",
        },
    },
    {
        "id": "denton-flower-mound-p4",
        "address": "6200 Canyon Falls Drive, Flower Mound, TX 76226",
        "expected": {A_COMM: "4", A_JP: "4", A_CONST: "4"},
        "representatives": {
            A_COMM: "Dianne Edmondson",
            A_JP: "Harris Hughey",
            A_CONST: "Danny Fletcher",
        },
    },
]

summaries = []
for case in CASES:
    result = resolver.resolve(case["address"], observed_on=None)
    (OUTPUT / f"{case['id']}.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if "error" in result:
        raise AssertionError(f"[{case['id']}] engine error: {result['error']}")
    payload = result["payload"]
    if J_DENTON not in {x["jurisdiction_id"] for x in payload["jurisdictions"]}:
        raise AssertionError(f"[{case['id']}] packaged Denton jurisdiction missing")

    assignments = {
        x["adapter_id"]: str(x["district_key"])
        for x in payload["district_assignments"]
        if x.get("jurisdiction_id") == J_DENTON
    }
    if assignments != case["expected"]:
        raise AssertionError(f"[{case['id']}] expected {case['expected']}, got {assignments}")

    representatives = {
        x["adapter_id"]: x.get("representative")
        for x in payload["district_assignments"]
        if x.get("jurisdiction_id") == J_DENTON
    }
    if representatives != case["representatives"]:
        raise AssertionError(f"[{case['id']}] representative join mismatch: {representatives}")

    applicable = [x for x in payload["applicable_offices"] if x.get("jurisdiction_id") == J_DENTON]
    wide = [x for x in applicable if x.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [x for x in applicable if x.get("applicability_scope") == "DISTRICT_MATCH"]
    if len(applicable) != 9 or len(wide) != 6 or len(district) != 3:
        raise AssertionError(
            f"[{case['id']}] expected 9 Denton offices = 6 wide + 3 district; "
            f"got total={len(applicable)}, wide={len(wide)}, district={len(district)}"
        )

    denton_actions = [x for x in payload["action_links"] if x.get("jurisdiction_id") == J_DENTON]
    action_ids = {x["action_id"] for x in denton_actions}
    expected_district_actions = {
        f"ACT-DENTON-CONTACT-COMMISSIONER-P{case['expected'][A_COMM]}",
        f"ACT-DENTON-CONTACT-JP-P{case['expected'][A_JP]}",
        f"ACT-DENTON-CONTACT-CONSTABLE-P{case['expected'][A_CONST]}",
    }
    if len(denton_actions) != 14 or not expected_district_actions.issubset(action_ids):
        raise AssertionError(f"[{case['id']}] expected 14 Denton actions with {sorted(expected_district_actions)}, got {len(denton_actions)} / {sorted(action_ids)}")
    wrong_precinct_actions = {aid for aid in action_ids if aid.startswith("ACT-DENTON-CONTACT-COMMISSIONER-P") or aid.startswith("ACT-DENTON-CONTACT-JP-P") or aid.startswith("ACT-DENTON-CONTACT-CONSTABLE-P")} - expected_district_actions
    if wrong_precinct_actions:
        raise AssertionError(f"[{case['id']}] leaked non-applicable precinct actions: {sorted(wrong_precinct_actions)}")

    action_coverage = [
        row for row in payload["coverage"]
        if row.get("layer") == "denton_action_endpoints" and row.get("status") == "RELEASE_BACKED"
    ]
    if not action_coverage:
        raise AssertionError(f"[{case['id']}] missing RELEASE_BACKED Denton action coverage")

    summaries.append({
        "case": case["id"],
        "address": case["address"],
        "status": "PASS",
        "assignments": assignments,
        "applicable_offices": len(applicable),
        "denton_actions": len(denton_actions),
        "district_representatives": representatives,
    })

if summaries[0]["assignments"] == summaries[1]["assignments"]:
    raise AssertionError("Denton controls did not prove distinct district combinations")

summary = {
    "status": "PASS",
    "engine_version": registry.get("engine_version"),
    "registry_artifact_version": registry.get("registry_artifact_version"),
    "release_offices": 22,
    "cases": summaries,
}
(OUTPUT / "denton-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print("PASS: 2/2 packaged Denton live controls")
