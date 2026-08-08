#!/usr/bin/env python3
"""Williamson County CG-06 real-address interior controls.

This onboarding probe overlays a generated Williamson bundle onto a temporary
copy of the currently released Civic GPS runtime. It does not package or release
Williamson County. The proof must resolve real official county office addresses
through Census geocoding + official county precinct geometry + canonical roster.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke" / "williamson"
OUTPUT.mkdir(parents=True, exist_ok=True)
BUILDER_PATH = ROOT / "tools" / "civic_gps_tx_county_archetype.py"
ENGINE_PATH = GPS / "engine.py"

SERVICE = "https://gis.wilco.org/arcgis/rest/services/public/county_administrative_boundaries/MapServer/0"
FIELD = "PCT_NUMBER"
J = "jur-us-tx-williamson-county"
A_COMM = "DIST-TX-WILLIAMSON-COMMISSIONER"
A_JP = "DIST-TX-WILLIAMSON-JP"
A_CONST = "DIST-TX-WILLIAMSON-CONSTABLE"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


builder = load_module("civic_gps_tx_county_archetype_williamson_cg06", BUILDER_PATH)
engine_mod = load_module("civic_gps_engine_williamson_cg06", ENGINE_PATH)

countywide = [
    {"office_id": "office-us-tx-williamson-county-judge", "title": "County Judge", "holder": "Steven Snell", "selection_type": "appointment", "official_url": "https://www.wilcotx.gov/334/County-Judge"},
    {"office_id": "office-us-tx-williamson-county-sheriff", "title": "Sheriff", "holder": "Matthew Lindemann", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
    {"office_id": "office-us-tx-williamson-county-clerk", "title": "County Clerk", "holder": "Nancy E. Rister", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
    {"office_id": "office-us-tx-williamson-county-district-clerk", "title": "District Clerk", "holder": "Lisa David", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
    {"office_id": "office-us-tx-williamson-county-tax-assessor-collector", "title": "Tax Assessor-Collector", "holder": "Catherine Totty", "selection_type": "appointment", "official_url": "https://www.wilcotx.gov/tax"},
    {"office_id": "office-us-tx-williamson-county-treasurer", "title": "County Treasurer", "holder": "D. Scott Heselmeyer", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
]

families = [
    {
        "adapter_id": A_COMM,
        "layer": "williamson_county_commissioner_precinct",
        "service_url": SERVICE,
        "district_field": FIELD,
        "district_name_template": "Williamson County Commissioner Precinct {district}",
        "division_id_template": "div-us-tx-williamson-county-commissioner-{district}",
        "division_type": "county_commissioner_precinct",
        "office_id_template": "office-us-tx-williamson-county-commissioner-{district}",
        "office_title_template": "Commissioner Precinct {district}",
        "official_url": "https://www.wilcotx.gov/188/Elected-Officials",
        "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
        "endpoint_provenance_url": SERVICE,
        "endpoint_publisher": "Williamson County GIS",
        "coverage_reason": "Williamson County Commissioner precinct is resolved from official county precinct geometry.",
        "holders": {"1": "Terry Cook", "2": "Cynthia Long", "3": "Valerie Covey", "4": "Russ Boles"},
    },
    {
        "adapter_id": A_JP,
        "layer": "williamson_county_jp_precinct",
        "service_url": SERVICE,
        "district_field": FIELD,
        "district_name_template": "Williamson County Justice Precinct {district}",
        "division_id_template": "div-us-tx-williamson-county-jp-{district}",
        "division_type": "justice_precinct",
        "office_id_template": "office-us-tx-williamson-county-jp-{district}",
        "office_title_template": "Justice of the Peace Precinct {district}",
        "official_url": "https://www.wilcotx.gov/188/Elected-Officials",
        "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
        "endpoint_provenance_url": SERVICE,
        "endpoint_publisher": "Williamson County GIS",
        "coverage_reason": "Williamson County Justice precinct is resolved from official county precinct geometry.",
        "holders": {"1": "KT Musselman", "2": "Angela Williams", "3": "Evelyn McLean", "4": "Rhonda Redden"},
    },
    {
        "adapter_id": A_CONST,
        "layer": "williamson_county_constable_precinct",
        "service_url": SERVICE,
        "district_field": FIELD,
        "district_name_template": "Williamson County Constable Precinct {district}",
        "division_id_template": "div-us-tx-williamson-county-constable-{district}",
        "division_type": "constable_precinct",
        "office_id_template": "office-us-tx-williamson-county-constable-{district}",
        "office_title_template": "Constable Precinct {district}",
        "official_url": "https://www.wilcotx.gov/188/Elected-Officials",
        "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
        "endpoint_provenance_url": SERVICE,
        "endpoint_publisher": "Williamson County GIS",
        "coverage_reason": "Williamson County Constable precinct is resolved from official county precinct geometry.",
        "holders": {"1": "Mickey Chance", "2": "Jeff Anderson", "3": "Kevin Wilkie", "4": "Paul Leal"},
    },
]

spec = {
    "county_name": "Williamson County",
    "county_geoid": "48491",
    "jurisdiction_id": J,
    "division_id": "div-us-tx-williamson-county",
    "adapter_id": "ADAPTER-TX-WILLIAMSON",
    "response_id_prefix": "civic-gps-williamson",
    "release_filename": "civic_gps_williamson_county_v0.1.json",
    "snapshot_ref": "williamson-cg06-live-proof-2026-08-08",
    "observed_on": "2026-08-08",
    "countywide_offices": countywide,
    "district_families": families,
    "release_note": "CG-06 onboarding proof only; not yet packaged or released.",
    "release_status": "PROBE_CURRENT",
    "source_status": "LIVE_ARCHETYPE_PROOF",
    "source_manifest": {
        "identity": "https://www.wilcotx.gov/188/Elected-Officials + current office-specific pages",
        "geometry": SERVICE,
        "controls": "official Williamson County precinct office physical addresses",
    },
    "known_gaps": [
        {"gap_id": "GAP-WILLIAMSON-GPS-001", "layer": "williamson_action_endpoints", "status": "NOT_YET_RELEASED", "reason": "CG-06 proves office applicability only; civic actions are a later release."}
    ],
}
release, bundle = builder.build_texas_county_precinct_artifacts(spec)

if len(release["payload"]["offices"]) != 18 or len(release["payload"]["officeholders"]) != 18:
    raise AssertionError("Williamson CG-06 generated release must contain 18 offices / 18 holders")

CASES = [
    {
        "id": "williamson-p1-jester-annex",
        "address": "1801 E Old Settlers Boulevard, Round Rock, TX 78664",
        "official_source": "https://www.wilcotx.gov/349/Precinct-One",
        "expected_key": "1",
        "representatives": {A_COMM: "Terry Cook", A_JP: "KT Musselman", A_CONST: "Mickey Chance"},
    },
    {
        "id": "williamson-p2-cedar-park-annex",
        "address": "350 Discovery Boulevard, Cedar Park, TX 78613",
        "official_source": "https://www.wilcotx.gov/comm2",
        "expected_key": "2",
        "representatives": {A_COMM: "Cynthia Long", A_JP: "Angela Williams", A_CONST: "Jeff Anderson"},
    },
    {
        "id": "williamson-p3-georgetown-annex",
        "address": "100 Wilco Way, Georgetown, TX 78626",
        "official_source": "https://www.wilcotx.gov/comm3",
        "expected_key": "3",
        "representatives": {A_COMM: "Valerie Covey", A_JP: "Evelyn McLean", A_CONST: "Kevin Wilkie"},
    },
    {
        "id": "williamson-p4-joe-dimaggio-annex",
        "address": "3001 Joe DiMaggio Boulevard, Round Rock, TX 78665",
        "official_source": "https://www.wilcotx.gov/comm4",
        "expected_key": "4",
        "representatives": {A_COMM: "Russ Boles", A_JP: "Rhonda Redden", A_CONST: "Paul Leal"},
    },
]

with tempfile.TemporaryDirectory(prefix="civic-gps-williamson-cg06-") as temp_root:
    temp_gps = Path(temp_root) / "civic_gps"
    shutil.copytree(GPS, temp_gps)
    registry_path = temp_gps / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.3":
        raise AssertionError(
            f"CG-06 expects released engine 0.6.1 / registry 0.5.3, got "
            f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
        )
    if any(row.get("adapter_id") == bundle["adapter_id"] for row in registry.get("bundles", [])):
        raise AssertionError("Williamson unexpectedly already exists in released registry")
    registry["bundles"] = copy.deepcopy(registry.get("bundles") or []) + [bundle]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (temp_gps / spec["release_filename"]).write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    resolver = engine_mod.CivicGPSOverlayEngine.from_file(registry_path, timeout_seconds=30.0)
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
        if J not in {row["jurisdiction_id"] for row in payload["jurisdictions"]}:
            raise AssertionError(f"[{case['id']}] Williamson jurisdiction did not activate")
        assignments = {
            row["adapter_id"]: str(row["district_key"])
            for row in payload["district_assignments"]
            if row.get("jurisdiction_id") == J
        }
        expected = {A_COMM: case["expected_key"], A_JP: case["expected_key"], A_CONST: case["expected_key"]}
        if assignments != expected:
            raise AssertionError(f"[{case['id']}] expected assignments {expected}, got {assignments}")
        reps = {
            row["adapter_id"]: row.get("representative")
            for row in payload["district_assignments"]
            if row.get("jurisdiction_id") == J
        }
        if reps != case["representatives"]:
            raise AssertionError(f"[{case['id']}] canonical representative join mismatch: {reps}")
        applicable = [row for row in payload["applicable_offices"] if row.get("jurisdiction_id") == J]
        wide = [row for row in applicable if row.get("applicability_scope") == "JURISDICTION_WIDE"]
        district = [row for row in applicable if row.get("applicability_scope") == "DISTRICT_MATCH"]
        if (len(applicable), len(wide), len(district)) != (9, 6, 3):
            raise AssertionError(
                f"[{case['id']}] expected 9 = 6 countywide + 3 district offices, "
                f"got {len(applicable)} = {len(wide)} + {len(district)}"
            )
        if any(row.get("jurisdiction_id") == J for row in payload.get("action_links") or []):
            raise AssertionError(f"[{case['id']}] Williamson actions must remain unreleased in CG-06")
        summaries.append(
            {
                "case": case["id"],
                "address": case["address"],
                "official_source": case["official_source"],
                "expected_key": case["expected_key"],
                "assignments": assignments,
                "representatives": reps,
                "applicable_offices": len(applicable),
                "status": "PASS",
            }
        )

if {row["expected_key"] for row in summaries} != {"1", "2", "3", "4"}:
    raise AssertionError("CG-06 controls did not cover every Williamson precinct key 1-4")
if len({tuple(sorted(row["assignments"].items())) for row in summaries}) != 4:
    raise AssertionError("CG-06 controls did not produce four distinct district assignment sets")

summary = {
    "gate": "CG-06",
    "status": "PASS",
    "county": "Williamson County, TX",
    "geoid": "48491",
    "engine_version": "0.6.1",
    "registry_artifact_version": "0.5.3",
    "packaged": False,
    "engine_change_required": False,
    "controls": summaries,
    "coverage": {"precinct_keys": ["1", "2", "3", "4"], "controls": 4, "applicable_offices_each": 9},
    "next_gate": "CG-07 outside negative",
}
(OUTPUT / "cg06-interior-controls.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("WILLIAMSON CG-06 PASS")
