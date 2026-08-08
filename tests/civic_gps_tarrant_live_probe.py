#!/usr/bin/env python3
"""Packaged Tarrant County CG-09 proof for Civic GPS v0.6.1 / registry v0.5.5."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-tarrant-cg09"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
RELEASE_PATH = GPS / "civic_gps_tarrant_county_v0.1.json"
COMM_SERVICE = "https://mapit.tarrantcounty.com/arcgis/rest/services/BondProject/BondProjects/MapServer/3"
JPC_SERVICE = "https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/JusticeOfThePeace/MapServer/0"
J = "jur-us-tx-tarrant-county"
TRAVIS = "jur-us-tx-travis-county"
A_COMM = "DIST-TX-TARRANT-COMMISSIONER"
A_JP = "DIST-TX-TARRANT-JP"
A_CONST = "DIST-TX-TARRANT-CONSTABLE"
EXPECTED_ADAPTERS = {A_COMM, A_JP, A_CONST}
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


engine_mod = load_module("civic_gps_engine_tarrant_packaged", ENGINE_PATH)
registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.5":
    raise AssertionError(
        "Tarrant packaged proof requires engine 0.6.1 / registry 0.5.5, got "
        f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
    )
bundle = next(
    (row for row in registry.get("bundles", []) if row.get("adapter_id") == "ADAPTER-TX-TARRANT"),
    None,
)
if not bundle:
    raise AssertionError("Packaged registry is missing ADAPTER-TX-TARRANT")
if bundle.get("release_files") != [RELEASE_PATH.name]:
    raise AssertionError(f"Unexpected Tarrant release files: {bundle.get('release_files')}")
if bundle.get("action_registry_files"):
    raise AssertionError("Tarrant action routing must remain unreleased in CG-09")
adapters = {row.get("adapter_id"): row for row in bundle.get("district_adapters", [])}
if set(adapters) != EXPECTED_ADAPTERS:
    raise AssertionError(f"Unexpected Tarrant adapters: {sorted(adapters)}")
for adapter_id, adapter in adapters.items():
    if adapter.get("failure_scope") != "ADAPTER":
        raise AssertionError(f"{adapter_id} must remain ADAPTER-scoped")
    if adapter.get("boundary_policy") != POLICY:
        raise AssertionError(f"{adapter_id} boundary policy changed")
    if adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY":
        raise AssertionError(f"{adapter_id} identity source changed")

release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
offices = release.get("payload", {}).get("offices", [])
holders = release.get("payload", {}).get("officeholders", [])
if len(offices) != 26 or len(holders) != 26:
    raise AssertionError(
        f"Packaged Tarrant release must contain 26 offices / 26 holders, got {len(offices)} / {len(holders)}"
    )
office_ids = {row.get("office_id") for row in offices}
holder_ids = {row.get("office_id") for row in holders}
if len(office_ids) != 26 or office_ids != holder_ids:
    raise AssertionError("Packaged Tarrant office/officeholder identity join failed")
holder_by_office = {row["office_id"]: row.get("canonical_name") for row in holders}
countywide_ids = {
    "office-us-tx-tarrant-county-judge",
    "office-us-tx-tarrant-county-sheriff",
    "office-us-tx-tarrant-county-clerk",
    "office-us-tx-tarrant-county-district-clerk",
    "office-us-tx-tarrant-county-tax-assessor-collector",
    "office-us-tx-tarrant-county-criminal-district-attorney",
}
if not countywide_ids.issubset(office_ids):
    raise AssertionError("Packaged Tarrant bounded countywide office set changed")

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
CASES = [
    ("tarrant-jp1", "100 W Weatherford Street, Fort Worth, TX 76196", "4", "1", {A_COMM: "Manny Ramirez", A_JP: "Ralph Swearingin Jr.", A_CONST: "Dale Clark"}),
    ("tarrant-jp2", "700 E Abram Street, Arlington, TX 76010", "2", "2", {A_COMM: "Alisa Simmons", A_JP: "Mary Tom Curnutt", A_CONST: "David Woodruff"}),
    ("tarrant-jp3", "1400 Main Street, Southlake, TX 76092", "3", "3", {A_COMM: "Matt Krause", A_JP: "William P. Brandt", A_CONST: "Darrell Huffman"}),
    ("tarrant-jp4", "6713 Telephone Road, Lake Worth, TX 76135", "4", "4", {A_COMM: "Manny Ramirez", A_JP: "Christopher Gregory", A_CONST: "Jody Johnson"}),
    ("tarrant-jp5", "350 W Belknap Street, Fort Worth, TX 76102", "4", "5", {A_COMM: "Manny Ramirez", A_JP: "Sergio L. De Leon", A_CONST: 'Pedro "Pete" Munoz'}),
    ("tarrant-jp6", "6551 Granbury Road, Fort Worth, TX 76133", "1", "6", {A_COMM: "Roderick Miles Jr", A_JP: "Jason Charbonnet", A_CONST: "Jon H. Siegel"}),
    ("tarrant-jp7", "1100 E Broad Street, Mansfield, TX 76063", "2", "7", {A_COMM: "Alisa Simmons", A_JP: "Kenneth Sanders", A_CONST: "Sandra Lee"}),
    ("tarrant-jp8", "3500 Miller Avenue, Fort Worth, TX 76119", "1", "8", {A_COMM: "Roderick Miles Jr", A_JP: "Lisa R. Woodard", A_CONST: "Michael R. Campbell"}),
]
interior_summaries = []
commissioner_keys: set[str] = set()
jpc_keys: set[str] = set()
for case_id, address, commissioner_key, jpc_key, expected_reps in CASES:
    result = resolver.resolve(address, observed_on=None)
    (OUTPUT / f"{case_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if "error" in result:
        raise AssertionError(f"[{case_id}] engine error: {result['error']}")
    payload = result["payload"]
    if J not in {row.get("jurisdiction_id") for row in payload.get("jurisdictions") or []}:
        raise AssertionError(f"[{case_id}] Tarrant jurisdiction did not activate")
    assignments = assignment_map(payload)
    expected_assignments = {A_COMM: commissioner_key, A_JP: jpc_key, A_CONST: jpc_key}
    if assignments != expected_assignments:
        raise AssertionError(f"[{case_id}] expected {expected_assignments}, got {assignments}")
    reps = representative_map(payload)
    if reps != expected_reps:
        raise AssertionError(f"[{case_id}] representative join mismatch: {reps}")
    matched_offices = applicable(payload)
    wide = [row for row in matched_offices if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in matched_offices if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(matched_offices), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(
            f"[{case_id}] expected 9 = 6 wide + 3 district, got "
            f"{len(matched_offices)} = {len(wide)} + {len(district)}"
        )
    if {row.get("office_id") for row in wide} != countywide_ids:
        raise AssertionError(f"[{case_id}] bounded countywide office set changed")
    expected_district_ids = {
        f"office-us-tx-tarrant-county-commissioner-{commissioner_key}",
        f"office-us-tx-tarrant-county-jp-{jpc_key}",
        f"office-us-tx-tarrant-county-constable-{jpc_key}",
    }
    if {row.get("office_id") for row in district} != expected_district_ids:
        raise AssertionError(f"[{case_id}] district office set changed")
    if any(row.get("jurisdiction_id") == J for row in payload.get("action_links") or []):
        raise AssertionError(f"[{case_id}] Tarrant actions must remain unreleased")
    commissioner_keys.add(commissioner_key)
    jpc_keys.add(jpc_key)
    interior_summaries.append(
        {
            "case": case_id,
            "assignments": assignments,
            "representatives": reps,
            "applicable_offices": 9,
            "status": "PASS",
        }
    )
if commissioner_keys != {"1", "2", "3", "4"}:
    raise AssertionError(f"Interior controls missed Commissioner keys: {sorted(commissioner_keys)}")
if jpc_keys != {str(number) for number in range(1, 9)}:
    raise AssertionError(f"Interior controls missed JP/Constable keys: {sorted(jpc_keys)}")

outside = resolver.resolve("700 Lavaca Street, Austin, TX 78701", observed_on=None)
(OUTPUT / "tarrant-outside-austin.json").write_text(
    json.dumps(outside, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
if "error" in outside:
    raise AssertionError(f"Outside-Austin control failed: {outside['error']}")
outside_payload = outside["payload"]
outside_jurisdictions = {
    row.get("jurisdiction_id") for row in outside_payload.get("jurisdictions") or []
}
if TRAVIS not in outside_jurisdictions or J in outside_jurisdictions:
    raise AssertionError(f"Outside control failed jurisdiction isolation: {outside_jurisdictions}")
if any(
    row.get("jurisdiction_id") == J
    for row in (outside_payload.get("district_assignments") or [])
    + (outside_payload.get("applicable_offices") or [])
    + (outside_payload.get("action_links") or [])
):
    raise AssertionError("Outside-Austin control leaked Tarrant assignments/offices/actions")
if any(
    "tarrant" in json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
    for row in outside_payload.get("coverage") or []
):
    raise AssertionError("Outside-Austin control leaked Tarrant coverage")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"})


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
            values.append(normalize_key(raw))
    return sorted(set(values), key=int)


def rounded_point(point: tuple[float, float]) -> tuple[float, float]:
    return round(float(point[0]), 8), round(float(point[1]), 8)


def segment_index(features: list[dict], field: str) -> dict:
    index: dict = {}
    for feature in features:
        district = normalize_key((feature.get("attributes") or {}).get(field))
        for ring in (feature.get("geometry") or {}).get("rings") or []:
            for a_raw, b_raw in zip(ring, ring[1:]):
                a = (float(a_raw[0]), float(a_raw[1]))
                b = (float(b_raw[0]), float(b_raw[1]))
                key_a, key_b = rounded_point(a), rounded_point(b)
                if key_a == key_b:
                    continue
                index.setdefault(tuple(sorted((key_a, key_b))), []).append((district, a, b))
    return index


def find_isolated_boundary(
    primary_service: str,
    primary_field: str,
    other_service: str,
    other_field: str,
) -> dict:
    candidates = []
    for rows in segment_index(all_features(primary_service, primary_field), primary_field).values():
        districts = sorted({row[0] for row in rows}, key=int)
        if len(districts) < 2:
            continue
        a, b = rows[0][1], rows[0][2]
        candidates.append((math.hypot(b[0] - a[0], b[1] - a[1]), districts, a, b))
    candidates.sort(reverse=True, key=lambda row: row[0])
    for _, shared_districts, a, b in candidates:
        midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        primary_mid = point_keys(primary_service, primary_field, *midpoint)
        other_mid = point_keys(other_service, other_field, *midpoint)
        if len(primary_mid) < 2 or len(other_mid) != 1:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        nx, ny = -dy / norm, dx / norm
        for epsilon in (2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5):
            side_a = (midpoint[0] + nx * epsilon, midpoint[1] + ny * epsilon)
            side_b = (midpoint[0] - nx * epsilon, midpoint[1] - ny * epsilon)
            primary_a = point_keys(primary_service, primary_field, *side_a)
            primary_b = point_keys(primary_service, primary_field, *side_b)
            other_a = point_keys(other_service, other_field, *side_a)
            other_b = point_keys(other_service, other_field, *side_b)
            if (
                len(primary_a) == len(primary_b) == len(other_a) == len(other_b) == 1
                and primary_a[0] != primary_b[0]
                and other_a[0] == other_b[0] == other_mid[0]
            ):
                return {
                    "midpoint": midpoint,
                    "primary_mid_keys": primary_mid,
                    "other_mid_key": other_mid[0],
                    "side_a": side_a,
                    "side_a_primary_key": primary_a[0],
                    "side_b": side_b,
                    "side_b_primary_key": primary_b[0],
                    "epsilon_degrees": epsilon,
                    "shared_segment_districts": shared_districts,
                }
    raise AssertionError(f"Could not derive isolated boundary from {primary_service}")


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
            {"User-Agent": "CivicGPS/0.6.1 (+https://github.com/MightyLoud/CivicData)"}
        )

    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse(
                {
                    "result": {
                        "addressMatches": [
                            {
                                "matchedAddress": "TARRANT PACKAGE BOUNDARY",
                                "coordinates": {"x": self.lon, "y": self.lat},
                                "geographies": {
                                    "States": [{"GEOID": "48", "STATE": "48"}],
                                    "Counties": [{"GEOID": "48439", "COUNTY": "439"}],
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


def expected_representatives(assignments: dict[str, str]) -> dict[str, str | None]:
    prefixes = {
        A_COMM: "office-us-tx-tarrant-county-commissioner-",
        A_JP: "office-us-tx-tarrant-county-jp-",
        A_CONST: "office-us-tx-tarrant-county-constable-",
    }
    return {
        adapter_id: holder_by_office[f"{prefixes[adapter_id]}{district_key}"]
        for adapter_id, district_key in assignments.items()
    }


def conflict_layers(payload: dict) -> set[str]:
    return {
        row.get("layer")
        for row in payload.get("coverage") or []
        if row.get("status") == "CONFLICT"
    }


commissioner_boundary = find_isolated_boundary(
    COMM_SERVICE, "District_N", JPC_SERVICE, "JP"
)
commissioner_exact = resolve_point(
    "tarrant-commissioner-boundary-exact", tuple(commissioner_boundary["midpoint"])
)
commissioner_exact_assignments = assignment_map(commissioner_exact)
if set(commissioner_exact_assignments) != {A_JP, A_CONST}:
    raise AssertionError(
        "Commissioner exact boundary must suppress only Commissioner and preserve JP/Constable: "
        f"{commissioner_exact_assignments}"
    )
if set(commissioner_exact_assignments.values()) != {commissioner_boundary["other_mid_key"]}:
    raise AssertionError("Commissioner exact boundary changed the isolated JP/Constable key")
if representative_map(commissioner_exact) != expected_representatives(commissioner_exact_assignments):
    raise AssertionError("Commissioner exact boundary representative join changed")
if len(applicable(commissioner_exact)) != 8:
    raise AssertionError("Commissioner exact boundary must preserve eight Tarrant offices")
if "tarrant_county_commissioner_precinct" not in conflict_layers(commissioner_exact):
    raise AssertionError("Commissioner exact boundary did not emit CONFLICT coverage")

commissioner_sides = []
for label, point, expected_commissioner in (
    ("side-a", commissioner_boundary["side_a"], commissioner_boundary["side_a_primary_key"]),
    ("side-b", commissioner_boundary["side_b"], commissioner_boundary["side_b_primary_key"]),
):
    payload = resolve_point(f"tarrant-commissioner-boundary-{label}", tuple(point))
    assignments = assignment_map(payload)
    expected = {
        A_COMM: expected_commissioner,
        A_JP: commissioner_boundary["other_mid_key"],
        A_CONST: commissioner_boundary["other_mid_key"],
    }
    if assignments != expected:
        raise AssertionError(f"Commissioner boundary {label} assignments changed: {assignments}")
    if representative_map(payload) != expected_representatives(assignments):
        raise AssertionError(f"Commissioner boundary {label} representative join changed")
    if len(applicable(payload)) != 9:
        raise AssertionError(f"Commissioner boundary {label} must restore nine offices")
    commissioner_sides.append({"side": label, "assignments": assignments, "status": "PASS"})

jpc_boundary = find_isolated_boundary(JPC_SERVICE, "JP", COMM_SERVICE, "District_N")
jpc_exact = resolve_point("tarrant-jpc-boundary-exact", tuple(jpc_boundary["midpoint"]))
jpc_exact_assignments = assignment_map(jpc_exact)
if set(jpc_exact_assignments) != {A_COMM}:
    raise AssertionError(
        f"JP/Constable exact boundary must preserve only Commissioner: {jpc_exact_assignments}"
    )
if jpc_exact_assignments[A_COMM] != jpc_boundary["other_mid_key"]:
    raise AssertionError("JP/Constable exact boundary changed the isolated Commissioner key")
if representative_map(jpc_exact) != expected_representatives(jpc_exact_assignments):
    raise AssertionError("JP/Constable exact boundary representative join changed")
if len(applicable(jpc_exact)) != 7:
    raise AssertionError("JP/Constable exact boundary must preserve seven Tarrant offices")
required_conflicts = {"tarrant_county_jp_precinct", "tarrant_county_constable_precinct"}
if not required_conflicts.issubset(conflict_layers(jpc_exact)):
    raise AssertionError("JP/Constable exact boundary did not emit both CONFLICT rows")

jpc_sides = []
for label, point, expected_jpc in (
    ("side-a", jpc_boundary["side_a"], jpc_boundary["side_a_primary_key"]),
    ("side-b", jpc_boundary["side_b"], jpc_boundary["side_b_primary_key"]),
):
    payload = resolve_point(f"tarrant-jpc-boundary-{label}", tuple(point))
    assignments = assignment_map(payload)
    expected = {
        A_COMM: jpc_boundary["other_mid_key"],
        A_JP: expected_jpc,
        A_CONST: expected_jpc,
    }
    if assignments != expected:
        raise AssertionError(f"JP/Constable boundary {label} assignments changed: {assignments}")
    if representative_map(payload) != expected_representatives(assignments):
        raise AssertionError(f"JP/Constable boundary {label} representative join changed")
    if len(applicable(payload)) != 9:
        raise AssertionError(f"JP/Constable boundary {label} must restore nine offices")
    jpc_sides.append({"side": label, "assignments": assignments, "status": "PASS"})

runtime_sha = hashlib.sha256(
    b"".join(part.read_bytes() for part in sorted((ROOT / "civic_gps_runtime_parts").glob("part.*")))
).hexdigest()
summary = {
    "status": "PASS",
    "gate": "CG-09",
    "county": "Tarrant County, TX",
    "geoid": "48439",
    "engine_version": "0.6.1",
    "registry_artifact_version": "0.5.5",
    "runtime_sha256": runtime_sha,
    "release_offices": 26,
    "release_holders": 26,
    "interior_controls": interior_summaries,
    "outside_negative": "PASS",
    "commissioner_boundary": {
        "midpoint": commissioner_boundary["midpoint"],
        "official_intersections": commissioner_boundary["primary_mid_keys"],
        "exact_assignments": commissioner_exact_assignments,
        "exact_applicable_offices": 8,
        "sides": commissioner_sides,
        "policy": POLICY,
    },
    "jp_constable_boundary": {
        "midpoint": jpc_boundary["midpoint"],
        "official_intersections": jpc_boundary["primary_mid_keys"],
        "exact_assignments": jpc_exact_assignments,
        "exact_applicable_offices": 7,
        "sides": jpc_sides,
        "policy": POLICY,
    },
    "actions": "NOT_YET_RELEASED",
    "candidate_packaged": True,
    "next_gate": "CG-10",
}
(OUTPUT / "packaged-tarrant-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("TARRANT PACKAGED CG-09 PASS")
