#!/usr/bin/env python3
"""Packaged Collin County live proof for the reusable Texas county archetype."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke" / "collin"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

engine_mod = load_module("civic_gps_engine_collin", ENGINE_PATH)

J = "jur-us-tx-collin-county"
A_COMM = "DIST-TX-COLLIN-COMMISSIONER"
A_JP = "DIST-TX-COLLIN-JP"
A_CONST = "DIST-TX-COLLIN-CONSTABLE"
GIS_COMM_SERVICE = "https://maps.collincountytx.gov/server/rest/services/Election/VotingPrecincts_Edited_PlanC2333/FeatureServer/3"
GIS_JPC_SERVICE = "https://maps.collincountytx.gov/server/rest/services/Election/VotingPrecincts_Edited_PlanC2333/FeatureServer/4"

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.2":
    raise AssertionError(
        f"Collin release proof requires engine 0.6.1 / registry 0.5.2, got "
        f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
    )
bundle = next((b for b in registry.get("bundles", []) if b.get("adapter_id") == "ADAPTER-TX-COLLIN"), None)
if not bundle:
    raise AssertionError("Packaged registry is missing ADAPTER-TX-COLLIN")
release_file = GPS / "civic_gps_collin_county_v0.1.json"
release = json.loads(release_file.read_text(encoding="utf-8"))
if len(release["payload"]["offices"]) != 18 or len(release["payload"]["officeholders"]) != 18:
    raise AssertionError("Packaged Collin release must contain 18 offices and 18 officeholders")
if bundle.get("action_registry_files"):
    raise AssertionError("Collin action routing must remain unreleased in the county-archetype batch")

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)

CASES = [
    {
        "id": "collin-frisco",
        "address": "6101 Frisco Square Boulevard, Frisco, TX 75034",
        "expected": {A_COMM: "1", A_JP: "4", A_CONST: "4"},
        "representatives": {A_COMM: "Susan Fletcher", A_JP: "Vincent J. Venegoni", A_CONST: "Steve Asher"},
    },
    {
        "id": "collin-plano",
        "address": "1520 K Avenue, Plano, TX 75074",
        "expected": {A_COMM: "2", A_JP: "3", A_CONST: "3"},
        "representatives": {A_COMM: "Cheryl Williams", A_JP: "Mike Missildine", A_CONST: "Sammy Knapp"},
    },
    {
        "id": "collin-mckinney",
        "address": "2300 Bloomdale Road, McKinney, TX 75071",
        "expected": {A_COMM: "3", A_JP: "1", A_CONST: "1"},
        "representatives": {A_COMM: "Darrell Hale", A_JP: "Paul Raleeh", A_CONST: "Matt Carpenter"},
    },
]

summaries = []
for case in CASES:
    result = resolver.resolve(case["address"], observed_on=None)
    (OUTPUT / f"{case['id']}.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if "error" in result:
        raise AssertionError(f"[{case['id']}] engine error: {result['error']}")
    payload = result["payload"]
    if J not in {row["jurisdiction_id"] for row in payload["jurisdictions"]}:
        raise AssertionError(f"[{case['id']}] Collin jurisdiction did not activate")
    assignments = {row["adapter_id"]: str(row["district_key"]) for row in payload["district_assignments"] if row.get("jurisdiction_id") == J}
    reps = {row["adapter_id"]: row.get("representative") for row in payload["district_assignments"] if row.get("jurisdiction_id") == J}
    if assignments != case["expected"]:
        raise AssertionError(f"[{case['id']}] expected {case['expected']}, got {assignments}")
    if reps != case["representatives"]:
        raise AssertionError(f"[{case['id']}] canonical representative join mismatch: {reps}")
    applicable = [row for row in payload["applicable_offices"] if row.get("jurisdiction_id") == J]
    wide = [row for row in applicable if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in applicable if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(applicable), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(f"[{case['id']}] expected 9 = 6 wide + 3 district, got {len(applicable)} = {len(wide)} + {len(district)}")
    if any(row.get("jurisdiction_id") == J for row in payload["action_links"]):
        raise AssertionError(f"[{case['id']}] Collin action routes must remain unreleased in this batch")
    action_cov = [row for row in payload["coverage"] if row.get("layer") == "collin_action_endpoints"]
    if not action_cov or action_cov[0].get("status") != "NOT_YET_RELEASED":
        raise AssertionError(f"[{case['id']}] Collin action coverage must be explicitly NOT_YET_RELEASED: {action_cov}")
    gaps = {row.get("gap_id"): row.get("status") for row in payload["known_gaps"]}
    if gaps.get("GAP-COLLIN-GPS-002") != "NOT_YET_RELEASED":
        raise AssertionError(f"[{case['id']}] missing explicit Collin action gap: {gaps}")
    summaries.append({"case": case["id"], "status": "PASS", "assignments": assignments, "representatives": reps, "applicable_offices": 9})

if len({tuple(sorted(row["assignments"].items())) for row in summaries}) != len(summaries):
    raise AssertionError("Collin controls did not prove distinct district combinations")

outside = resolver.resolve("1500 Marilla Street, Dallas, TX 75201", observed_on=None)
(OUTPUT / "collin-outside-dallas.json").write_text(json.dumps(outside, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
if "error" in outside:
    raise AssertionError(f"[collin-outside-dallas] engine error: {outside['error']}")
out_payload = outside["payload"]
if J in {row["jurisdiction_id"] for row in out_payload["jurisdictions"]}:
    raise AssertionError("Outside-Dallas negative unexpectedly activated Collin")
if any(row.get("jurisdiction_id") == J for row in out_payload["district_assignments"] + out_payload["applicable_offices"] + out_payload["action_links"]):
    raise AssertionError("Outside-Dallas negative leaked Collin assignments/offices/actions")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"})

def get_json(url: str, params: dict) -> dict:
    response = SESSION.get(url, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
    return body

def all_features(service: str, field: str) -> list[dict]:
    return get_json(service.rstrip("/") + "/query", {"where": "1=1", "outFields": field, "returnGeometry": "true", "outSR": "4326", "f": "json"}).get("features") or []

def point_keys(service: str, field: str, lon: float, lat: float) -> list[str]:
    body = get_json(service.rstrip("/") + "/query", {
        "where": "1=1", "geometry": f"{lon:.12f},{lat:.12f}", "geometryType": "esriGeometryPoint", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "outFields": field, "returnGeometry": "false", "f": "json",
    })
    vals = []
    for feature in body.get("features") or []:
        raw = (feature.get("attributes") or {}).get(field)
        if raw not in (None, ""):
            vals.append(str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw).strip())
    return sorted(set(vals))

def rounded_point(point) -> tuple[float, float]:
    return round(float(point[0]), 8), round(float(point[1]), 8)

def segment_index(features: list[dict], field: str) -> dict:
    index: dict = {}
    for feature in features:
        district = str((feature.get("attributes") or {}).get(field)).strip()
        for ring in (feature.get("geometry") or {}).get("rings") or []:
            for a_raw, b_raw in zip(ring, ring[1:]):
                a = (float(a_raw[0]), float(a_raw[1])); b = (float(b_raw[0]), float(b_raw[1]))
                ka, kb = rounded_point(a), rounded_point(b)
                if ka == kb:
                    continue
                index.setdefault(tuple(sorted((ka, kb))), []).append((district, a, b))
    return index

def find_isolated_boundary(primary_service: str, primary_field: str, other_service: str, other_field: str) -> dict:
    candidates = []
    for rows in segment_index(all_features(primary_service, primary_field), primary_field).values():
        districts = sorted({row[0] for row in rows})
        if len(districts) < 2:
            continue
        a, b = rows[0][1], rows[0][2]
        candidates.append((math.hypot(b[0]-a[0], b[1]-a[1]), districts, a, b))
    candidates.sort(reverse=True, key=lambda row: row[0])
    for _, districts, a, b in candidates:
        mid = ((a[0]+b[0])/2.0, (a[1]+b[1])/2.0)
        pm = point_keys(primary_service, primary_field, *mid)
        om = point_keys(other_service, other_field, *mid)
        if len(pm) < 2 or len(om) != 1:
            continue
        dx, dy = b[0]-a[0], b[1]-a[1]; norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        nx, ny = -dy/norm, dx/norm
        for eps in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
            side_a=(mid[0]+nx*eps, mid[1]+ny*eps); side_b=(mid[0]-nx*eps, mid[1]-ny*eps)
            pa=point_keys(primary_service, primary_field, *side_a); pb=point_keys(primary_service, primary_field, *side_b)
            oa=point_keys(other_service, other_field, *side_a); ob=point_keys(other_service, other_field, *side_b)
            if len(pa)==len(pb)==len(oa)==len(ob)==1 and pa[0] != pb[0] and oa[0] == ob[0] == om[0]:
                return {"midpoint": mid, "mid_keys": pm, "other_key": om[0], "side_a": side_a, "side_a_key": pa[0], "side_b": side_b, "side_b_key": pb[0], "epsilon": eps, "shared": districts}
    raise AssertionError(f"No isolated boundary found for {primary_service}")

class FakeResponse:
    def __init__(self, body: dict): self._body = body
    def raise_for_status(self): return None
    def json(self): return self._body

class FixedPointSession:
    def __init__(self, lon: float, lat: float):
        self.lon = lon; self.lat = lat; self.real = requests.Session(); self.real.headers.update({"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"})
    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse({"result": {"addressMatches": [{"matchedAddress": "COLLIN BOUNDARY CONTROL", "coordinates": {"x": self.lon, "y": self.lat}, "geographies": {"States": [{"GEOID": "48", "STATE": "48"}], "Counties": [{"GEOID": "48085", "COUNTY": "085"}]}}]}})
        return self.real.get(url, params=params, timeout=timeout)

def resolve_point(point: tuple[float, float]) -> dict:
    fixed = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, session=FixedPointSession(point[0], point[1]), timeout_seconds=30.0)
    result = fixed.resolve("COLLIN BOUNDARY CONTROL", observed_on=None)
    if "error" in result:
        raise AssertionError(f"Boundary engine error: {result['error']}")
    return result

comm_boundary = find_isolated_boundary(GIS_COMM_SERVICE, "COMMISH", GIS_JPC_SERVICE, "JPC_1")
comm_exact = resolve_point(comm_boundary["midpoint"]); comm_a = resolve_point(comm_boundary["side_a"]); comm_b = resolve_point(comm_boundary["side_b"])
comm_exact_assign = {x["adapter_id"]: str(x["district_key"]) for x in comm_exact["payload"]["district_assignments"] if x.get("jurisdiction_id") == J}
if A_COMM in comm_exact_assign or set(comm_exact_assign) != {A_JP, A_CONST}:
    raise AssertionError(f"Commissioner exact boundary must suppress only Commissioner assignment, got {comm_exact_assign}")
if len([x for x in comm_exact["payload"]["applicable_offices"] if x.get("jurisdiction_id") == J]) != 8:
    raise AssertionError("Commissioner exact boundary must preserve 6 wide + JP + Constable = 8 offices")
for side in (comm_a, comm_b):
    assigns={x["adapter_id"]: str(x["district_key"]) for x in side["payload"]["district_assignments"] if x.get("jurisdiction_id") == J}
    if set(assigns) != {A_COMM, A_JP, A_CONST}:
        raise AssertionError(f"Commissioner boundary side did not fully resolve: {assigns}")

jp_boundary = find_isolated_boundary(GIS_JPC_SERVICE, "JPC_1", GIS_COMM_SERVICE, "COMMISH")
if len(point_keys(GIS_JPC_SERVICE, "JPC_1", *jp_boundary["midpoint"])) < 2:
    raise AssertionError("JP exact boundary did not also intersect multiple official Constable polygons")
jp_exact = resolve_point(jp_boundary["midpoint"]); jp_a = resolve_point(jp_boundary["side_a"]); jp_b = resolve_point(jp_boundary["side_b"])
jp_exact_assign = {x["adapter_id"]: str(x["district_key"]) for x in jp_exact["payload"]["district_assignments"] if x.get("jurisdiction_id") == J}
if set(jp_exact_assign) != {A_COMM}:
    raise AssertionError(f"JP/Constable exact boundary must suppress JP+Constable only, got {jp_exact_assign}")
if len([x for x in jp_exact["payload"]["applicable_offices"] if x.get("jurisdiction_id") == J]) != 7:
    raise AssertionError("JP/Constable exact boundary must preserve 6 wide + Commissioner = 7 offices")
for side in (jp_a, jp_b):
    assigns={x["adapter_id"]: str(x["district_key"]) for x in side["payload"]["district_assignments"] if x.get("jurisdiction_id") == J}
    if set(assigns) != {A_COMM, A_JP, A_CONST} or assigns[A_JP] != assigns[A_CONST]:
        raise AssertionError(f"JP/Constable boundary side did not fully/coherently resolve: {assigns}")

boundary_summary = {
    "commissioner": {"status": "PASS", "exact_keys": comm_boundary["mid_keys"], "exact_assignments": comm_exact_assign, "side_a_key": comm_boundary["side_a_key"], "side_b_key": comm_boundary["side_b_key"], "applicable_offices_exact": 8},
    "jp_constable": {"status": "PASS", "exact_keys": jp_boundary["mid_keys"], "exact_assignments": jp_exact_assign, "side_a_key": jp_boundary["side_a_key"], "side_b_key": jp_boundary["side_b_key"], "applicable_offices_exact": 7},
}
(OUTPUT / "collin-boundary-summary.json").write_text(json.dumps(boundary_summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

summary = {
    "status": "PASS",
    "archetype": "TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1",
    "engine_version": registry["engine_version"],
    "registry_artifact_version": registry["registry_artifact_version"],
    "release_offices": 18,
    "countywide_offices": 6,
    "district_families": 3,
    "interior_controls": summaries,
    "outside_negative": "PASS",
    "boundaries": boundary_summary,
    "engine_transport_change": "DEFAULT_USER_AGENT_V0.6.1",
    "consumer_schema_change_required": False,
}
(OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print("PASS: packaged Collin County reusable archetype release proof")
