#!/usr/bin/env python3
"""Packaged Williamson County release proof for Civic GPS v0.6.2 / registry v0.5.7."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-williamson-cg09"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
SERVICE = "https://gis.wilco.org/arcgis/rest/services/public/county_administrative_boundaries/MapServer/0"
FIELD = "PCT_NUMBER"
COUNTY_WHERE = "COUNTY='WILLIAMSON'"
J = "jur-us-tx-williamson-county"
A_COMM = "DIST-TX-WILLIAMSON-COMMISSIONER"
A_JP = "DIST-TX-WILLIAMSON-JP"
A_CONST = "DIST-TX-WILLIAMSON-CONSTABLE"
EXPECTED_ADAPTERS = {A_COMM, A_JP, A_CONST}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


engine_mod = load_module("civic_gps_engine_williamson_packaged", ENGINE_PATH)
registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.5.7":
    raise AssertionError(
        f"Williamson packaged proof requires engine 0.6.2 / registry 0.5.7, got "
        f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
    )
bundle = next((b for b in registry.get("bundles", []) if b.get("adapter_id") == "ADAPTER-TX-WILLIAMSON"), None)
if not bundle:
    raise AssertionError("Packaged registry is missing ADAPTER-TX-WILLIAMSON")
if bundle.get("release_files") != ["civic_gps_williamson_county_v0.1.json"]:
    raise AssertionError(f"Unexpected Williamson release files: {bundle.get('release_files')}")
if bundle.get("action_registry_files"):
    raise AssertionError("Williamson action routing must remain unreleased in CG-09")
if any(row.get("failure_scope") != "ADAPTER" for row in bundle.get("district_adapters", [])):
    raise AssertionError("Williamson district adapters must remain ADAPTER-scoped")

release = json.loads((GPS / "civic_gps_williamson_county_v0.1.json").read_text(encoding="utf-8"))
offices = release.get("payload", {}).get("offices", [])
holders = release.get("payload", {}).get("officeholders", [])
if len(offices) != 18 or len(holders) != 18:
    raise AssertionError(f"Packaged Williamson release must contain 18 offices / 18 holders, got {len(offices)} / {len(holders)}")
if len({row.get("office_id") for row in offices}) != 18:
    raise AssertionError("Packaged Williamson office IDs are not unique")

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
CASES = [
    ("williamson-p1", "1801 E Old Settlers Boulevard, Round Rock, TX 78664", "1", {A_COMM: "Terry Cook", A_JP: "KT Musselman", A_CONST: "Mickey Chance"}),
    ("williamson-p2", "350 Discovery Boulevard, Cedar Park, TX 78613", "2", {A_COMM: "Cynthia Long", A_JP: "Angela Williams", A_CONST: "Jeff Anderson"}),
    ("williamson-p3", "405 Martin Luther King Street, Georgetown, TX 78626", "3", {A_COMM: "Valerie Covey", A_JP: "Evelyn McLean", A_CONST: "Kevin Wilkie"}),
    ("williamson-p4", "3001 Joe DiMaggio Boulevard, Round Rock, TX 78665", "4", {A_COMM: "Russ Boles", A_JP: "Rhonda Redden", A_CONST: "Paul Leal"}),
]
interiors = []
for case_id, address, key, expected_reps in CASES:
    result = resolver.resolve(address, observed_on=None)
    (OUTPUT / f"{case_id}.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if "error" in result:
        raise AssertionError(f"[{case_id}] engine error: {result['error']}")
    payload = result["payload"]
    if J not in {row.get("jurisdiction_id") for row in payload.get("jurisdictions") or []}:
        raise AssertionError(f"[{case_id}] Williamson jurisdiction did not activate")
    assignments = {
        row["adapter_id"]: str(row["district_key"])
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == J
    }
    expected = {A_COMM: key, A_JP: key, A_CONST: key}
    if assignments != expected:
        raise AssertionError(f"[{case_id}] expected {expected}, got {assignments}")
    reps = {
        row["adapter_id"]: row.get("representative")
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == J
    }
    if reps != expected_reps:
        raise AssertionError(f"[{case_id}] canonical representative join mismatch: {reps}")
    applicable = [row for row in payload.get("applicable_offices") or [] if row.get("jurisdiction_id") == J]
    wide = [row for row in applicable if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in applicable if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(applicable), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(f"[{case_id}] expected 9 = 6 wide + 3 district, got {len(applicable)} = {len(wide)} + {len(district)}")
    if any(row.get("jurisdiction_id") == J for row in payload.get("action_links") or []):
        raise AssertionError(f"[{case_id}] Williamson actions must remain unreleased")
    interiors.append({"case": case_id, "key": key, "assignments": assignments, "representatives": reps, "applicable_offices": 9, "status": "PASS"})

outside = resolver.resolve("700 Lavaca Street, Austin, TX 78701", observed_on=None)
(OUTPUT / "williamson-outside-austin.json").write_text(json.dumps(outside, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
if "error" in outside:
    raise AssertionError(f"Outside-Austin control failed: {outside['error']}")
out_payload = outside["payload"]
if J in {row.get("jurisdiction_id") for row in out_payload.get("jurisdictions") or []}:
    raise AssertionError("Outside-Austin control unexpectedly activated Williamson")
if any(row.get("jurisdiction_id") == J for row in (out_payload.get("district_assignments") or []) + (out_payload.get("applicable_offices") or []) + (out_payload.get("action_links") or [])):
    raise AssertionError("Outside-Austin control leaked Williamson assignments/offices/actions")
if any(str(row.get("layer") or "").startswith("williamson_") for row in out_payload.get("coverage") or []):
    raise AssertionError("Outside-Austin control leaked Williamson coverage")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})


def get_json(params: dict) -> dict:
    response = SESSION.get(SERVICE.rstrip("/") + "/query", params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise AssertionError(f"ArcGIS error: {body['error']}")
    return body


def normalize_key(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def point_keys(lon: float, lat: float) -> list[str]:
    body = get_json({
        "where": COUNTY_WHERE,
        "geometry": f"{lon:.12f},{lat:.12f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": FIELD,
        "returnGeometry": "false",
        "f": "json",
    })
    values = []
    for feature in body.get("features") or []:
        raw = (feature.get("attributes") or {}).get(FIELD)
        if raw not in (None, ""):
            values.append(normalize_key(raw))
    return sorted(set(values), key=int)


MIDPOINT = (-97.69241162682931, 30.5413362710713)
exact_keys = point_keys(*MIDPOINT)
if exact_keys != ["1", "4"]:
    raise AssertionError(f"Frozen CG-08 Williamson boundary must still intersect official keys 1 and 4, got {exact_keys}")


def find_two_sides(mid: tuple[float, float]) -> tuple[tuple[float, float], str, tuple[float, float], str, float]:
    directions = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
    for eps in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
        singles = []
        for dx, dy in directions:
            norm = math.hypot(dx, dy)
            p = (mid[0] + (dx / norm) * eps, mid[1] + (dy / norm) * eps)
            keys = point_keys(*p)
            if len(keys) == 1 and keys[0] in exact_keys:
                singles.append((p, keys[0]))
        for a in singles:
            for b in singles:
                if a[1] != b[1]:
                    return a[0], a[1], b[0], b[1], eps
    raise AssertionError("Could not derive opposite single-precinct sides around frozen Williamson P1/P4 boundary")


side_a_point, side_a_key, side_b_point, side_b_key, epsilon = find_two_sides(MIDPOINT)


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body
    def raise_for_status(self):
        return None
    def json(self):
        return self._body


class FixedPointSession:
    def __init__(self, lon: float, lat: float):
        self.lon = lon
        self.lat = lat
        self.real = requests.Session()
        self.real.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})
    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse({"result": {"addressMatches": [{"matchedAddress": "WILLIAMSON PACKAGE BOUNDARY", "coordinates": {"x": self.lon, "y": self.lat}, "geographies": {"States": [{"GEOID": "48", "STATE": "48"}], "Counties": [{"GEOID": "48491", "COUNTY": "491"}]}}]}})
        return self.real.get(url, params=params, timeout=timeout)


def resolve_point(point: tuple[float, float]) -> dict:
    fixed = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, session=FixedPointSession(point[0], point[1]), timeout_seconds=30.0)
    result = fixed.resolve("WILLIAMSON PACKAGE BOUNDARY", observed_on=None)
    if "error" in result:
        raise AssertionError(f"Boundary engine error: {result['error']}")
    return result


exact = resolve_point(MIDPOINT)
exact_payload = exact["payload"]
exact_assignments = {row["adapter_id"]: str(row["district_key"]) for row in exact_payload.get("district_assignments") or [] if row.get("jurisdiction_id") == J}
if exact_assignments:
    raise AssertionError(f"Exact shared boundary must suppress all Williamson district assignments, got {exact_assignments}")
exact_offices = [row for row in exact_payload.get("applicable_offices") or [] if row.get("jurisdiction_id") == J]
if len(exact_offices) != 6 or any(row.get("applicability_scope") == "DISTRICT_MATCH" for row in exact_offices):
    raise AssertionError(f"Exact shared boundary must preserve only 6 countywide offices, got {len(exact_offices)}")

holders_by_key = {
    "1": {A_COMM: "Terry Cook", A_JP: "KT Musselman", A_CONST: "Mickey Chance"},
    "4": {A_COMM: "Russ Boles", A_JP: "Rhonda Redden", A_CONST: "Paul Leal"},
}
side_summaries = []
for label, point, expected_key in (("side_a", side_a_point, side_a_key), ("side_b", side_b_point, side_b_key)):
    result = resolve_point(point)
    assignments = {row["adapter_id"]: str(row["district_key"]) for row in result["payload"].get("district_assignments") or [] if row.get("jurisdiction_id") == J}
    if set(assignments) != EXPECTED_ADAPTERS or set(assignments.values()) != {expected_key}:
        raise AssertionError(f"{label} must resolve all three Williamson adapters to {expected_key}, got {assignments}")
    reps = {row["adapter_id"]: row.get("representative") for row in result["payload"].get("district_assignments") or [] if row.get("jurisdiction_id") == J}
    if reps != holders_by_key[expected_key]:
        raise AssertionError(f"{label} canonical representative join mismatch: {reps}")
    applicable = [row for row in result["payload"].get("applicable_offices") or [] if row.get("jurisdiction_id") == J]
    if len(applicable) != 9:
        raise AssertionError(f"{label} must restore 9 Williamson offices, got {len(applicable)}")
    side_summaries.append({"side": label, "key": expected_key, "assignments": assignments, "representatives": reps, "applicable_offices": 9, "status": "PASS"})

summary = {
    "status": "PASS",
    "county": "Williamson County, TX",
    "geoid": "48491",
    "engine_version": "0.6.2",
    "registry_artifact_version": "0.5.7",
    "release_offices": 18,
    "release_holders": 18,
    "interior_controls": interiors,
    "outside_negative": "PASS",
    "boundary": {
        "midpoint": list(MIDPOINT),
        "official_intersections": exact_keys,
        "exact_assignments": 0,
        "exact_applicable_offices": 6,
        "sides": side_summaries,
        "epsilon_degrees": epsilon,
        "policy": "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK",
    },
    "actions": "NOT_YET_RELEASED",
}
(OUTPUT / "packaged-williamson-summary.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("WILLIAMSON PACKAGED CG-09 PASS")
