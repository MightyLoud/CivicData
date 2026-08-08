#!/usr/bin/env python3
"""Williamson County CG-05 live GIS / adapter proof.

This is an onboarding probe, not a packaged county release. It proves that the
existing Texas county archetype can express Williamson County using official
county GIS with no resolver change.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke" / "williamson"
OUTPUT.mkdir(parents=True, exist_ok=True)
BUILDER_PATH = ROOT / "tools" / "civic_gps_tx_county_archetype.py"

SERVICE = "https://gis.wilco.org/arcgis/rest/services/public/county_administrative_boundaries/MapServer/0"
FIELD = "PCT_NUMBER"
COUNTY_WHERE = "COUNTY='WILLIAMSON'"
EXPECTED_KEYS = {"1", "2", "3", "4"}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"})


def get_json(url: str, params: dict | None = None) -> dict:
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


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        crosses = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
        )
        if crosses:
            inside = not inside
        j = i
    return inside


def point_in_geometry(x: float, y: float, geometry: dict) -> bool:
    # Esri polygon rings use an even/odd fill rule; toggling handles holes.
    inside = False
    for ring in geometry.get("rings") or []:
        if point_in_ring(x, y, ring):
            inside = not inside
    return inside


def interior_point(geometry: dict) -> tuple[float, float]:
    rings = geometry.get("rings") or []
    if not rings:
        raise AssertionError("Polygon feature has no rings")
    xs = [float(p[0]) for ring in rings for p in ring]
    ys = [float(p[1]) for ring in rings for p in ring]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    # Deterministic grid search for a point safely inside the polygon.
    for denom in (10, 20, 40):
        for iy in range(1, denom):
            y = ymin + (ymax - ymin) * iy / denom
            for ix in range(1, denom):
                x = xmin + (xmax - xmin) * ix / denom
                if point_in_geometry(x, y, geometry):
                    return x, y
    raise AssertionError("Could not derive an interior point from official geometry")


def load_builder():
    spec = importlib.util.spec_from_file_location("civic_gps_tx_county_archetype_williamson", BUILDER_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


meta = get_json(SERVICE, {"f": "json"})
if meta.get("geometryType") != "esriGeometryPolygon":
    raise AssertionError(f"Expected polygon layer, got {meta.get('geometryType')}")
field = next((row for row in meta.get("fields") or [] if row.get("name") == FIELD), None)
if not field:
    raise AssertionError(f"Official layer is missing {FIELD}")
if field.get("type") not in {"esriFieldTypeSmallInteger", "esriFieldTypeInteger"}:
    raise AssertionError(f"{FIELD} must be numeric, got {field.get('type')}")

features_body = get_json(
    SERVICE.rstrip("/") + "/query",
    {
        "where": COUNTY_WHERE,
        "outFields": f"{FIELD},COUNTY",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    },
)
features = features_body.get("features") or []
by_key: dict[str, list[dict]] = {}
for feature in features:
    attrs = feature.get("attributes") or {}
    if str(attrs.get("COUNTY") or "").strip().upper() != "WILLIAMSON":
        continue
    key = normalize_key(attrs.get(FIELD))
    by_key.setdefault(key, []).append(feature)

if set(by_key) != EXPECTED_KEYS:
    raise AssertionError(f"Expected Williamson precinct keys {sorted(EXPECTED_KEYS)}, got {sorted(by_key)}")

samples: dict[str, dict] = {}
for key in sorted(EXPECTED_KEYS, key=int):
    point = None
    for feature in by_key[key]:
        geometry = feature.get("geometry") or {}
        try:
            point = interior_point(geometry)
            break
        except AssertionError:
            continue
    if point is None:
        raise AssertionError(f"Could not derive interior control for precinct {key}")
    lon, lat = point
    intersect = get_json(
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
    got = sorted({normalize_key((row.get("attributes") or {}).get(FIELD)) for row in intersect.get("features") or []})
    if got != [key]:
        raise AssertionError(f"Precinct {key} interior point expected [{key}], got {got} at {(lon, lat)}")
    samples[key] = {"lon": lon, "lat": lat, "intersections": got}

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
        "adapter_id": "DIST-TX-WILLIAMSON-COMMISSIONER",
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
        "adapter_id": "DIST-TX-WILLIAMSON-JP",
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
        "adapter_id": "DIST-TX-WILLIAMSON-CONSTABLE",
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

builder = load_builder()
release, bundle = builder.build_texas_county_precinct_artifacts(
    {
        "county_name": "Williamson County",
        "county_geoid": "48491",
        "jurisdiction_id": "jur-us-tx-williamson-county",
        "division_id": "div-us-tx-williamson-county",
        "adapter_id": "ADAPTER-TX-WILLIAMSON",
        "response_id_prefix": "civic-gps-williamson",
        "release_filename": "civic_gps_williamson_county_v0.1.json",
        "snapshot_ref": "williamson-cg05-live-proof-2026-08-08",
        "observed_on": "2026-08-08",
        "countywide_offices": countywide,
        "district_families": families,
        "release_note": "CG-05 onboarding proof only; not yet packaged or released.",
        "release_status": "PROBE_CURRENT",
        "source_status": "LIVE_ARCHETYPE_PROOF",
        "source_manifest": {
            "identity": "https://www.wilcotx.gov/188/Elected-Officials + current office-specific pages",
            "geometry": SERVICE,
        },
    }
)

if len(release["payload"]["offices"]) != 18 or len(release["payload"]["officeholders"]) != 18:
    raise AssertionError("Williamson archetype output must contain 18 offices and 18 holders")
if len(bundle.get("district_adapters") or []) != 3:
    raise AssertionError("Williamson must emit Commissioner, JP, and Constable adapters")
for adapter in bundle["district_adapters"]:
    if adapter.get("service_url") != SERVICE or adapter.get("district_field") != FIELD:
        raise AssertionError(f"Adapter source mismatch: {adapter}")
    if adapter.get("failure_scope") != "ADAPTER":
        raise AssertionError(f"Adapter must fail independently: {adapter.get('adapter_id')}")
    if adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY":
        raise AssertionError(f"GIS must not supply identity: {adapter.get('adapter_id')}")
    if adapter.get("boundary_policy") != "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK":
        raise AssertionError(f"Boundary policy drift: {adapter.get('adapter_id')}")

summary = {
    "gate": "CG-05",
    "status": "PASS",
    "county": "Williamson County, TX",
    "geoid": "48491",
    "service_url": SERVICE,
    "district_field": FIELD,
    "field_type": field.get("type"),
    "keys": sorted(EXPECTED_KEYS, key=int),
    "sample_intersections": samples,
    "adapter_ids": [row["adapter_id"] for row in bundle["district_adapters"]],
    "failure_scope": "ADAPTER",
    "boundary_policy": "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK",
    "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
    "generated_offices": len(release["payload"]["offices"]),
    "generated_holders": len(release["payload"]["officeholders"]),
    "engine_change_required": False,
}
(OUTPUT / "cg05-adapter-proof.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("WILLIAMSON CG-05 PASS")
