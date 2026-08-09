#!/usr/bin/env python3
"""Packaged Brazos County CG-09 proof for Civic GPS v0.6.2 / registry v0.5.8."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import math
import sys
import time
from pathlib import Path
from zipfile import ZipFile

import requests

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-brazos-cg09"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
RELEASE_PATH = GPS / "civic_gps_brazos_county_v0.1.json"
SERVICE = "https://services5.arcgis.com/s91b2wxhO15FkWh5/arcgis/rest/services/BRAZOS_CC_PCTS_11022021/FeatureServer/0"
FIELD = "ID"
J = "jur-us-tx-brazos-county"
TRAVIS = "jur-us-tx-travis-county"
A_COMM = "DIST-TX-BRAZOS-COMMISSIONER"
A_JP = "DIST-TX-BRAZOS-JP"
A_CONST = "DIST-TX-BRAZOS-CONSTABLE"
ADAPTERS = (A_COMM, A_JP, A_CONST)
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
EXPECTED_LAYERS = {
    "brazos_county_commissioner_precinct",
    "brazos_county_jp_precinct",
    "brazos_county_constable_precinct",
}
EXPECTED_REPS = {
    "1": {A_COMM: "Bentley Nettles", A_JP: "Kenny Elliott", A_CONST: "Jeff Reeves"},
    "2": {A_COMM: "Chuck Konderla", A_JP: "Terrence P. Nunn", A_CONST: "Donald Lampo"},
    "3": {A_COMM: "Fred Brown", A_JP: "Rick Hill", A_CONST: "J.P. Ingram"},
    "4": {A_COMM: "Wanda J. Watson", A_JP: "Darrell Booker", A_CONST: "Hezekiah Carter, Jr."},
}
COUNTYWIDE_IDS = {
    "office-us-tx-brazos-county-judge",
    "office-us-tx-brazos-county-sheriff",
    "office-us-tx-brazos-county-clerk",
    "office-us-tx-brazos-county-district-clerk",
    "office-us-tx-brazos-county-tax-assessor-collector",
    "office-us-tx-brazos-county-treasurer",
}
TRAVIS_EXPECTED = {
    "DIST-TX-TRAVIS-COMMISSIONER": "3",
    "DIST-TX-TRAVIS-JP": "5",
    "DIST-TX-TRAVIS-CONSTABLE": "5",
}
TRANSIENT_CENSUS_MARKERS = (
    "timed out",
    "timeout",
    "connection",
    "temporarily unavailable",
    "remote disconnected",
    "502",
    "503",
    "504",
)


def load_module(name: str, path: Path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    return module


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def assignment_map(payload: dict) -> dict[str, str]:
    return {
        row["adapter_id"]: str(row["district_key"])
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == J
    }


def representative_map(payload: dict) -> dict[str, str | None]:
    return {
        row["adapter_id"]: row.get("representative")
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == J
    }


def applicable(payload: dict) -> list[dict]:
    return [
        row
        for row in payload.get("applicable_offices") or []
        if row.get("jurisdiction_id") == J
    ]


def assert_no_actions(label: str, payload: dict) -> None:
    actions = [
        row
        for row in payload.get("action_links") or []
        if row.get("jurisdiction_id") == J
    ]
    if actions:
        raise AssertionError(f"[{label}] Brazos actions must remain unreleased: {actions}")


engine_mod = load_module("civic_gps_engine_brazos_packaged", ENGINE_PATH)
runtime_bytes = b"".join(
    part.read_bytes()
    for part in sorted((ROOT / "civic_gps_runtime_parts").glob("part.*"))
)
with ZipFile(io.BytesIO(runtime_bytes)) as runtime_archive:
    registry = json.loads(runtime_archive.read("civic_gps/registry.json"))
    release = json.loads(runtime_archive.read(f"civic_gps/{RELEASE_PATH.name}"))
if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.5.8":
    raise AssertionError(
        "Brazos packaged proof requires engine 0.6.2 / registry 0.5.8, got "
        f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
    )
bundle = next(
    (row for row in registry.get("bundles", []) if row.get("adapter_id") == "ADAPTER-TX-BRAZOS"),
    None,
)
if not bundle:
    raise AssertionError("Packaged registry is missing ADAPTER-TX-BRAZOS")
if bundle.get("release_files") != [RELEASE_PATH.name]:
    raise AssertionError(f"Unexpected Brazos release files: {bundle.get('release_files')}")
if bundle.get("action_registry_files"):
    raise AssertionError("Brazos action routing must remain unreleased in CG-09")
adapters = {row.get("adapter_id"): row for row in bundle.get("district_adapters", [])}
if set(adapters) != set(ADAPTERS):
    raise AssertionError(f"Unexpected Brazos adapters: {sorted(adapters)}")
for adapter_id, adapter in adapters.items():
    if adapter.get("failure_scope") != "ADAPTER":
        raise AssertionError(f"{adapter_id} must remain ADAPTER-scoped")
    if adapter.get("boundary_policy") != POLICY:
        raise AssertionError(f"{adapter_id} boundary policy changed")
    if adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY":
        raise AssertionError(f"{adapter_id} identity source changed")
    if adapter.get("source_status") != "LIVE_INTERIOR_NEGATIVE_BOUNDARY_PASS":
        raise AssertionError(f"{adapter_id} packaged source status changed")
gap = next(
    (row for row in bundle.get("known_gaps", []) if row.get("gap_id") == "GAP-BRAZOS-GPS-003"),
    None,
)
if not gap or gap.get("status") != "PROTECTED_PROMOTION_PENDING":
    raise AssertionError(f"Brazos package gap state changed: {gap}")

if release.get("meta", {}).get("release_status") != "RELEASE_BACKED_CURRENT":
    raise AssertionError("Brazos packaged release status changed")
release_without_hash = copy.deepcopy(release)
recorded_release_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
if recorded_release_sha != canonical_sha(release_without_hash):
    raise AssertionError("Brazos canonical content SHA mismatch")
offices = release.get("payload", {}).get("offices", [])
holders = release.get("payload", {}).get("officeholders", [])
if len(offices) != 18 or len(holders) != 18:
    raise AssertionError(
        f"Packaged Brazos release must contain 18 offices / 18 holders, got "
        f"{len(offices)} / {len(holders)}"
    )
office_ids = {row.get("office_id") for row in offices}
holder_ids = {row.get("office_id") for row in holders}
if len(office_ids) != 18 or office_ids != holder_ids:
    raise AssertionError("Packaged Brazos office/officeholder identity join failed")
if not COUNTYWIDE_IDS.issubset(office_ids):
    raise AssertionError("Packaged Brazos bounded countywide office set changed")

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)


def resolve_live(label: str, address: str) -> tuple[dict, int]:
    for attempt in range(1, 4):
        result = resolver.resolve(address, observed_on=None)
        error = result.get("error") or {}
        details = error.get("details") or {}
        upstream_error = str(details.get("error") or "").lower()
        transient = (
            error.get("code") == "UPSTREAM_REQUEST_FAILED"
            and error.get("message") == "GEOCODER request failed."
            and str(details.get("url") or "").startswith("https://geocoding.geo.census.gov/geocoder/")
            and any(marker in upstream_error for marker in TRANSIENT_CENSUS_MARKERS)
        )
        if not transient or attempt == 3:
            if "error" in result:
                raise AssertionError(f"[{label}] engine error: {result['error']}")
            return result, attempt
        time.sleep(2 ** (attempt - 1))
    raise AssertionError(f"[{label}] unreachable retry state")


CASES = [
    ("brazos-p1", "412 William D Fitch Parkway, College Station, TX 77845", "1"),
    ("brazos-p2", "977 N FM 2038, Bryan, TX 77808", "2"),
    ("brazos-p3", "1500 George Bush Drive, College Station, TX 77840", "3"),
    ("brazos-p4", "300 E 26th Street, Bryan, TX 77803", "4"),
]
interior_summaries = []
keys_covered = set()
for case_id, address, key in CASES:
    result, attempts = resolve_live(case_id, address)
    (OUTPUT / f"{case_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    payload = result["payload"]
    if J not in {row.get("jurisdiction_id") for row in payload.get("jurisdictions") or []}:
        raise AssertionError(f"[{case_id}] Brazos jurisdiction did not activate")
    assignments = assignment_map(payload)
    expected_assignments = {adapter_id: key for adapter_id in ADAPTERS}
    if assignments != expected_assignments:
        raise AssertionError(f"[{case_id}] expected {expected_assignments}, got {assignments}")
    reps = representative_map(payload)
    if reps != EXPECTED_REPS[key]:
        raise AssertionError(f"[{case_id}] representative join mismatch: {reps}")
    matched = applicable(payload)
    wide = [row for row in matched if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in matched if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(matched), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(
            f"[{case_id}] expected 9 = 6 wide + 3 district, got "
            f"{len(matched)} = {len(wide)} + {len(district)}"
        )
    if {row.get("office_id") for row in wide} != COUNTYWIDE_IDS:
        raise AssertionError(f"[{case_id}] bounded countywide office set changed")
    expected_district_ids = {
        f"office-us-tx-brazos-county-commissioner-{key}",
        f"office-us-tx-brazos-county-jp-{key}",
        f"office-us-tx-brazos-county-constable-{key}",
    }
    if {row.get("office_id") for row in district} != expected_district_ids:
        raise AssertionError(f"[{case_id}] district office set changed")
    release_layers = {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "RELEASE_BACKED"
        and str(row.get("layer") or "").startswith("brazos_county_")
    }
    if release_layers != EXPECTED_LAYERS:
        raise AssertionError(f"[{case_id}] packaged coverage layers changed: {release_layers}")
    assert_no_actions(case_id, payload)
    keys_covered.add(key)
    interior_summaries.append(
        {
            "case": case_id,
            "key": key,
            "assignments": assignments,
            "representatives": reps,
            "applicable_offices": 9,
            "resolution_attempts": attempts,
            "status": "PASS",
        }
    )
if keys_covered != {"1", "2", "3", "4"}:
    raise AssertionError(f"Packaged interiors missed Brazos keys: {sorted(keys_covered)}")

outside, outside_attempts = resolve_live(
    "brazos-outside-austin",
    "700 Lavaca Street, Austin, TX 78701",
)
(OUTPUT / "brazos-outside-austin.json").write_text(
    json.dumps(outside, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
outside_payload = outside["payload"]
outside_jurisdictions = {
    row.get("jurisdiction_id") for row in outside_payload.get("jurisdictions") or []
}
if TRAVIS not in outside_jurisdictions or J in outside_jurisdictions:
    raise AssertionError(f"Outside control failed jurisdiction isolation: {outside_jurisdictions}")
travis_assignments = {
    row["adapter_id"]: str(row["district_key"])
    for row in outside_payload.get("district_assignments") or []
    if row.get("jurisdiction_id") == TRAVIS
}
if travis_assignments != TRAVIS_EXPECTED:
    raise AssertionError(f"Outside control changed normal Travis assignments: {travis_assignments}")
travis_offices = [
    row
    for row in outside_payload.get("applicable_offices") or []
    if row.get("jurisdiction_id") == TRAVIS
]
if len(travis_offices) != 9:
    raise AssertionError(f"Outside control must preserve nine Travis offices, got {len(travis_offices)}")
if any(
    row.get("jurisdiction_id") == J
    for row in (outside_payload.get("district_assignments") or [])
    + (outside_payload.get("applicable_offices") or [])
    + (outside_payload.get("action_links") or [])
):
    raise AssertionError("Outside-Austin control leaked Brazos assignments/offices/actions")
if any(
    "brazos" in json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
    for row in outside_payload.get("coverage") or []
):
    raise AssertionError("Outside-Austin control leaked Brazos coverage")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})


def get_json(url: str, params: dict) -> dict:
    response = SESSION.get(url, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
    return body


def normalize_key(raw: object) -> str:
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def all_features() -> list[dict]:
    body = get_json(
        SERVICE.rstrip("/") + "/query",
        {
            "where": "1=1",
            "outFields": FIELD,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
    )
    features = body.get("features") or []
    keys = {
        normalize_key((feature.get("attributes") or {}).get(FIELD))
        for feature in features
    }
    if keys != {"1", "2", "3", "4"}:
        raise AssertionError(f"Brazos live precinct key set changed: {sorted(keys)}")
    return features


def point_keys(
    lon: float,
    lat: float,
    *,
    distance_meters: int | None = None,
) -> list[str]:
    params = {
        "where": "1=1",
        "geometry": f"{lon:.12f},{lat:.12f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": FIELD,
        "returnGeometry": "false",
        "f": "json",
    }
    if distance_meters is not None:
        params["distance"] = str(distance_meters)
        params["units"] = "esriSRUnit_Meter"
    body = get_json(
        SERVICE.rstrip("/") + "/query",
        params,
    )
    values = []
    for feature in body.get("features") or []:
        raw = (feature.get("attributes") or {}).get(FIELD)
        if raw not in (None, ""):
            values.append(normalize_key(raw))
    return sorted(set(values), key=int)


def rounded_point(point: tuple[float, float]) -> tuple[float, float]:
    return round(float(point[0]), 8), round(float(point[1]), 8)


def segment_index(features: list[dict]) -> dict:
    index: dict = {}
    for feature in features:
        district = normalize_key((feature.get("attributes") or {}).get(FIELD))
        for ring in (feature.get("geometry") or {}).get("rings") or []:
            for a_raw, b_raw in zip(ring, ring[1:]):
                a = (float(a_raw[0]), float(a_raw[1]))
                b = (float(b_raw[0]), float(b_raw[1]))
                key_a, key_b = rounded_point(a), rounded_point(b)
                if key_a == key_b:
                    continue
                index.setdefault(tuple(sorted((key_a, key_b))), []).append((district, a, b))
    return index


def find_shared_boundary() -> dict:
    candidates = []
    for rows in segment_index(all_features()).values():
        keys = sorted({row[0] for row in rows}, key=int)
        if len(keys) < 2:
            continue
        a, b = rows[0][1], rows[0][2]
        candidates.append((math.hypot(b[0] - a[0], b[1] - a[1]), keys, a, b))
    candidates.sort(reverse=True, key=lambda row: row[0])
    for _, shared_keys, a, b in candidates:
        midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        exact_service_keys = point_keys(*midpoint)
        topology_nearby_keys = point_keys(*midpoint, distance_meters=1)
        if (
            len(exact_service_keys) != 1
            or len(topology_nearby_keys) != 2
            or exact_service_keys[0] not in topology_nearby_keys
            or set(topology_nearby_keys) != set(shared_keys)
        ):
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        nx, ny = -dy / norm, dx / norm
        for epsilon in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
            side_a = (midpoint[0] + nx * epsilon, midpoint[1] + ny * epsilon)
            side_b = (midpoint[0] - nx * epsilon, midpoint[1] - ny * epsilon)
            side_a_keys = point_keys(*side_a, distance_meters=1)
            side_b_keys = point_keys(*side_b, distance_meters=1)
            if (
                len(side_a_keys) == 1
                and len(side_b_keys) == 1
                and side_a_keys[0] != side_b_keys[0]
                and {side_a_keys[0], side_b_keys[0]} == set(topology_nearby_keys)
            ):
                return {
                    "midpoint": midpoint,
                    "exact_service_keys": exact_service_keys,
                    "topology_nearby_keys": topology_nearby_keys,
                    "shared_segment_keys": shared_keys,
                    "side_a": side_a,
                    "side_a_key": side_a_keys[0],
                    "side_b": side_b,
                    "side_b_key": side_b_keys[0],
                    "epsilon_degrees": epsilon,
                }
    raise AssertionError("Could not derive exact two-sided Brazos boundary")


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class FixedPointSession:
    def __init__(self, lon: float, lat: float):
        self.lon = lon
        self.lat = lat
        self.real = requests.Session()
        self.real.headers.update(
            {"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"}
        )

    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse(
                {
                    "result": {
                        "addressMatches": [
                            {
                                "matchedAddress": "BRAZOS PACKAGE BOUNDARY",
                                "coordinates": {"x": self.lon, "y": self.lat},
                                "geographies": {
                                    "States": [{"GEOID": "48", "STATE": "48"}],
                                    "Counties": [{"GEOID": "48041", "COUNTY": "041"}],
                                },
                            }
                        ]
                    }
                }
            )
        return self.real.get(url, params=params, timeout=timeout)


def resolve_point(label: str, point: tuple[float, float]) -> dict:
    fixed = engine_mod.CivicGPSOverlayEngine.from_file(
        REGISTRY_PATH,
        session=FixedPointSession(point[0], point[1]),
        timeout_seconds=30.0,
    )
    result = fixed.resolve(label, observed_on=None)
    if "error" in result:
        raise AssertionError(f"[{label}] boundary engine error: {result['error']}")
    (OUTPUT / f"{label}.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result["payload"]


def conflict_layers(payload: dict) -> set[str]:
    return {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "CONFLICT"
        and str(row.get("layer") or "").startswith("brazos_county_")
    }


boundary = find_shared_boundary()
exact = resolve_point("brazos-shared-boundary-exact", tuple(boundary["midpoint"]))
exact_assignments = assignment_map(exact)
if exact_assignments or representative_map(exact):
    raise AssertionError(
        f"Exact shared boundary must suppress all three district families: {exact_assignments}"
    )
exact_matched = applicable(exact)
exact_wide = [
    row for row in exact_matched if row.get("applicability_scope") == "JURISDICTION_WIDE"
]
exact_district = [
    row for row in exact_matched if row.get("applicability_scope") == "DISTRICT_MATCH"
]
if (len(exact_matched), len(exact_wide), len(exact_district)) != (6, 6, 0):
    raise AssertionError(
        f"Exact boundary must preserve 6 = 6 wide + 0 district offices, got "
        f"{len(exact_matched)} = {len(exact_wide)} + {len(exact_district)}"
    )
if {row.get("office_id") for row in exact_wide} != COUNTYWIDE_IDS:
    raise AssertionError("Exact boundary countywide office set changed")
if conflict_layers(exact) != EXPECTED_LAYERS:
    raise AssertionError(f"Exact boundary conflict layers changed: {conflict_layers(exact)}")
assert_no_actions("boundary-exact", exact)

boundary_sides = []
for label, point, expected_key in (
    ("side-a", boundary["side_a"], boundary["side_a_key"]),
    ("side-b", boundary["side_b"], boundary["side_b_key"]),
):
    payload = resolve_point(f"brazos-shared-boundary-{label}", tuple(point))
    assignments = assignment_map(payload)
    expected_assignments = {adapter_id: expected_key for adapter_id in ADAPTERS}
    if assignments != expected_assignments:
        raise AssertionError(f"Boundary {label} assignments changed: {assignments}")
    reps = representative_map(payload)
    if reps != EXPECTED_REPS[expected_key]:
        raise AssertionError(f"Boundary {label} representative join changed: {reps}")
    matched = applicable(payload)
    wide = [row for row in matched if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in matched if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(matched), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(f"Boundary {label} must restore 9 = 6 + 3 offices")
    assert_no_actions(f"boundary-{label}", payload)
    boundary_sides.append(
        {
            "side": label,
            "key": expected_key,
            "assignments": assignments,
            "representatives": reps,
            "applicable_offices": 9,
            "status": "PASS",
        }
    )
if boundary_sides[0]["key"] == boundary_sides[1]["key"]:
    raise AssertionError("Boundary sides did not resolve distinct precincts")

runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
if runtime_sha != "bc40a0aa46fcdbd5b2c73976747ef702d9a64fd051832c615ba4aba1016a7427":
    raise AssertionError(f"Packaged Brazos runtime SHA changed: {runtime_sha}")

summary = {
    "status": "PASS",
    "gate": "CG-09",
    "county": "Brazos County, TX",
    "geoid": "48041",
    "engine_version": "0.6.2",
    "registry_artifact_version": "0.5.8",
    "runtime_sha256": runtime_sha,
    "release_offices": 18,
    "release_holders": 18,
    "interior_controls": interior_summaries,
    "outside_negative": {
        "status": "PASS",
        "travis_assignments": travis_assignments,
        "travis_applicable_offices": 9,
        "resolution_attempts": outside_attempts,
        "brazos_leakage": 0,
    },
    "shared_boundary": {
        "midpoint": boundary["midpoint"],
        "exact_service_keys": boundary["exact_service_keys"],
        "topology_nearby_keys": boundary["topology_nearby_keys"],
        "distance_probe_meters": 1,
        "exact_assignments": exact_assignments,
        "exact_applicable_offices": 6,
        "exact_conflict_layers": sorted(conflict_layers(exact)),
        "sides": boundary_sides,
        "policy": POLICY,
    },
    "actions": "NOT_YET_RELEASED",
    "candidate_packaged": True,
    "next_gate": "CG-10",
    "stopped_before": "CG-10",
}
(OUTPUT / "packaged-brazos-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("BRAZOS PACKAGED CG-09 PASS")
