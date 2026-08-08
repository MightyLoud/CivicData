#!/usr/bin/env python3
"""Denton County configuration-only live probe for Civic GPS v0.6.0."""
from __future__ import annotations

import copy
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
RESOLUTION = "CENSUS_GEOCODE_PLUS_OFFICIAL_ARCGIS_POINT_INTERSECT"

COUNTYWIDE = {
    "office-denton-county-judge": ("County Judge", "Andy Eads"),
    "office-denton-county-sheriff": ("Sheriff", "Tracy Murphree"),
    "office-denton-county-clerk": ("County Clerk", "Juli Luke"),
    "office-denton-county-district-clerk": ("District Clerk", "David Trantham"),
    "office-denton-county-tax-assessor-collector": ("Tax Assessor-Collector", "Dawn Waye"),
    "office-denton-county-treasurer": ("County Treasurer", "Cindy Yeatts Brown"),
}
COMMISSIONERS = {"1": "Ryan Williams", "2": "Kevin Falconer", "3": "Bobbie J. Mitchell", "4": "Dianne Edmondson"}
JPS = {"1": "Alan Wheeler", "2": "James R. DePiazza", "3": "James Kerbow", "4": "Harris Hughey", "5": "Mike Oglesby", "6": "Blanca Oliver"}
CONSTABLES = {"1": "Trevor Krueger", "2": "Michael A. Truitt", "3": "Dan Rochelle", "4": "Danny Fletcher", "5": "Doug Boydston", "6": "Richard Bachus"}


def office(office_id: str, name: str, holder: str):
    return (
        {"office_id": office_id, "jurisdiction_id": J_DENTON, "name": name, "coverage_class": "RELEASED_CURRENT"},
        {"office_id": office_id, "canonical_name": holder},
    )


offices, holders = [], []
for oid, (name, holder) in COUNTYWIDE.items():
    o, h = office(oid, name, holder); offices.append(o); holders.append(h)
for key, holder in COMMISSIONERS.items():
    o, h = office(f"office-denton-county-commissioner-precinct-{key}", f"County Commissioner Precinct {key}", holder); offices.append(o); holders.append(h)
for key, holder in JPS.items():
    o, h = office(f"office-denton-county-justice-of-the-peace-precinct-{key}", f"Justice of the Peace Precinct {key}", holder); offices.append(o); holders.append(h)
for key, holder in CONSTABLES.items():
    o, h = office(f"office-denton-county-constable-precinct-{key}", f"Constable Precinct {key}", holder); offices.append(o); holders.append(h)
assert len(offices) == len(holders) == 22

release_name = "civic_gps_denton_probe_release_v0.1.json"
release = {
    "meta": {"release_id": "civic-gps-denton-probe-v0.1", "status": "PROBE_ONLY"},
    "payload": {
        "jurisdictions": [{"jurisdiction_id": J_DENTON, "name": "Denton County", "snapshot_ref": "https://www.dentoncounty.gov/1144/Elected-Officials"}],
        "offices": offices,
        "officeholders": holders,
    },
}
(GPS / release_name).write_text(json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def district_adapter(adapter_id: str, layer: str, service: str, field: str, name_template: str, div_template: str, office_template: str):
    return {
        "adapter_id": adapter_id,
        "activation": {"jurisdiction_active": J_DENTON},
        "jurisdiction_id": J_DENTON,
        "layer": layer,
        "service_url": service,
        "district_field": field,
        "district_key_normalization": "NUMERIC",
        "district_name_template": name_template,
        "division_id_template": div_template,
        "parent_division_id": "div-us-tx-denton-county",
        "office_id_template": office_template,
        "required": True,
        "resolution_method": RESOLUTION,
    }


registry = copy.deepcopy(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
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
    "jurisdictions": [{"jurisdiction_id": J_DENTON, "activation": {"geography": "county", "fields": ["GEOID"], "equals": "48121"}}],
    "district_adapters": [
        district_adapter("DIST-TX-DENTON-COMMISSIONER", "county_commissioner_precinct", "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/4", "COMMISH", "Denton County Commissioner Precinct {district}", "div-us-tx-denton-county-commissioner-precinct-{district}", "office-denton-county-commissioner-precinct-{district}"),
        district_adapter("DIST-TX-DENTON-JP", "justice_of_the_peace_precinct", "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/5", "JP_C", "Denton County Justice of the Peace Precinct {district}", "div-us-tx-denton-county-jp-precinct-{district}", "office-denton-county-justice-of-the-peace-precinct-{district}"),
        district_adapter("DIST-TX-DENTON-CONSTABLE", "constable_precinct", "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/5", "JP_C", "Denton County Constable Precinct {district}", "div-us-tx-denton-county-constable-precinct-{district}", "office-denton-county-constable-precinct-{district}"),
    ],
    "applicable_office_rules": [{"jurisdiction_id": J_DENTON, "jurisdiction_wide_office_ids": list(COUNTYWIDE), "include_resolved_district_offices": True}],
    "coverage_rules": [],
    "known_gaps": [],
})
probe_registry = GPS / "registry-denton-probe.json"
probe_registry.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
resolver = engine_mod.CivicGPSOverlayEngine.from_file(probe_registry, timeout_seconds=30.0)

CASES = [
    {"id": "denton-frisco-p2", "address": "5533 FM 423, Frisco, TX 75036", "expected": {"DIST-TX-DENTON-COMMISSIONER": "2", "DIST-TX-DENTON-JP": "2", "DIST-TX-DENTON-CONSTABLE": "2"}},
    {"id": "denton-lewisville-p3", "address": "400 N Valley Parkway, Lewisville, TX 75067", "expected": {"DIST-TX-DENTON-COMMISSIONER": "3", "DIST-TX-DENTON-JP": "3", "DIST-TX-DENTON-CONSTABLE": "3"}},
]

summaries = []
for case in CASES:
    result = resolver.resolve(case["address"], observed_on=None)
    (OUTPUT / f"{case['id']}.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if "error" in result:
        raise AssertionError(f"[{case['id']}] engine error: {result['error']}")
    payload = result["payload"]
    if J_DENTON not in {x["jurisdiction_id"] for x in payload["jurisdictions"]}:
        raise AssertionError(f"[{case['id']}] Denton jurisdiction missing")
    assignments = {x["adapter_id"]: str(x["district_key"]) for x in payload["district_assignments"] if x.get("jurisdiction_id") == J_DENTON}
    if assignments != case["expected"]:
        raise AssertionError(f"[{case['id']}] expected assignments {case['expected']}, got {assignments}")
    applicable = [x for x in payload["applicable_offices"] if x.get("jurisdiction_id") == J_DENTON]
    wide = [x for x in applicable if x.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [x for x in applicable if x.get("applicability_scope") == "DISTRICT_MATCH"]
    if len(applicable) != 9 or len(wide) != 6 or len(district) != 3:
        raise AssertionError(f"[{case['id']}] expected 9 offices = 6 wide + 3 district; got total={len(applicable)}, wide={len(wide)}, district={len(district)}")
    summaries.append({
        "case": case["id"], "address": case["address"], "status": "PASS",
        "assignments": assignments, "applicable_offices": len(applicable),
        "district_representatives": {x["adapter_id"]: x.get("representative") for x in payload["district_assignments"] if x.get("jurisdiction_id") == J_DENTON},
    })

if summaries[0]["assignments"] == summaries[1]["assignments"]:
    raise AssertionError("Denton controls did not prove distinct district combinations")
summary = {"status": "PASS", "engine_version": registry.get("engine_version"), "registry_artifact_version": registry.get("registry_artifact_version"), "cases": summaries}
(OUTPUT / "denton-summary.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print("PASS: 2/2 Denton configuration-only live controls")
