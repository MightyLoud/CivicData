#!/usr/bin/env python3
"""Williamson County CG-08 exact-boundary fail-closed controls.

This onboarding probe reuses the exact CG-06 generated Williamson bundle and
canonical roster. It derives a shared precinct boundary from live official
Williamson County polygon geometry and proves that an exact boundary never
silently selects a district. Because Commissioner, JP, and Constable all use the
same precinct geometry in Williamson, all three district families must suppress
together at the exact boundary and resolve together on either side.
"""
from __future__ import annotations

import copy
import json
import math
import requests
import runpy
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CG06 = ROOT / "tests" / "civic_gps_williamson_cg06_probe.py"

# Reuse the exact positive-fixture bundle/roster. Running CG-06 here guards
# against CG-08 drifting away from the already-proven onboarding spec.
ctx = runpy.run_path(str(CG06))
GPS: Path = ctx["GPS"]
OUTPUT: Path = ctx["OUTPUT"]
engine_mod = ctx["engine_mod"]
bundle = ctx["bundle"]
release = ctx["release"]
spec = ctx["spec"]
J = ctx["J"]
A_COMM = ctx["A_COMM"]
A_JP = ctx["A_JP"]
A_CONST = ctx["A_CONST"]
SERVICE = ctx["SERVICE"]
FIELD = ctx["FIELD"]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"})
COUNTY_WHERE = "COUNTY='WILLIAMSON'"


def get_json(url: str, params: dict) -> dict:
    response = SESSION.get(url, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
    return body


def normalize_key(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def all_features() -> list[dict]:
    body = get_json(
        SERVICE.rstrip("/") + "/query",
        {
            "where": COUNTY_WHERE,
            "outFields": f"{FIELD},COUNTY",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
    )
    return body.get("features") or []


def point_keys(lon: float, lat: float) -> list[str]:
    body = get_json(
        SERVICE.rstrip("/") + "/query",
        {
            "where": COUNTY_WHERE,
            "geometry": f"{lon:.12f},{lat:.12f}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": FIELD,
            "returnGeometry": "false",
            "f": "json",
        },
    )
    values = []
    for feature in body.get("features") or []:
        raw = (feature.get("attributes") or {}).get(FIELD)
        if raw not in (None, ""):
            values.append(normalize_key(raw))
    return sorted(set(values), key=int)


def rounded_point(point: list[float] | tuple[float, float]) -> tuple[float, float]:
    return round(float(point[0]), 8), round(float(point[1]), 8)


def segment_index(features: list[dict]) -> dict:
    index: dict = {}
    for feature in features:
        attrs = feature.get("attributes") or {}
        if str(attrs.get("COUNTY") or "").strip().upper() != "WILLIAMSON":
            continue
        district = normalize_key(attrs.get(FIELD))
        for ring in (feature.get("geometry") or {}).get("rings") or []:
            for a_raw, b_raw in zip(ring, ring[1:]):
                a = (float(a_raw[0]), float(a_raw[1]))
                b = (float(b_raw[0]), float(b_raw[1]))
                ka, kb = rounded_point(a), rounded_point(b)
                if ka == kb:
                    continue
                index.setdefault(tuple(sorted((ka, kb))), []).append((district, a, b))
    return index


def find_shared_boundary() -> dict:
    candidates = []
    for rows in segment_index(all_features()).values():
        districts = sorted({row[0] for row in rows}, key=int)
        if len(districts) < 2:
            continue
        a, b = rows[0][1], rows[0][2]
        candidates.append((math.hypot(b[0] - a[0], b[1] - a[1]), districts, a, b))
    candidates.sort(reverse=True, key=lambda row: row[0])

    for _, districts, a, b in candidates:
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        exact_keys = point_keys(*mid)
        if len(exact_keys) < 2:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        nx, ny = -dy / norm, dx / norm
        for eps in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
            side_a = (mid[0] + nx * eps, mid[1] + ny * eps)
            side_b = (mid[0] - nx * eps, mid[1] - ny * eps)
            keys_a = point_keys(*side_a)
            keys_b = point_keys(*side_b)
            if (
                len(keys_a) == 1
                and len(keys_b) == 1
                and keys_a[0] != keys_b[0]
                and keys_a[0] in exact_keys
                and keys_b[0] in exact_keys
            ):
                return {
                    "midpoint": mid,
                    "exact_keys": exact_keys,
                    "side_a": side_a,
                    "side_a_key": keys_a[0],
                    "side_b": side_b,
                    "side_b_key": keys_b[0],
                    "epsilon_degrees": eps,
                    "shared_segment_keys": districts,
                }
    raise AssertionError("Could not derive a two-sided exact Williamson precinct boundary from official geometry")


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
        self.real.headers.update({"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"})

    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse(
                {
                    "result": {
                        "addressMatches": [
                            {
                                "matchedAddress": "WILLIAMSON BOUNDARY CONTROL",
                                "coordinates": {"x": self.lon, "y": self.lat},
                                "geographies": {
                                    "States": [{"GEOID": "48", "STATE": "48"}],
                                    "Counties": [{"GEOID": "48491", "COUNTY": "491"}],
                                },
                            }
                        ]
                    }
                }
            )
        return self.real.get(url, params=params, timeout=timeout)


with tempfile.TemporaryDirectory(prefix="civic-gps-williamson-cg08-") as temp_root:
    temp_gps = Path(temp_root) / "civic_gps"
    shutil.copytree(GPS, temp_gps)
    registry_path = temp_gps / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.3":
        raise AssertionError(
            f"CG-08 expects released engine 0.6.1 / registry 0.5.3, got "
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

    boundary = find_shared_boundary()

    def resolve_point(point: tuple[float, float]) -> dict:
        resolver = engine_mod.CivicGPSOverlayEngine.from_file(
            registry_path,
            session=FixedPointSession(point[0], point[1]),
            timeout_seconds=30.0,
        )
        result = resolver.resolve("WILLIAMSON BOUNDARY CONTROL", observed_on=None)
        if "error" in result:
            raise AssertionError(f"CG-08 boundary engine error: {result['error']}")
        return result

    exact = resolve_point(boundary["midpoint"])
    side_a = resolve_point(boundary["side_a"])
    side_b = resolve_point(boundary["side_b"])

for name, result in (("exact", exact), ("side_a", side_a), ("side_b", side_b)):
    (OUTPUT / f"cg08-{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

expected_adapters = {A_COMM, A_JP, A_CONST}

exact_payload = exact["payload"]
if J not in {row.get("jurisdiction_id") for row in exact_payload.get("jurisdictions") or []}:
    raise AssertionError("CG-08 exact boundary must still activate Williamson County jurisdiction")
exact_assignments = {
    row["adapter_id"]: str(row["district_key"])
    for row in exact_payload.get("district_assignments") or []
    if row.get("jurisdiction_id") == J
}
if exact_assignments:
    raise AssertionError(f"CG-08 exact shared boundary must suppress all Williamson district assignments, got {exact_assignments}")
exact_offices = [row for row in exact_payload.get("applicable_offices") or [] if row.get("jurisdiction_id") == J]
exact_wide = [row for row in exact_offices if row.get("applicability_scope") == "JURISDICTION_WIDE"]
exact_district = [row for row in exact_offices if row.get("applicability_scope") == "DISTRICT_MATCH"]
if (len(exact_offices), len(exact_wide), len(exact_district)) != (6, 6, 0):
    raise AssertionError(
        f"CG-08 exact boundary must preserve only 6 countywide offices, got "
        f"{len(exact_offices)} = {len(exact_wide)} wide + {len(exact_district)} district"
    )
if any(row.get("jurisdiction_id") == J for row in exact_payload.get("action_links") or []):
    raise AssertionError("CG-08 exact boundary must not release Williamson actions")

holders_by_key = {
    "1": {A_COMM: "Terry Cook", A_JP: "KT Musselman", A_CONST: "Mickey Chance"},
    "2": {A_COMM: "Cynthia Long", A_JP: "Angela Williams", A_CONST: "Jeff Anderson"},
    "3": {A_COMM: "Valerie Covey", A_JP: "Evelyn McLean", A_CONST: "Kevin Wilkie"},
    "4": {A_COMM: "Russ Boles", A_JP: "Rhonda Redden", A_CONST: "Paul Leal"},
}

side_summaries = []
for label, result, expected_key in (
    ("side_a", side_a, boundary["side_a_key"]),
    ("side_b", side_b, boundary["side_b_key"]),
):
    payload = result["payload"]
    assignments = {
        row["adapter_id"]: str(row["district_key"])
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == J
    }
    if set(assignments) != expected_adapters or set(assignments.values()) != {expected_key}:
        raise AssertionError(f"CG-08 {label} must resolve all three adapters to {expected_key}, got {assignments}")
    reps = {
        row["adapter_id"]: row.get("representative")
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == J
    }
    if reps != holders_by_key[expected_key]:
        raise AssertionError(f"CG-08 {label} representative join mismatch for key {expected_key}: {reps}")
    offices = [row for row in payload.get("applicable_offices") or [] if row.get("jurisdiction_id") == J]
    if len(offices) != 9:
        raise AssertionError(f"CG-08 {label} must restore 9 Williamson offices, got {len(offices)}")
    side_summaries.append(
        {
            "side": label,
            "district_key": expected_key,
            "assignments": assignments,
            "representatives": reps,
            "applicable_offices": len(offices),
            "status": "PASS",
        }
    )

if boundary["side_a_key"] == boundary["side_b_key"]:
    raise AssertionError("CG-08 sides must resolve to different precinct keys")
if len(boundary["exact_keys"]) < 2:
    raise AssertionError("CG-08 exact boundary must intersect multiple official precinct polygons")

summary = {
    "gate": "CG-08",
    "status": "PASS",
    "county": "Williamson County, TX",
    "geoid": "48491",
    "service_url": SERVICE,
    "district_field": FIELD,
    "boundary_policy": "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK",
    "shared_geometry_families": sorted(expected_adapters),
    "exact_boundary": {
        "midpoint": boundary["midpoint"],
        "official_intersections": boundary["exact_keys"],
        "district_assignments": 0,
        "applicable_offices": 6,
        "district_offices": 0,
    },
    "sides": side_summaries,
    "epsilon_degrees": boundary["epsilon_degrees"],
    "engine_version": "0.6.1",
    "registry_artifact_version": "0.5.3",
    "packaged": False,
    "engine_change_required": False,
    "next_gate": "CG-09 package + regression",
}
(OUTPUT / "cg08-boundary-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("WILLIAMSON CG-08 PASS")
