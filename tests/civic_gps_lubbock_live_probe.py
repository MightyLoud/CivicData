#!/usr/bin/env python3
"""Lubbock County production proof for the protected CG-10 release."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zipfile import ZipFile

try:
    import requests
except ModuleNotFoundError:  # Local restricted sandboxes may lack the CI-installed dependency.
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class StandardLibraryResponse:
        def __init__(self, body: bytes):
            self._body = body

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return json.loads(self._body)

    class StandardLibrarySession:
        def __init__(self):
            self.headers: dict[str, str] = {}

        def get(self, url, params=None, timeout=None, headers=None):
            if params:
                separator = "&" if urllib.parse.urlparse(url).query else "?"
                url = url + separator + urllib.parse.urlencode(params)
            request = urllib.request.Request(url, headers=headers or self.headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return StandardLibraryResponse(response.read())
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                raise RequestException(str(exc)) from exc

    requests.RequestException = RequestException
    requests.Session = StandardLibrarySession
    requests.get = StandardLibrarySession().get
    sys.modules["requests"] = requests


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PARTS = ROOT / "civic_gps_runtime_parts"
RELEASE_RUNTIME_SHA256 = "cd8a5807fdeb7ca0253885ec8192cf3468c8b0c29a4c099ba78c0707c9818d1a"
EXPECTED_REGISTRY_VERSION = os.environ.get("CIVIC_GPS_EXPECTED_REGISTRY_VERSION", "0.6.1")
EXPECTED_BUNDLE_COUNT = int(os.environ.get("CIVIC_GPS_EXPECTED_BUNDLE_COUNT", "14"))
SERVICE = "https://gisserver.halff.com/ags/rest/services/Lubbock_CO/Reference_Layers/MapServer/0"
FIELD = "District_ID"
J = "jur-us-tx-lubbock-county"
TRAVIS = "jur-us-tx-travis-county"
A_COMM = "DIST-TX-LUBBOCK-COMMISSIONER"
A_JP = "DIST-TX-LUBBOCK-JP"
A_CONST = "DIST-TX-LUBBOCK-CONSTABLE"
ADAPTERS = (A_COMM, A_JP, A_CONST)
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
EXPECTED_LAYERS = {
    "lubbock_county_commissioner_precinct",
    "lubbock_county_jp_precinct",
    "lubbock_county_constable_precinct",
}
CASES = [
    ("lubbock-p1", (-101.97072351, 33.46755612), "1"),
    ("lubbock-p2", (-101.69540989, 33.49819024), "2"),
    ("lubbock-p3", (-101.73045843, 33.69671576), "3"),
    ("lubbock-p4", (-101.97199855, 33.69565520), "4"),
]
BOUNDARY = {
    "midpoint": (-102.01777335295748, 33.561425140143754),
    "exact": ["1"],
    "nearby": ["1", "4"],
    "side_a": (-102.01777337950007, 33.56144514012614),
    "side_a_key": "4",
    "side_b": (-102.01777332641488, 33.56140514016137),
    "side_b_key": "1",
}
TRAVIS_POINT = (-97.6910527, 30.2395263)
TRANSIENT_MARKERS = ("timed out", "timeout", "connection", "temporarily unavailable", "502", "503", "504")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def normalize_key(raw: object) -> str:
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


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
    return [row for row in payload.get("applicable_offices") or [] if row.get("jurisdiction_id") == J]


def conflict_layers(payload: dict) -> set[str]:
    return {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "CONFLICT" and str(row.get("layer") or "").startswith("lubbock_county_")
    }


def assert_no_actions(label: str, payload: dict) -> None:
    rows = [row for row in payload.get("action_links") or [] if row.get("jurisdiction_id") == J]
    if rows:
        raise AssertionError(f"[{label}] Lubbock actions must remain unreleased: {rows}")


def get_json(url: str, params: dict) -> dict:
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=30,
                headers={"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"},
            )
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
            return body
        except requests.RequestException as exc:
            last = exc
            if attempt < 3 and any(marker in str(exc).lower() for marker in TRANSIENT_MARKERS):
                time.sleep(2**attempt)
                continue
            raise
    raise AssertionError(f"Unreachable ArcGIS retry state: {last}")


def point_keys(point: tuple[float, float], *, distance_meters: int | None = None) -> list[str]:
    params = {
        "where": "1=1",
        "geometry": f"{point[0]:.12f},{point[1]:.12f}",
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
    body = get_json(SERVICE.rstrip("/") + "/query", params)
    return sorted(
        {
            normalize_key((feature.get("attributes") or {}).get(FIELD))
            for feature in body.get("features") or []
            if (feature.get("attributes") or {}).get(FIELD) not in (None, "")
        },
        key=int,
    )


class FakeResponse:
    def __init__(self, body: dict):
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FixedPointSession:
    def __init__(
        self,
        point: tuple[float, float],
        county_geoid: str,
        *,
        lubbock_exact: list[str] | None = None,
        lubbock_probe: list[str] | None = None,
    ):
        self.point = point
        self.county_geoid = county_geoid
        self.lubbock_exact = lubbock_exact or []
        self.lubbock_probe = lubbock_probe or self.lubbock_exact
        self.real = requests.Session()
        self.real.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})

    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse(
                {
                    "result": {
                        "addressMatches": [
                            {
                                "matchedAddress": "PUBLIC FIXED COORDINATE CONTROL",
                                "coordinates": {"x": self.point[0], "y": self.point[1]},
                                "geographies": {
                                    "States": [{"GEOID": "48", "STATE": "48"}],
                                    "Counties": [{"GEOID": self.county_geoid, "COUNTY": self.county_geoid[-3:]}],
                                },
                            }
                        ]
                    }
                }
            )
        if url.startswith(SERVICE.rstrip("/") + "/query"):
            keys = self.lubbock_probe if params and params.get("distance") else self.lubbock_exact
            return FakeResponse({"features": [{"attributes": {FIELD: key}} for key in keys]})
        if "gis.traviscountytx.gov" in url:
            key = "3" if "/MapServer/0/query" in url else "5"
            return FakeResponse({"features": [{"attributes": {"PRECINCT": key}}]})
        return self.real.get(url, params=params, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/civic-gps-lubbock-cg10")
    parser.add_argument("--expected-runtime-sha256", default=RELEASE_RUNTIME_SHA256)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    runtime_bytes = b"".join(part.read_bytes() for part in sorted(RUNTIME_PARTS.glob("part.*")))
    runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
    if runtime_sha != args.expected_runtime_sha256:
        raise AssertionError(f"Lubbock CG-10 runtime SHA changed: {runtime_sha}")
    if EXPECTED_REGISTRY_VERSION == "0.6.1" and runtime_sha != RELEASE_RUNTIME_SHA256:
        raise AssertionError(f"Lubbock v0.6.1 release runtime SHA changed: {runtime_sha}")

    with ZipFile(io.BytesIO(runtime_bytes)) as archive:
        names = archive.namelist()
        registry = json.loads(archive.read("civic_gps/registry.json"))
        release = json.loads(archive.read("civic_gps/civic_gps_lubbock_county_v0.1.json"))
        engine_bytes = archive.read("civic_gps/engine.py")
    if len(names) != 22 or len(names) != len(set(names)):
        raise AssertionError(f"Expected 22 unique runtime entries, got {len(names)}")
    if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != EXPECTED_REGISTRY_VERSION:
        raise AssertionError(
            f"Lubbock release requires engine 0.6.2 / registry {EXPECTED_REGISTRY_VERSION}"
        )
    if len(registry.get("bundles") or []) != EXPECTED_BUNDLE_COUNT:
        raise AssertionError("Lubbock release requires exactly 14 registry bundles")
    registry_copy = copy.deepcopy(registry)
    recorded_registry_sha = registry_copy.pop("canonical_content_sha256", None)
    if recorded_registry_sha != canonical_sha(registry_copy):
        raise AssertionError("Lubbock registry canonical SHA mismatch")
    bundle = next((row for row in registry.get("bundles") or [] if row.get("adapter_id") == "ADAPTER-TX-LUBBOCK"), None)
    if not bundle or bundle.get("release_files") != ["civic_gps_lubbock_county_v0.1.json"]:
        raise AssertionError("Packaged registry is missing the exact Lubbock release bundle")
    if bundle.get("action_registry_files"):
        raise AssertionError("Lubbock action routing must remain absent")
    if {row.get("adapter_id") for row in bundle.get("district_adapters") or []} != set(ADAPTERS):
        raise AssertionError("Lubbock district-adapter set changed")
    for adapter in bundle["district_adapters"]:
        if (
            adapter.get("failure_scope") != "ADAPTER"
            or adapter.get("boundary_policy") != POLICY
            or adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY"
            or adapter.get("source_status") != "LIVE_INTERIOR_NEGATIVE_BOUNDARY_PASS"
        ):
            raise AssertionError(f"Lubbock adapter contract changed: {adapter}")

    release_copy = copy.deepcopy(release)
    recorded_release_sha = release_copy["meta"].pop("canonical_content_sha256", None)
    if recorded_release_sha != canonical_sha(release_copy):
        raise AssertionError("Lubbock canonical release SHA mismatch")
    offices = release.get("payload", {}).get("offices") or []
    holders = release.get("payload", {}).get("officeholders") or []
    office_ids = {row.get("office_id") for row in offices}
    holder_ids = {row.get("office_id") for row in holders}
    if len(offices) != 18 or len(holders) != 18 or len(office_ids) != 18 or office_ids != holder_ids:
        raise AssertionError("Lubbock release must contain 18 unique offices with 18 complete holder joins")

    engine_path = args.output_dir / "_engine.py"
    engine_path.write_bytes(engine_bytes)
    engine_mod = load_module("civic_gps_engine_lubbock_cg10", engine_path)
    required_runtime_artifacts = {
        name
        for row in registry.get("bundles") or []
        for name in (row.get("release_files") or []) + (row.get("action_registry_files") or [])
    }
    with ZipFile(io.BytesIO(runtime_bytes)) as archive:
        archived_by_name = {Path(name).name: name for name in archive.namelist()}
        for artifact_name in required_runtime_artifacts:
            archived_name = archived_by_name.get(artifact_name)
            if not archived_name:
                raise AssertionError(f"Runtime is missing configured artifact: {artifact_name}")
            (args.output_dir / artifact_name).write_bytes(archive.read(archived_name))

    def resolve_point(
        label: str,
        point: tuple[float, float],
        county_geoid: str = "48303",
        *,
        exact_keys: list[str] | None = None,
        probe_keys: list[str] | None = None,
    ) -> dict:
        resolver = engine_mod.CivicGPSOverlayEngine(
            registry,
            registry_root=args.output_dir,
            session=FixedPointSession(
                point,
                county_geoid,
                lubbock_exact=exact_keys,
                lubbock_probe=probe_keys,
            ),
            timeout_seconds=45.0,
        )
        result = resolver.resolve(label, observed_on="2026-08-12")
        if "error" in result:
            raise AssertionError(f"[{label}] engine error: {result['error']}")
        write_json(args.output_dir / f"{label}.json", result)
        return result["payload"]

    expected_reps = {
        "1": {A_COMM: "Mike Dalby", A_JP: "Betty Dills", A_CONST: "Paul Hanna"},
        "2": {A_COMM: "Jason Corley", A_JP: "Susan Rowley", A_CONST: "Jody Barnes"},
        "3": {A_COMM: "Cary Shaw", A_JP: "Francisco Gutierrez", A_CONST: "Jose A. Sanchez"},
        "4": {A_COMM: "Jordan Rackler", A_JP: "Lance Cansino", A_CONST: "Joe Pinson"},
    }
    interior = []
    for label, point, key in CASES:
        if point_keys(point) != [key] or point_keys(point, distance_meters=1) != [key]:
            raise AssertionError(f"[{label}] official live precinct control changed")
        payload = resolve_point(label, point, exact_keys=[key], probe_keys=[key])
        assignments = assignment_map(payload)
        expected = {adapter_id: key for adapter_id in ADAPTERS}
        if assignments != expected or representative_map(payload) != expected_reps[key]:
            raise AssertionError(f"[{label}] Lubbock assignment/representative join changed")
        rows = applicable(payload)
        if len(rows) != 9 or len([row for row in rows if row.get("applicability_scope") == "JURISDICTION_WIDE"]) != 6:
            raise AssertionError(f"[{label}] expected 9 applicable Lubbock offices")
        if conflict_layers(payload):
            raise AssertionError(f"[{label}] normal interior reported a boundary conflict")
        assert_no_actions(label, payload)
        interior.append({"case": label, "key": key, "assignments": assignments, "status": "PASS"})

    outside = resolve_point("lubbock-outside-austin", TRAVIS_POINT, "48453")
    outside_jurisdictions = {row.get("jurisdiction_id") for row in outside.get("jurisdictions") or []}
    if J in outside_jurisdictions or TRAVIS not in outside_jurisdictions:
        raise AssertionError(f"Outside control failed jurisdiction isolation: {outside_jurisdictions}")
    if any(
        row.get("jurisdiction_id") == J
        for row in (outside.get("district_assignments") or [])
        + (outside.get("applicable_offices") or [])
        + (outside.get("action_links") or [])
    ):
        raise AssertionError("Outside control leaked Lubbock assignments/offices/actions")
    if any("lubbock" in json.dumps(row, sort_keys=True).lower() for row in outside.get("coverage") or []):
        raise AssertionError("Outside control leaked Lubbock coverage")

    if point_keys(BOUNDARY["midpoint"]) != BOUNDARY["exact"]:
        raise AssertionError("Lubbock exact-boundary service result changed")
    if point_keys(BOUNDARY["midpoint"], distance_meters=1) != BOUNDARY["nearby"]:
        raise AssertionError("Lubbock one-meter boundary topology changed")
    exact = resolve_point(
        "lubbock-shared-boundary-exact",
        BOUNDARY["midpoint"],
        exact_keys=BOUNDARY["exact"],
        probe_keys=BOUNDARY["nearby"],
    )
    if assignment_map(exact) or representative_map(exact) or len(applicable(exact)) != 6:
        raise AssertionError("Exact shared boundary must suppress all district assignments and preserve six countywide offices")
    if conflict_layers(exact) != EXPECTED_LAYERS:
        raise AssertionError(f"Exact shared boundary conflict layers changed: {conflict_layers(exact)}")
    assert_no_actions("shared-boundary-exact", exact)

    boundary_sides = []
    for side in ("side_a", "side_b"):
        key = BOUNDARY[f"{side}_key"]
        point = BOUNDARY[side]
        if point_keys(point, distance_meters=1) != [key]:
            raise AssertionError(f"Lubbock {side} live topology changed")
        payload = resolve_point(
            f"lubbock-shared-boundary-{side.replace('_', '-')}",
            point,
            exact_keys=[key],
            probe_keys=[key],
        )
        expected = {adapter_id: key for adapter_id in ADAPTERS}
        if assignment_map(payload) != expected or representative_map(payload) != expected_reps[key]:
            raise AssertionError(f"Lubbock {side} assignment/representative join changed")
        if len(applicable(payload)) != 9 or conflict_layers(payload):
            raise AssertionError(f"Lubbock {side} did not restore all district offices")
        assert_no_actions(side, payload)
        boundary_sides.append({"side": side, "key": key, "status": "PASS"})

    summary = {
        "status": "PASS",
        "county": "Lubbock County, TX",
        "geoid": "48303",
        "gates": {"CG-10": "PASS"},
        "engine_version": "0.6.2",
        "registry_artifact_version": EXPECTED_REGISTRY_VERSION,
        "bundle_count": EXPECTED_BUNDLE_COUNT,
        "runtime_sha256": runtime_sha,
        "release_offices": 18,
        "release_holders": 18,
        "interior_controls": interior,
        "outside_negative": {"status": "PASS", "lubbock_leakage": 0, "control_jurisdiction": "Travis County"},
        "shared_boundary": {
            "status": "PASS",
            "midpoint": list(BOUNDARY["midpoint"]),
            "exact_service_keys": BOUNDARY["exact"],
            "topology_nearby_keys": BOUNDARY["nearby"],
            "exact_assignments": {},
            "exact_applicable_offices": 6,
            "conflict_layers": sorted(conflict_layers(exact)),
            "sides": boundary_sides,
            "distance_probe_meters": 1,
            "policy": POLICY,
        },
        "actions": "NOT_YET_RELEASED",
        "production_runtime_changed": True,
        "release_packaged": True,
    }
    write_json(args.output_dir / "lubbock-cg10-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("LUBBOCK CG-10 RELEASE PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
