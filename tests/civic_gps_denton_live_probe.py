#!/usr/bin/env python3
"""Focused Denton County Civic GPS configuration-only live probe.

This does not modify the packaged runtime. It loads the exact reconstructed v0.6.0
engine + v0.4.1 registry, writes a temporary Denton release/registry beside them,
and proves that one county BASE can resolve Commissioner + JP + Constable district
assignments concurrently.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke"
OUTPUT.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("civic_gps_engine_denton", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)

J_DENTON = "jur-us-tx-denton-county"
SNAPSHOT = "https://www.dentoncounty.gov/1144/Elected-Officials"

countywide = [
    ("office-denton-county-judge", "County Judge", "Andy Eads"),
    ("office-denton-county-sheriff", "Sheriff", "Tracy Murphree"),
    ("office-denton-county-clerk", "County Clerk", "Juli Luke"),
    ("office-denton-county-district-clerk", "District Clerk", "David Trantham"),
    ("office-denton-county-tax-assessor-collector", "Tax Assessor-Collector", "Dawn Waye"),
    ("office-denton-county-treasurer", "County Treasurer", "Cindy Yeatts Brown"),
]
commissioners = {
    "1": "Ryan Williams",
    "2": "Kevin Falconer",
    "3": "Bobbie J. Mitchell",
    "4": "Dianne Edmondson",
}
jps = {
    "1": "Alan Wheeler",
    "2": "James R. DePiazza",
    "3": "James Kerbow",
    "4": "Harris Hughey",
    "5": "Mike Oglesby",
    "6": "Blanca Oliver",
}
constables = {
    "1": "Trevor Krueger",
    "2": "Michael A. Truitt",
    "3": "Dan Rochelle",
    "4": "Danny Fletcher",
    "5": "Doug Boydston",
    "6": "Richard Bachus",
}

offices = []
holders = []
for oid, name, person in countywide:
    offices.append({"office_id": oid, "jurisdiction_id": J_DENTON, "name": name, "coverage_class": "RELEASED_CURRENT"})
    holders.append({"office_id": oid, "canonical_name": person})
for key, person in commissioners.items():
    oid = f"office-denton-county-commissioner-precinct-{key}"
    offices.append({"office_id": oid, "jurisdiction_id": J_DENTON, "name": f"County Commissioner Precinct {key}", "coverage_class": "RELEASED_CURRENT"})
    holders.append({"office_id": oid, "canonical_name": person})
for key, person in jps.items():
    oid = f"office-denton-county-justice-of-the-peace-precinct-{key}"
    offices.append({"office_id": oid, "jurisdiction_id": J_DENTON, "name": f"Justice of the Peace Precinct {key}", "coverage_class": "RELEASED_CURRENT"})
    holders.append({"office_id": oid, "canonical_name": person})
for key, person in constables.items():
    oid = f"office-denton-county-constable-precinct-{key}"
    offices.append({"office_id": oid, "jurisdiction_id": J_DENTON, "name": f"Constable Precinct {key}", "coverage_class": "RELEASED_CURRENT"})
    holders.append({"office_id": oid, "canonical_name": person})

assert len(offices) == 22
assert len(holders) == 22

release = {
    "meta": {"release_id": "civic-gps-denton-probe-v0.1", "status": "PROBE_ONLY"},
    "payload": {
        "jurisdictions": [{"jurisdiction_id": J_DENTON, "name": "Denton County", "snapshot_ref": SNAPSHOT}],
        "offices": offices,
        "officeholders": holders,
    },
}
release_name = "civic_gps_denton_probe_release_v0.1.json"
(GPS / release_name).write_text(json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
registry = copy.deepcopy(registry)
registry["bundles"].append({
    "adapter_id": "ADAPTER-TX-DENTON",
    "mode": "BASE",
    "priority": 100,
    "response_id_prefix": "gps-tx-denton",
    "scope_match": {"all": [
        {"geography": "state", "fields": ["GEOID", "STATE"], "equals": "48"},
        {"geography": "county", "fields": ["GEOID"], "equals": "48121"},
    ]},
    "release_files": [release_name],
    "division_rules": [
        {"division_id": "div-us-tx", "name": "Texas", "parent_id": None, "type": "state", "when": {"geography": "state", "fields": ["GEOID", "STATE"], "equals": "48"}},
        {"division_id": "div-us-tx-denton-county", "name": "Denton County", "parent_id": "div-us-tx", "type": "county", "when": {"geography": "county", "fields": ["GEOID"], "equals": "48121"}},
    ],
    "jurisdictions": [
        {"jurisdiction_id": J_DENTON, "activation": {"geography": "county", "fields": ["GEOID"], "equals": "48121"}},
    ],
    "district_adapters": [
        {
            "adapter_id": "DIST-TX-DENTON-COMMISSIONER",
            "activation": {"jurisdiction_active": J_DENTON},
            "jurisdiction_id": J_DENTON,
            "layer": "county_commissioner_precinct",
            "service_url": "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/4",
            "district_field": "COMMISH",
            "district_key_normalization": "NUMERIC",
            "district_name_template": "Denton County Commissioner Precinct {district}",
            "division_id_template": "div-us-tx-denton-county-commissioner-precinct-{district}",
            "division_type": "commissioner_precinct",
            "parent_division_id": "div-us-tx-denton-county",
            "office_id_template": "office-denton-county-commissioner-precinct-{district}",
            "required": True,
        },
        {
            "adapter_id": "DIST-TX-DENTON-JP",
            "activation": {"jurisdiction_active": J_DENTON},
            "jurisdiction_id": J_DENTON,
            "layer": "justice_of_the_peace_precinct",
            "service_url": "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/5",
            "district_field": "JP_C",
            "district_key_normalization": "NUMERIC",
            "district_name_template": "Denton County Justice of the Peace Precinct {district}",
            "division_id_template": "div-us-tx-denton-county-jp-precinct-{district}",
            "division_type": "justice_of_the_peace_precinct",
            "parent_division_id": "div-us-tx-denton-county",
            "office_id_template": "office-denton-county-justice-of-the-peace-precinct-{district}",
            "required": True,
        },
        {
            "adapter_id": "DIST-TX-DENTON-CONSTABLE",
            "activation": {"jurisdiction_active": J_DENTON},
            "jurisdiction_id": J_DENTON,
            "layer": "constable_precinct",
            "service_url": "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/5",
            "district_field": "JP_C",
            "district_key_normalization": "NUMERIC",
            "district_name_template": "Denton County Constable Precinct {district}",
            "division_id_template": "div-us-tx-denton-county-constable-precinct-{district}",
            "division_type": "constable_precinct",
            "parent_division_id": "div-us-tx-denton-county",
            "office_id_template": "office-denton-county-constable-precinct-{district}",
            "required": True,
        },
    ],
    "applicable_office_rules": [{
        "jurisdiction_id": J_DENTON,
        "jurisdiction_wide_office_ids": [x[0] for x in countywide],
        "include_resolved_district_offices": True,
    }],
    "coverage_rules": [
        {"layer": "county_government", "status": "RELEASE_BACKED", "reason": "Denton County probe release is joined.", "when": {"jurisdiction_active": J_DENTON}},
        {"layer": "county_commissioner_precinct", "status": "RELEASE_BACKED", "reason": "Official Denton County Commissioner precinct resolved.", "when": {"district_resolved": "DIST-TX-DENTON-COMMISSIONER"}},
        {"layer": "justice_of_the_peace_precinct", "status": "RELEASE_BACKED", "reason": "Official Denton County JP precinct resolved.", "when": {"district_resolved": "DIST-TX-DENTON-JP"}},
        {"layer": "constable_precinct", "status": "RELEASE_BACKED", "reason": "Official Denton County Constable precinct resolved.", "when": {"district_resolved": "DIST-TX-DENTON-CONSTABLE"}},
    ],
    "known_gaps": [],
})

probe_registry = GPS / "registry-denton-probe.json"
probe_registry.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
resolver = engine_mod.CivicGPSOverlayEngine.from_file(probe_registry, timeout_seconds=30.0)

CASES = [
    {"id": "denton-courthouse", "address": "1 Courthouse Drive, Denton, TX 76208"},
    {"id": "denton-frisco", "address": "5533 FM 423, Frisco, TX 75036"},
]

summaries = []
for case in CASES:
    result = resolver.resolve(case["address"], observed_on=None)
    (OUTPUT / f"{case['id']}.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if "error" in result:
        raise AssertionError(f"[{case['id']}] engine error: {result['error']}")
    payload = result["payload"]
    jurisdictions = {x["jurisdiction_id"] for x in payload["jurisdictions"]}
    if J_DENTON not in jurisdictions:
        raise AssertionError(f"[{case['id']}] Denton jurisdiction missing: {sorted(jurisdictions)}")
    assignments = {x["adapter_id"]: str(x["district_key"]) for x in payload["district_assignments"] if x.get("jurisdiction_id") == J_DENTON}
    required = {"DIST-TX-DENTON-COMMISSIONER", "DIST-TX-DENTON-JP", "DIST-TX-DENTON-CONSTABLE"}
    if set(assignments) != required:
        raise AssertionError(f"[{case['id']}] expected exactly 3 Denton assignments, got {assignments}")
    if assignments["DIST-TX-DENTON-JP"] != assignments["DIST-TX-DENTON-CONSTABLE"]:
        raise AssertionError(f"[{case['id']}] JP/Constable precinct mismatch: {assignments}")
    denton_applicable = [x for x in payload["applicable_offices"] if x.get("jurisdiction_id") == J_DENTON]
    if len(denton_applicable) != 9:
        raise AssertionError(f"[{case['id']}] expected 9 Denton applicable offices, got {len(denton_applicable)}")
    district_scopes = [x for x in denton_applicable if x.get("applicability_scope") == "DISTRICT_MATCH"]
    wide_scopes = [x for x in denton_applicable if x.get("applicability_scope") == "JURISDICTION_WIDE"]
    if len(district_scopes) != 3 or len(wide_scopes) != 6:
        raise AssertionError(f"[{case['id']}] expected 6 wide + 3 district offices; got wide={len(wide_scopes)}, district={len(district_scopes)}")
    summaries.append({
        "case": case["id"],
        "address": case["address"],
        "matched_address": payload["input"].get("matched_address"),
        "assignments": assignments,
        "applicable_offices": len(denton_applicable),
        "district_representatives": {x["adapter_id"]: x.get("representative") for x in payload["district_assignments"] if x.get("jurisdiction_id") == J_DENTON},
        "status": "PASS",
    })

summary = {"status": "PASS", "engine_version": registry.get("engine_version"), "registry_artifact_version": registry.get("registry_artifact_version"), "cases": summaries}
(OUTPUT / "denton-summary.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print(f"PASS: {len(summaries)}/{len(CASES)} Denton configuration-only live controls")
