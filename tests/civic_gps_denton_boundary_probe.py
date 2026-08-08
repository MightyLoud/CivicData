#!/usr/bin/env python3
"""Packaged Denton County exact-boundary fail-closed proof for Civic GPS v0.6.0."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"

J_DENTON = "jur-us-tx-denton-county"
A_COMM = "DIST-TX-DENTON-COMMISSIONER"
A_JP = "DIST-TX-DENTON-JP"
A_CONST = "DIST-TX-DENTON-CONSTABLE"
COMM_SERVICE = "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/4"
JPC_SERVICE = "https://gis.dentoncounty.gov/arcgis/rest/services/PoliticalBoundaries_GC/MapServer/5"
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"

spec = importlib.util.spec_from_file_location("civic_gps_engine_denton_boundary", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)


def get_json(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
    return body


def all_features(service: str, field: str) -> list[dict]:
    body = get_json(
        service.rstrip("/") + "/query",
        {
            "where": "1=1",
            "outFields": field,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
    )
    features = body.get("features") or []
    if len(features) < 2:
        raise AssertionError(f"Expected multiple polygons from {service}; got {len(features)}")
    return features


def point_keys(service: str, field: str, lon: float, lat: float) -> list[str]:
    body = get_json(
        service.rstrip("/") + "/query",
        {
            "where": "1=1",
            "geometry": f"{lon:.12f},{lat:.12f}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": field,
            "returnGeometry": "false",
            "f": "json",
        },
    )
    values = []
    for feature in body.get("features") or []:
        raw = (feature.get("attributes") or {}).get(field)
        if raw not in (None, ""):
            values.append(str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw).strip())
    return sorted(set(values))


def rounded_point(point) -> tuple[float, float]:
    return (round(float(point[0]), 8), round(float(point[1]), 8))


def segment_index(features: list[dict], field: str) -> dict:
    index = {}
    for feature in features:
        district = str((feature.get("attributes") or {}).get(field)).strip()
        for ring in (feature.get("geometry") or {}).get("rings") or []:
            for a_raw, b_raw in zip(ring, ring[1:]):
                a = (float(a_raw[0]), float(a_raw[1]))
                b = (float(b_raw[0]), float(b_raw[1]))
                ka, kb = rounded_point(a), rounded_point(b)
                if ka == kb:
                    continue
                key = tuple(sorted((ka, kb)))
                index.setdefault(key, []).append((district, a, b))
    return index


def find_isolated_boundary(primary_service: str, primary_field: str, other_service: str, other_field: str) -> dict:
    features = all_features(primary_service, primary_field)
    candidates = []
    for rows in segment_index(features, primary_field).values():
        districts = sorted({row[0] for row in rows})
        if len(districts) < 2:
            continue
        a, b = rows[0][1], rows[0][2]
        candidates.append((math.hypot(b[0] - a[0], b[1] - a[1]), districts, a, b))
    candidates.sort(reverse=True, key=lambda row: row[0])
    if not candidates:
        raise AssertionError(f"No shared polygon segment found in {primary_service}")

    for _, shared_districts, a, b in candidates:
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        primary_mid = point_keys(primary_service, primary_field, *mid)
        other_mid = point_keys(other_service, other_field, *mid)
        if len(primary_mid) < 2 or len(other_mid) != 1:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        nx, ny = -dy / norm, dx / norm
        for eps in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
            side_a = (mid[0] + nx * eps, mid[1] + ny * eps)
            side_b = (mid[0] - nx * eps, mid[1] - ny * eps)
            pa = point_keys(primary_service, primary_field, *side_a)
            pb = point_keys(primary_service, primary_field, *side_b)
            oa = point_keys(other_service, other_field, *side_a)
            ob = point_keys(other_service, other_field, *side_b)
            if len(pa) == len(pb) == len(oa) == len(ob) == 1 and pa[0] != pb[0] and oa[0] == ob[0] == other_mid[0]:
                return {
                    "midpoint": mid,
                    "primary_mid_keys": primary_mid,
                    "other_mid_key": other_mid[0],
                    "side_a": side_a,
                    "side_a_primary_key": pa[0],
                    "side_b": side_b,
                    "side_b_primary_key": pb[0],
                    "epsilon_degrees": eps,
                    "shared_segment_districts": shared_districts,
                }
    raise AssertionError(f"Could not derive isolated two-sided boundary control from {primary_service}")


registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
bundle = next((b for b in registry.get("bundles", []) if b.get("adapter_id") == "ADAPTER-TX-DENTON"), None)
if not bundle:
    raise AssertionError("Packaged Denton bundle missing")
adapters = {a["adapter_id"]: a for a in bundle.get("district_adapters", [])}
for adapter_id in (A_COMM, A_JP, A_CONST):
    adapter = adapters.get(adapter_id)
    if not adapter:
        raise AssertionError(f"Packaged adapter missing: {adapter_id}")
    if adapter.get("failure_scope") != "ADAPTER":
        raise AssertionError(f"{adapter_id} must fail at ADAPTER scope on ambiguous boundaries")
    if adapter.get("boundary_policy") != POLICY:
        raise AssertionError(f"{adapter_id} boundary policy mismatch: {adapter.get('boundary_policy')}")

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
observed = datetime.now(timezone.utc).date().isoformat()
geo = {
    "state": {"GEOID": "48", "STATE": "48", "NAME": "Texas"},
    "county": {"GEOID": "48121", "NAME": "Denton County"},
}


def resolve_xy(label: str, point: tuple[float, float]) -> dict:
    lon, lat = point
    gc = {
        "longitude": lon,
        "latitude": lat,
        "matched_address": None,
        "geographies": {},
        "request_url": f"derived-from-official-denton-arcgis:{label}:{lon:.12f},{lat:.12f}",
    }
    part = resolver._resolve_part(bundle, label, gc, geo, observed)
    if not part.get("active"):
        raise AssertionError(f"[{label}] Denton BASE did not remain active")
    return part["payload"]


def assignments(payload: dict) -> dict[str, str]:
    return {
        row["adapter_id"]: str(row["district_key"])
        for row in payload["district_assignments"]
        if row.get("jurisdiction_id") == J_DENTON
    }


def applicable_count(payload: dict) -> int:
    return len([row for row in payload["applicable_offices"] if row.get("jurisdiction_id") == J_DENTON])


def conflict_layers(payload: dict) -> set[str]:
    return {
        row.get("layer")
        for row in payload.get("coverage", [])
        if row.get("status") == "CONFLICT"
    }


commissioner_boundary = find_isolated_boundary(COMM_SERVICE, "COMMISH", JPC_SERVICE, "JP_C")
commissioner_exact = resolve_xy("denton-commissioner-boundary-exact", tuple(commissioner_boundary["midpoint"]))
commissioner_a = resolve_xy("denton-commissioner-boundary-side-a", tuple(commissioner_boundary["side_a"]))
commissioner_b = resolve_xy("denton-commissioner-boundary-side-b", tuple(commissioner_boundary["side_b"]))

comm_exact_assign = assignments(commissioner_exact)
if A_COMM in comm_exact_assign:
    raise AssertionError(f"Commissioner exact boundary silently assigned precinct: {comm_exact_assign}")
if set(comm_exact_assign) != {A_JP, A_CONST}:
    raise AssertionError(f"Commissioner exact boundary should preserve only JP+Constable assignments; got {comm_exact_assign}")
if comm_exact_assign[A_JP] != commissioner_boundary["other_mid_key"] or comm_exact_assign[A_CONST] != commissioner_boundary["other_mid_key"]:
    raise AssertionError(f"Commissioner exact boundary changed isolated JP/Constable key: {comm_exact_assign}")
if applicable_count(commissioner_exact) != 8:
    raise AssertionError(f"Commissioner exact boundary should produce 8 Denton offices, got {applicable_count(commissioner_exact)}")
if "county_commissioner_precinct" not in conflict_layers(commissioner_exact):
    raise AssertionError("Commissioner exact boundary did not emit CONFLICT coverage")

comm_a_assign, comm_b_assign = assignments(commissioner_a), assignments(commissioner_b)
for side_name, payload, got, expected_comm in (
    ("side_a", commissioner_a, comm_a_assign, commissioner_boundary["side_a_primary_key"]),
    ("side_b", commissioner_b, comm_b_assign, commissioner_boundary["side_b_primary_key"]),
):
    if got.get(A_COMM) != expected_comm or got.get(A_JP) != commissioner_boundary["other_mid_key"] or got.get(A_CONST) != commissioner_boundary["other_mid_key"]:
        raise AssertionError(f"Commissioner {side_name} assignments incorrect: {got}")
    if applicable_count(payload) != 9:
        raise AssertionError(f"Commissioner {side_name} should resolve 9 Denton offices")
if comm_a_assign[A_COMM] == comm_b_assign[A_COMM]:
    raise AssertionError("Commissioner boundary side controls did not resolve distinct precincts")

jpc_boundary = find_isolated_boundary(JPC_SERVICE, "JP_C", COMM_SERVICE, "COMMISH")
jpc_exact = resolve_xy("denton-jpc-boundary-exact", tuple(jpc_boundary["midpoint"]))
jpc_a = resolve_xy("denton-jpc-boundary-side-a", tuple(jpc_boundary["side_a"]))
jpc_b = resolve_xy("denton-jpc-boundary-side-b", tuple(jpc_boundary["side_b"]))

jpc_exact_assign = assignments(jpc_exact)
if A_JP in jpc_exact_assign or A_CONST in jpc_exact_assign:
    raise AssertionError(f"JP/Constable exact boundary silently assigned shared precinct: {jpc_exact_assign}")
if set(jpc_exact_assign) != {A_COMM}:
    raise AssertionError(f"JP/Constable exact boundary should preserve only Commissioner assignment; got {jpc_exact_assign}")
if jpc_exact_assign[A_COMM] != jpc_boundary["other_mid_key"]:
    raise AssertionError(f"JP/Constable exact boundary changed isolated Commissioner key: {jpc_exact_assign}")
if applicable_count(jpc_exact) != 7:
    raise AssertionError(f"JP/Constable exact boundary should produce 7 Denton offices, got {applicable_count(jpc_exact)}")
if not {"justice_of_the_peace_precinct", "constable_precinct"}.issubset(conflict_layers(jpc_exact)):
    raise AssertionError(f"JP/Constable exact boundary did not emit both CONFLICT coverage rows: {conflict_layers(jpc_exact)}")

jpc_a_assign, jpc_b_assign = assignments(jpc_a), assignments(jpc_b)
for side_name, payload, got, expected_jpc in (
    ("side_a", jpc_a, jpc_a_assign, jpc_boundary["side_a_primary_key"]),
    ("side_b", jpc_b, jpc_b_assign, jpc_boundary["side_b_primary_key"]),
):
    if got.get(A_COMM) != jpc_boundary["other_mid_key"] or got.get(A_JP) != expected_jpc or got.get(A_CONST) != expected_jpc:
        raise AssertionError(f"JP/Constable {side_name} assignments incorrect: {got}")
    if applicable_count(payload) != 9:
        raise AssertionError(f"JP/Constable {side_name} should resolve 9 Denton offices")
if jpc_a_assign[A_JP] == jpc_b_assign[A_JP]:
    raise AssertionError("JP/Constable boundary side controls did not resolve distinct precincts")

for name, payload in (
    ("denton-commissioner-boundary-exact", commissioner_exact),
    ("denton-commissioner-boundary-side-a", commissioner_a),
    ("denton-commissioner-boundary-side-b", commissioner_b),
    ("denton-jpc-boundary-exact", jpc_exact),
    ("denton-jpc-boundary-side-a", jpc_a),
    ("denton-jpc-boundary-side-b", jpc_b),
):
    (OUTPUT / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

summary = {
    "status": "PASS",
    "engine_version": registry.get("engine_version"),
    "registry_artifact_version": registry.get("registry_artifact_version"),
    "policy": POLICY,
    "commissioner_boundary": {
        "midpoint": commissioner_boundary["midpoint"],
        "exact_intersections": commissioner_boundary["primary_mid_keys"],
        "preserved_jpc_key": commissioner_boundary["other_mid_key"],
        "exact_assignments": comm_exact_assign,
        "exact_applicable_offices": applicable_count(commissioner_exact),
        "side_a_assignments": comm_a_assign,
        "side_b_assignments": comm_b_assign,
        "epsilon_degrees": commissioner_boundary["epsilon_degrees"],
    },
    "jp_constable_boundary": {
        "midpoint": jpc_boundary["midpoint"],
        "exact_intersections": jpc_boundary["primary_mid_keys"],
        "preserved_commissioner_key": jpc_boundary["other_mid_key"],
        "exact_assignments": jpc_exact_assign,
        "exact_applicable_offices": applicable_count(jpc_exact),
        "side_a_assignments": jpc_a_assign,
        "side_b_assignments": jpc_b_assign,
        "epsilon_degrees": jpc_boundary["epsilon_degrees"],
    },
}
(OUTPUT / "denton-boundary-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print("PASS: packaged Denton Commissioner + JP/Constable boundary fail-closed controls")
