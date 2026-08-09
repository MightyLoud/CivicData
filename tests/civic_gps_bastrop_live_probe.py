#!/usr/bin/env python3
"""Packaged Bastrop County regression for Civic GPS v0.6.2 / registry v0.5.9."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-bastrop-cg09"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
RELEASE_PATH = GPS / "civic_gps_bastrop_county_v0.1.json"
SERVICE = "https://maps.co.bastrop.tx.us/server/rest/services/Viewers/PublicGISViewerService/MapServer/8"
FIELD = "precinct"
J = "jur-us-tx-bastrop-county"
TRAVIS = "jur-us-tx-travis-county"
A_COMM = "DIST-TX-BASTROP-COMMISSIONER"
A_JP = "DIST-TX-BASTROP-JP"
A_CONST = "DIST-TX-BASTROP-CONSTABLE"
ADAPTERS = (A_COMM, A_JP, A_CONST)
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
EXPECTED_REGISTRY_VERSION = os.environ.get("CIVIC_GPS_EXPECTED_REGISTRY_VERSION", "0.5.9")
EXPECTED_RUNTIME_SHA256 = os.environ.get(
    "CIVIC_GPS_EXPECTED_RUNTIME_SHA256",
    "49b54af31cb4687936a2dddb6a91f6305aa7b4977756a3db203562971296a23a",
)
EXPECTED_LAYERS = {
    "bastrop_county_commissioner_precinct",
    "bastrop_county_jp_precinct",
    "bastrop_county_constable_precinct",
}
EXPECTED_REPS = {
    "1": {A_COMM: "Butch Carmack", A_JP: "Cindy Allen", A_CONST: "Wayne Wood"},
    "2": {A_COMM: "Clara Beckett", A_JP: "Zachary Carter", A_CONST: "James Scoggins"},
    "3": {A_COMM: "Mark Meuth", A_JP: "Krystal Stabeno", A_CONST: "Tim Sparkman"},
    "4": {A_COMM: "David Glass", A_JP: "Larry Dunne", A_CONST: "Joey Dzienowski"},
}
COUNTYWIDE_IDS = {
    "office-us-tx-bastrop-county-judge",
    "office-us-tx-bastrop-county-sheriff",
    "office-us-tx-bastrop-county-clerk",
    "office-us-tx-bastrop-county-district-clerk",
    "office-us-tx-bastrop-county-tax-assessor-collector",
    "office-us-tx-bastrop-county-treasurer",
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
        raise AssertionError(f"[{label}] Bastrop actions must remain unreleased: {actions}")


engine_mod = load_module("civic_gps_engine_bastrop_packaged", ENGINE_PATH)
registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != EXPECTED_REGISTRY_VERSION:
    raise AssertionError(
        f"Bastrop packaged proof requires engine 0.6.2 / registry {EXPECTED_REGISTRY_VERSION}, got "
        f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
    )
bundle = next(
    (row for row in registry.get("bundles", []) if row.get("adapter_id") == "ADAPTER-TX-BASTROP"),
    None,
)
if not bundle:
    raise AssertionError("Packaged registry is missing ADAPTER-TX-BASTROP")
if bundle.get("release_files") != [RELEASE_PATH.name]:
    raise AssertionError(f"Unexpected Bastrop release files: {bundle.get('release_files')}")
if bundle.get("action_registry_files"):
    raise AssertionError("Bastrop action routing must remain unreleased in CG-09")
adapters = {row.get("adapter_id"): row for row in bundle.get("district_adapters", [])}
if set(adapters) != set(ADAPTERS):
    raise AssertionError(f"Unexpected Bastrop adapters: {sorted(adapters)}")
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
    (row for row in bundle.get("known_gaps", []) if row.get("gap_id") == "GAP-BASTROP-GPS-003"),
    None,
)
if not gap or gap.get("status") != "PROTECTED_PROMOTION_PENDING":
    raise AssertionError(f"Bastrop package gap state changed: {gap}")

release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
if release.get("meta", {}).get("release_status") != "RELEASE_BACKED_CURRENT":
    raise AssertionError("Bastrop packaged release status changed")
release_without_hash = copy.deepcopy(release)
recorded_release_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
if recorded_release_sha != canonical_sha(release_without_hash):
    raise AssertionError("Bastrop canonical content SHA mismatch")
offices = release.get("payload", {}).get("offices", [])
holders = release.get("payload", {}).get("officeholders", [])
if len(offices) != 18 or len(holders) != 18:
    raise AssertionError(
        f"Packaged Bastrop release must contain 18 offices / 18 holders, got "
        f"{len(offices)} / {len(holders)}"
    )
office_ids = {row.get("office_id") for row in offices}
holder_ids = {row.get("office_id") for row in holders}
if len(office_ids) != 18 or office_ids != holder_ids:
    raise AssertionError("Packaged Bastrop office/officeholder identity join failed")
if not COUNTYWIDE_IDS.issubset(office_ids):
    raise AssertionError("Packaged Bastrop bounded countywide office set changed")

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
    ("bastrop-p1", "803 Pine Street, Bastrop, TX 78602", "1"),
    ("bastrop-p2", "1624 NE Loop 230, Smithville, TX 78957", "2"),
    ("bastrop-p3", "5540 FM 535, Cedar Creek, TX 78612", "3"),
    ("bastrop-p4", "1125 Dildy Drive, Elgin, TX 78621", "4"),
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
        raise AssertionError(f"[{case_id}] Bastrop jurisdiction did not activate")
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
        f"office-us-tx-bastrop-county-commissioner-{key}",
        f"office-us-tx-bastrop-county-jp-{key}",
        f"office-us-tx-bastrop-county-constable-{key}",
    }
    if {row.get("office_id") for row in district} != expected_district_ids:
        raise AssertionError(f"[{case_id}] district office set changed")
    release_layers = {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "RELEASE_BACKED"
        and str(row.get("layer") or "").startswith("bastrop_county_")
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
    raise AssertionError(f"Packaged interiors missed Bastrop keys: {sorted(keys_covered)}")

outside, outside_attempts = resolve_live(
    "bastrop-outside-austin",
    "700 Lavaca Street, Austin, TX 78701",
)
(OUTPUT / "bastrop-outside-austin.json").write_text(
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
    raise AssertionError("Outside-Austin control leaked Bastrop assignments/offices/actions")
if any(
    "bastrop" in json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
    for row in outside_payload.get("coverage") or []
):
    raise AssertionError("Outside-Austin control leaked Bastrop coverage")

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
        raise AssertionError(f"Bastrop live precinct key set changed: {sorted(keys)}")
    return features


def point_keys(lon: float, lat: float) -> list[str]:
    body = get_json(
        SERVICE.rstrip("/") + "/query",
        {
            "where": "1=1",
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
        midpoint_keys = point_keys(*midpoint)
        if len(midpoint_keys) != 2:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        nx, ny = -dy / norm, dx / norm
        for epsilon in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
            side_a = (midpoint[0] + nx * epsilon, midpoint[1] + ny * epsilon)
            side_b = (midpoint[0] - nx * epsilon, midpoint[1] - ny * epsilon)
            side_a_keys = point_keys(*side_a)
            side_b_keys = point_keys(*side_b)
            if (
                len(side_a_keys) == 1
                and len(side_b_keys) == 1
                and side_a_keys[0] != side_b_keys[0]
                and {side_a_keys[0], side_b_keys[0]} == set(midpoint_keys)
            ):
                return {
                    "midpoint": midpoint,
                    "exact_intersections": midpoint_keys,
                    "shared_segment_keys": shared_keys,
                    "side_a": side_a,
                    "side_a_key": side_a_keys[0],
                    "side_b": side_b,
                    "side_b_key": side_b_keys[0],
                    "epsilon_degrees": epsilon,
                }
    raise AssertionError("Could not derive exact two-sided Bastrop boundary")


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
                                "matchedAddress": "BASTROP PACKAGE BOUNDARY",
                                "coordinates": {"x": self.lon, "y": self.lat},
                                "geographies": {
                                    "States": [{"GEOID": "48", "STATE": "48"}],
                                    "Counties": [{"GEOID": "48021", "COUNTY": "021"}],
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
        and str(row.get("layer") or "").startswith("bastrop_county_")
    }


boundary = find_shared_boundary()
exact = resolve_point("bastrop-shared-boundary-exact", tuple(boundary["midpoint"]))
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
    payload = resolve_point(f"bastrop-shared-boundary-{label}", tuple(point))
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

runtime_sha = hashlib.sha256(
    b"".join(
        part.read_bytes()
        for part in sorted((ROOT / "civic_gps_runtime_parts").glob("part.*"))
    )
).hexdigest()
if runtime_sha != EXPECTED_RUNTIME_SHA256:
    raise AssertionError(f"Packaged Bastrop runtime SHA changed: {runtime_sha}")

summary = {
    "status": "PASS",
    "gate": "CG-09",
    "county": "Bastrop County, TX",
    "geoid": "48021",
    "engine_version": "0.6.2",
    "registry_artifact_version": EXPECTED_REGISTRY_VERSION,
    "runtime_sha256": runtime_sha,
    "release_offices": 18,
    "release_holders": 18,
    "interior_controls": interior_summaries,
    "outside_negative": {
        "status": "PASS",
        "travis_assignments": travis_assignments,
        "travis_applicable_offices": 9,
        "resolution_attempts": outside_attempts,
        "bastrop_leakage": 0,
    },
    "shared_boundary": {
        "midpoint": boundary["midpoint"],
        "official_intersections": boundary["exact_intersections"],
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
(OUTPUT / "packaged-bastrop-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("BASTROP PACKAGED CG-09 PASS")
