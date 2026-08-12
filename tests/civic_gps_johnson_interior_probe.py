#!/usr/bin/env python3
"""Johnson County CG-06 real interior-address proof; stop before outside negative."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zipfile import ZipFile

try:
    import requests
except ModuleNotFoundError:  # Local restricted sandboxes may lack the CI dependency.
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

        def get(self, url, params=None, timeout=None):
            if params:
                separator = "&" if urllib.parse.urlparse(url).query else "?"
                url = url + separator + urllib.parse.urlencode(params)
            request = urllib.request.Request(url, headers=self.headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return StandardLibraryResponse(response.read())
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                raise RequestException(str(exc)) from exc

    requests.RequestException = RequestException
    requests.Session = StandardLibrarySession
    sys.modules["requests"] = requests

from civic_gps_johnson_adapter_probe import (  # noqa: E402
    SERVICE,
    get_json,
    normalize_key,
    validate_adapter_contracts,
    validate_live_layer,
)
from civic_gps_johnson_roster_probe import (  # noqa: E402
    ADAPTERS,
    ONBOARDING_TOOL,
    POLICY,
    PRODUCTION_MAIN_COMMIT,
    PRODUCTION_MAIN_TREE,
    RUNTIME_PARTS,
    SPEC_PATH,
    validate_candidate,
    validate_production_runtime,
    write_json,
)


JURISDICTION = "jur-us-tx-johnson-county"
A_COMM = "DIST-TX-JOHNSON-COMMISSIONER"
A_JP = "DIST-TX-JOHNSON-JP"
A_CONST = "DIST-TX-JOHNSON-CONSTABLE"
EXPECTED_ADAPTERS = (A_COMM, A_JP, A_CONST)
EXPECTED_LAYERS = {
    "johnson_county_commissioner_precinct",
    "johnson_county_jp_precinct",
    "johnson_county_constable_precinct",
}
COUNTYWIDE_IDS = {
    "office-us-tx-johnson-county-judge",
    "office-us-tx-johnson-county-sheriff",
    "office-us-tx-johnson-county-clerk",
    "office-us-tx-johnson-county-district-clerk",
    "office-us-tx-johnson-county-tax-assessor-collector",
    "office-us-tx-johnson-county-treasurer",
}
EXPECTED_REPRESENTATIVES = {
    "1": {A_COMM: "Rick Bailey", A_JP: "DeeAnn Strother", A_CONST: "Matt Wylie"},
    "2": {A_COMM: "Kenny Howell", A_JP: "Jeff Monk", A_CONST: "Adam Crawford"},
    "3": {A_COMM: "Mike White", A_JP: "Andrew Nolan", A_CONST: "Steve Williams"},
    "4": {A_COMM: "Larry Woolley", A_JP: "Robert Shaw", A_CONST: "Troy Fuller"},
}
CASES = [
    {
        "id": "johnson-precinct1-candidate",
        "address": "3400 FM 1434, Cleburne, TX 76033",
        "key": "1",
    },
    {
        "id": "johnson-precinct2-candidate",
        "address": "3425 County Road 920, Crowley, TX 76036",
        "key": "2",
    },
    {
        "id": "johnson-precinct3-candidate",
        "address": "10420 East FM 917, Alvarado, TX 76009",
        "key": "3",
    },
    {
        "id": "johnson-precinct4-candidate",
        "address": "4300 East FM 4, Cleburne, TX 76031",
        "key": "4",
    },
]
CENSUS_PREFIX = "https://geocoding.geo.census.gov/geocoder/"
CENSUS_URL = CENSUS_PREFIX + "geographies/onelineaddress"
SERVICE_QUERY = SERVICE.rstrip("/") + "/query"


def load_module(name: str, path: Path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    return module


class CountingSession:
    def __init__(self):
        self.real = requests.Session()
        self.real.headers.update(
            {"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"}
        )
        self.geocoder_calls = 0
        self.exact_point_intersection_calls = 0
        self.distance_probe_calls = 0
        self.unexpected_calls: list[str] = []

    def get(self, url, params=None, timeout=None):
        if url.startswith(CENSUS_PREFIX):
            self.geocoder_calls += 1
        elif url == SERVICE_QUERY:
            if not params or params.get("geometryType") != "esriGeometryPoint":
                self.unexpected_calls.append(url)
            elif "distance" in params or "units" in params:
                if params.get("distance") == "1" and params.get("units") == "esriSRUnit_Meter":
                    self.distance_probe_calls += 1
                else:
                    self.unexpected_calls.append(url)
            else:
                self.exact_point_intersection_calls += 1
            if params and params.get("inSR") != "4326":
                self.unexpected_calls.append(url)
        else:
            self.unexpected_calls.append(url)
        return self.real.get(url, params=params, timeout=timeout)


def assignment_map(payload: dict) -> dict[str, str]:
    return {
        row["adapter_id"]: str(row["district_key"])
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == JURISDICTION
    }


def representative_map(payload: dict) -> dict[str, str | None]:
    return {
        row["adapter_id"]: row.get("representative")
        for row in payload.get("district_assignments") or []
        if row.get("jurisdiction_id") == JURISDICTION
    }


def validate_frozen_cases(spec: dict) -> None:
    actual = [
        {"id": row.get("id"), "address": row.get("address")}
        for row in spec.get("controls", {}).get("interiors") or []
    ]
    expected = [{"id": row["id"], "address": row["address"]} for row in CASES]
    if actual != expected:
        raise AssertionError(f"Johnson frozen interior controls changed: {actual} != {expected}")


def validate_direct_control_candidates(registry: dict) -> list[dict]:
    geocoder = registry.get("geocoder") or {}
    if geocoder.get("url") != CENSUS_URL:
        raise AssertionError(f"Johnson CG-06 geocoder contract changed: {geocoder}")
    evidence = []
    for case in CASES:
        params = {
            "address": case["address"],
            "benchmark": geocoder["benchmark"],
            "vintage": geocoder["vintage"],
            "format": "json",
        }
        if geocoder.get("layers"):
            params["layers"] = ",".join(geocoder["layers"])
        geocoder_body = get_json(CENSUS_URL, params)
        matches = geocoder_body.get("result", {}).get("addressMatches") or []
        if len(matches) != 1:
            raise AssertionError(f"[{case['id']}] expected one Census address match, got {len(matches)}")
        match = matches[0]
        counties = match.get("geographies", {}).get("Counties") or []
        if [row.get("GEOID") for row in counties] != ["48251"]:
            raise AssertionError(f"[{case['id']}] Census county match changed: {counties}")
        coordinates = match.get("coordinates") or {}
        point = f"{float(coordinates['x'])},{float(coordinates['y'])}"
        exact_body = get_json(
            SERVICE_QUERY,
            {
                "where": "1=1",
                "geometry": point,
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "ID",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        keys = sorted(
            {
                normalize_key((row.get("attributes") or {}).get("ID"))
                for row in exact_body.get("features") or []
            },
            key=int,
        )
        if keys != [case["key"]]:
            raise AssertionError(f"[{case['id']}] direct official-layer key changed: {keys}")
        evidence.append(
            {
                "address": case["address"],
                "case": case["id"],
                "county_geoid": "48251",
                "exact_key": case["key"],
                "matched_address": match.get("matchedAddress"),
                "status": "DIRECT_SOURCE_CHECK_PASS",
            }
        )
    return evidence


def validate_interior(case: dict, payload: dict) -> tuple[dict[str, str], dict[str, str | None]]:
    label = case["id"]
    key = case["key"]
    if JURISDICTION not in {
        row.get("jurisdiction_id") for row in payload.get("jurisdictions") or []
    }:
        raise AssertionError(f"[{label}] Johnson jurisdiction did not activate")

    assignments = assignment_map(payload)
    expected_assignments = {adapter_id: key for adapter_id in EXPECTED_ADAPTERS}
    if assignments != expected_assignments:
        raise AssertionError(f"[{label}] expected {expected_assignments}, got {assignments}")
    representatives = representative_map(payload)
    if representatives != EXPECTED_REPRESENTATIVES[key]:
        raise AssertionError(f"[{label}] canonical representative join changed: {representatives}")

    applicable = [
        row
        for row in payload.get("applicable_offices") or []
        if row.get("jurisdiction_id") == JURISDICTION
    ]
    wide = [row for row in applicable if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in applicable if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(applicable), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(
            f"[{label}] expected 9 = 6 wide + 3 district, got "
            f"{len(applicable)} = {len(wide)} + {len(district)}"
        )
    if {row.get("office_id") for row in wide} != COUNTYWIDE_IDS:
        raise AssertionError(f"[{label}] bounded countywide office set changed")
    expected_district_ids = {
        f"office-us-tx-johnson-county-commissioner-{key}",
        f"office-us-tx-johnson-county-jp-{key}",
        f"office-us-tx-johnson-county-constable-{key}",
    }
    if {row.get("office_id") for row in district} != expected_district_ids:
        raise AssertionError(f"[{label}] district office set changed")

    release_layers = {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "RELEASE_BACKED"
        and str(row.get("layer") or "").startswith("johnson_county_")
    }
    if release_layers != EXPECTED_LAYERS:
        raise AssertionError(f"[{label}] Johnson release-backed coverage changed: {release_layers}")
    action_coverage = [
        row for row in payload.get("coverage") or [] if row.get("layer") == "johnson_action_endpoints"
    ]
    if len(action_coverage) != 1 or action_coverage[0].get("status") != "NOT_YET_RELEASED":
        raise AssertionError(f"[{label}] Johnson action coverage gap changed: {action_coverage}")
    if any(
        row.get("jurisdiction_id") == JURISDICTION for row in payload.get("action_links") or []
    ):
        raise AssertionError(f"[{label}] Johnson actions must remain unreleased")
    return assignments, representatives


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    validate_frozen_cases(spec)
    onboarding = output / "onboarding"
    import subprocess

    subprocess.run(
        [
            sys.executable,
            str(ONBOARDING_TOOL),
            str(SPEC_PATH),
            "--output-dir",
            str(onboarding),
            "--expect",
            "SUPPORTED_V0_1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report, release, bundle = validate_candidate(onboarding)
    runtime = validate_production_runtime()
    live_layer = validate_live_layer()
    adapter_evidence = validate_adapter_contracts(bundle)
    if set(ADAPTERS) != set(EXPECTED_ADAPTERS):
        raise AssertionError(f"Johnson adapter prerequisite changed: {sorted(ADAPTERS)}")

    runtime_bytes = b"".join(part.read_bytes() for part in sorted(RUNTIME_PARTS.glob("part.*")))
    if hashlib.sha256(runtime_bytes).hexdigest() != runtime["runtime_sha256"]:
        raise AssertionError("Johnson production runtime changed after prerequisite validation")

    direct_candidates = []
    engine_blocker = {}
    with tempfile.TemporaryDirectory(prefix="civic-gps-johnson-cg06-") as temp_name:
        temp_root = Path(temp_name)
        with ZipFile(io.BytesIO(runtime_bytes)) as runtime_archive:
            runtime_archive.extractall(temp_root)
        runtime_gps = temp_root / "civic_gps"
        engine_mod = load_module("civic_gps_engine_johnson_cg06", runtime_gps / "engine.py")
        registry = json.loads((runtime_gps / "registry.json").read_text(encoding="utf-8"))
        if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.6.0":
            raise AssertionError(f"Johnson CG-06 production registry changed: {registry}")
        if any(
            row.get("adapter_id") == "ADAPTER-TX-JOHNSON" for row in registry.get("bundles") or []
        ):
            raise AssertionError("Johnson must not already exist in the packaged production registry")
        active_registry = copy.deepcopy(registry)
        active_registry["bundles"].append(bundle)
        release_name = spec["county"]["release_filename"]
        write_json(runtime_gps / release_name, release)
        direct_candidates = validate_direct_control_candidates(active_registry)
        session = CountingSession()
        resolver = engine_mod.CivicGPSOverlayEngine(
            active_registry,
            registry_root=runtime_gps,
            session=session,
            timeout_seconds=45.0,
        )
        attempted_case = CASES[0]
        result = resolver.resolve(
            attempted_case["address"], observed_on=spec["county"]["observed_on"]
        )
        write_json(output / "johnson-cg06-engine-blocker.json", result)
        if "error" not in result:
            raise AssertionError(
                "Johnson one-meter topology compatibility changed; replace the blocker proof with full CG-06 controls"
            )
        error = result["error"]
        api_error = (error.get("details") or {}).get("api_error") or {}
        api_details = " ".join(str(row) for row in api_error.get("details") or [])
        expected_marker = "24204: The spatial reference identifier (SRID) is not valid."
        if (
            error.get("code") != "UPSTREAM_API_ERROR"
            or api_error.get("code") != 400
            or expected_marker not in api_details
        ):
            raise AssertionError(f"Johnson CG-06 failed for an unexpected reason: {error}")
        if (
            session.geocoder_calls,
            session.exact_point_intersection_calls,
            session.distance_probe_calls,
        ) != (1, 1, 1):
            raise AssertionError(
                "Johnson CG-06 blocker must occur after one geocoder, one exact point query, "
                f"and one one-meter probe: {session.__dict__}"
            )
        if session.unexpected_calls:
            raise AssertionError(f"Johnson CG-06 crossed its network scope: {session.unexpected_calls}")
        engine_blocker = {
            "adapter_id": A_COMM,
            "address": attempted_case["address"],
            "case": attempted_case["id"],
            "distance_probe_meters": 1,
            "engine_error_code": error["code"],
            "official_service_error_code": api_error["code"],
            "reason": "OFFICIAL_LAYER_REJECTS_WGS84_DISTANCE_QUERY_SRID",
            "service_url": SERVICE,
            "status": "REPRODUCED",
        }

    summary = {
        "status": "BLOCKED",
        "county": "Johnson County, TX",
        "geoid": "48251",
        "gates": {"CG-06": "BLOCKED"},
        "prerequisite_gates": {"CG-04": "PASS", "CG-05": "PASS"},
        "fit_result": report["result"],
        "live_layer": {
            "field": live_layer["field"],
            "field_type": live_layer["field_type"],
            "keys": live_layer["keys"],
            "service_url": live_layer["service_url"],
            "status": live_layer["status"],
        },
        "adapter_count": len(adapter_evidence),
        "direct_control_candidates": direct_candidates,
        "direct_control_candidates_verified": 4,
        "engine_blocker": engine_blocker,
        "interior_controls_attempted": 1,
        "interior_controls_passed": 0,
        "outside_negative_controls_run": 0,
        "boundary_controls_run": 0,
        "actions": "NOT_YET_RELEASED",
        "scope": "BOUNDED_V0_1_SCOPE",
        "adapter_failure_scope": "ADAPTER",
        "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
        "boundary_policy": POLICY,
        "stop_class": "ARCHITECTURE_CHANGE_REQUIRED",
        "architecture_change": "GENERIC_HARDENING",
        "candidate_packaged": False,
        "production_main_commit": PRODUCTION_MAIN_COMMIT,
        "production_main_tree": PRODUCTION_MAIN_TREE,
        **runtime,
        "production_runtime_changed": False,
        "next_gate": None,
        "stopped_before": "CG-07",
    }
    write_json(output / "johnson-cg06-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("JOHNSON CG-06 BLOCKED BEFORE CG-07: GENERIC TOPOLOGY HARDENING REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
