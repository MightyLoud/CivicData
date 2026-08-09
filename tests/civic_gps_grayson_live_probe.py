#!/usr/bin/env python3
"""Grayson County CG-04 through CG-08 live proof on the unchanged v0.6.2 runtime."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import math
import subprocess
import sys
import tempfile
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


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "tests/fixtures/civic_gps_county_onboarding/grayson_county10_candidate_v0.1.json"
ONBOARDING_TOOL = ROOT / "tools/civic_gps_county_onboarding.py"
RUNTIME_PARTS = ROOT / "civic_gps_runtime_parts"
RUNTIME_SHA256 = "49b54af31cb4687936a2dddb6a91f6305aa7b4977756a3db203562971296a23a"
J = "jur-us-tx-grayson-county"
TRAVIS = "jur-us-tx-travis-county"
A_COMM = "DIST-TX-GRAYSON-COMMISSIONER"
A_JP = "DIST-TX-GRAYSON-JP"
A_CONST = "DIST-TX-GRAYSON-CONSTABLE"
ADAPTERS = (A_COMM, A_JP, A_CONST)
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
COMM_SERVICE = "https://maps.co.grayson.tx.us/arcgis/rest/services/Grayson/Grayson_County_Public_Interactive_Map/MapServer/15"
JPC_SERVICE = "https://maps.co.grayson.tx.us/arcgis/rest/services/Grayson/Grayson_County_Public_Interactive_Map/MapServer/13"
COMM_FIELD = "COMMISSIONER"
JPC_FIELD = "JP_NAME"
EXPECTED_LAYERS = {
    A_COMM: "grayson_county_commissioner_precinct",
    A_JP: "grayson_county_jp_precinct",
    A_CONST: "grayson_county_constable_precinct",
}
COUNTYWIDE_IDS = {
    "office-us-tx-grayson-county-judge",
    "office-us-tx-grayson-county-sheriff",
    "office-us-tx-grayson-county-clerk",
    "office-us-tx-grayson-county-district-clerk",
    "office-us-tx-grayson-county-tax-assessor-collector",
    "office-us-tx-grayson-county-treasurer",
}
EXPECTED_ROSTER = {
    "office-us-tx-grayson-county-judge": "Bruce Dawsey",
    "office-us-tx-grayson-county-sheriff": "Tony Bennie",
    "office-us-tx-grayson-county-clerk": "Deana Patterson",
    "office-us-tx-grayson-county-district-clerk": "Kelly Ashmore",
    "office-us-tx-grayson-county-tax-assessor-collector": "Bruce Stidham",
    "office-us-tx-grayson-county-treasurer": "Gayla Hawkins",
    "office-us-tx-grayson-county-commissioner-1": "Josh Marr",
    "office-us-tx-grayson-county-commissioner-2": "Art Arthur",
    "office-us-tx-grayson-county-commissioner-3": "Lindsay Wright",
    "office-us-tx-grayson-county-commissioner-4": "Matt Hardenburg",
    "office-us-tx-grayson-county-jp-1": "Ginny Hampton",
    "office-us-tx-grayson-county-jp-2": "Dennis Michael",
    "office-us-tx-grayson-county-jp-3": "Damon Vannoy",
    "office-us-tx-grayson-county-jp-4": "Christina Fox",
    "office-us-tx-grayson-county-constable-1": "Tommy Carter",
    "office-us-tx-grayson-county-constable-2": "Cody Putman",
    "office-us-tx-grayson-county-constable-3": "Todd Booher",
    "office-us-tx-grayson-county-constable-4": "William R. (Bob) Douglas",
}
EXPECTED_REPRESENTATIVES = {
    A_COMM: {"1": "Josh Marr", "2": "Art Arthur", "3": "Lindsay Wright", "4": "Matt Hardenburg"},
    A_JP: {"1": "Ginny Hampton", "2": "Dennis Michael", "3": "Damon Vannoy", "4": "Christina Fox"},
    A_CONST: {"1": "Tommy Carter", "2": "Cody Putman", "3": "Todd Booher", "4": "William R. (Bob) Douglas"},
}
CASES = [
    {
        "id": "grayson-jp1",
        "address": "100 W Houston Street, Suite 27, Sherman, TX 75090",
        "jp_key": "1",
    },
    {
        "id": "grayson-jp2",
        "address": "101 W Woodard Street, Denison, TX 75021",
        "jp_key": "2",
    },
    {
        "id": "grayson-jp3",
        "address": "509 N Union Street, Whitesboro, TX 76273",
        "jp_key": "3",
    },
    {
        "id": "grayson-jp4",
        "address": "117 S Main Street, Van Alstyne, TX 75495",
        "jp_key": "4",
    },
]
TRANSIENT_NETWORK_MARKERS = (
    "timed out", "timeout", "connection", "temporarily unavailable", "remote disconnected", "502", "503", "504"
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


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


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


def assert_no_actions(label: str, payload: dict) -> None:
    actions = [row for row in payload.get("action_links") or [] if row.get("jurisdiction_id") == J]
    if actions:
        raise AssertionError(f"[{label}] Grayson action routing must remain unreleased: {actions}")


def conflict_layers(payload: dict) -> set[str]:
    return {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "CONFLICT" and str(row.get("layer") or "").startswith("grayson_county_")
    }


def transient_upstream(error: dict) -> bool:
    details = error.get("details") or {}
    url = str(details.get("url") or "")
    upstream = str(details.get("error") or "").lower()
    supported_upstream = url.startswith("https://geocoding.geo.census.gov/geocoder/") or url.startswith(
        "https://maps.co.grayson.tx.us/arcgis/rest/services/Grayson/"
    )
    return (
        error.get("code") == "UPSTREAM_REQUEST_FAILED"
        and supported_upstream
        and any(marker in upstream for marker in TRANSIENT_NETWORK_MARKERS)
    )


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})


def get_json(url: str, params: dict) -> dict:
    for attempt in range(1, 4):
        try:
            response = SESSION.get(url, params=params, timeout=45)
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
            return body
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt - 1))
    raise AssertionError(f"Unreachable ArcGIS retry state for {url}")


def normalize_key(raw: object) -> str:
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def service_keys(service: str, field: str) -> list[str]:
    body = get_json(
        service.rstrip("/") + "/query",
        {"where": "1=1", "outFields": field, "returnGeometry": "false", "f": "json"},
    )
    return sorted(
        {
            normalize_key((feature.get("attributes") or {}).get(field))
            for feature in body.get("features") or []
        },
        key=int,
    )


def point_keys(
    service: str,
    field: str,
    point: tuple[float, float],
    *,
    distance_meters: int | None = None,
) -> list[str]:
    params = {
        "where": "1=1",
        "geometry": f"{point[0]:.12f},{point[1]:.12f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": field,
        "returnGeometry": "false",
        "f": "json",
    }
    if distance_meters is not None:
        params["distance"] = str(distance_meters)
        params["units"] = "esriSRUnit_Meter"
    body = get_json(service.rstrip("/") + "/query", params)
    return sorted(
        {
            normalize_key((feature.get("attributes") or {}).get(field))
            for feature in body.get("features") or []
            if (feature.get("attributes") or {}).get(field) not in (None, "")
        },
        key=int,
    )


def service_features(service: str, field: str) -> list[dict]:
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
    keys = {
        normalize_key((feature.get("attributes") or {}).get(field))
        for feature in features
    }
    if keys != {"1", "2", "3", "4"}:
        raise AssertionError(f"Live {field} geometry key set changed: {sorted(keys)}")
    return features


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
    primary: tuple[str, str],
    other: tuple[str, str],
) -> dict:
    service, field = primary
    candidates = []
    for rows in segment_index(service_features(service, field), field).values():
        shared_keys = sorted({row[0] for row in rows}, key=int)
        if len(shared_keys) != 2:
            continue
        a, b = rows[0][1], rows[0][2]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        candidates.append((length, shared_keys, a, b))
    candidates.sort(
        key=lambda row: (-row[0], row[1], rounded_point(row[2]), rounded_point(row[3]))
    )
    for _, shared_keys, a, b in candidates:
        midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        exact_keys = point_keys(service, field, midpoint)
        nearby_keys = point_keys(service, field, midpoint, distance_meters=1)
        other_keys = point_keys(*other, midpoint, distance_meters=1)
        if (
            len(exact_keys) != 1
            or len(nearby_keys) != 2
            or exact_keys[0] not in nearby_keys
            or set(nearby_keys) != set(shared_keys)
            or len(other_keys) != 1
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
            side_a_keys = point_keys(service, field, side_a, distance_meters=1)
            side_b_keys = point_keys(service, field, side_b, distance_meters=1)
            if (
                len(side_a_keys) == 1
                and len(side_b_keys) == 1
                and side_a_keys[0] != side_b_keys[0]
                and {side_a_keys[0], side_b_keys[0]} == set(nearby_keys)
                and point_keys(*other, side_a, distance_meters=1) == other_keys
                and point_keys(*other, side_b, distance_meters=1) == other_keys
            ):
                return {
                    "midpoint": midpoint,
                    "exact": exact_keys,
                    "nearby": nearby_keys,
                    "other": other_keys,
                    "side_a": side_a,
                    "side_a_key": side_a_keys[0],
                    "side_b": side_b,
                    "side_b_key": side_b_keys[0],
                    "epsilon_degrees": epsilon,
                }
    raise AssertionError(f"Could not derive isolated boundary for {field}")


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class FixedPointSession:
    def __init__(self, lon: float, lat: float, county_geoid: str = "48181", county_code: str = "181"):
        self.lon = lon
        self.lat = lat
        self.county_geoid = county_geoid
        self.county_code = county_code
        self.real = requests.Session()
        self.real.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})

    def get(self, url, params=None, timeout=None):
        if "geocoding.geo.census.gov" in url:
            return FakeResponse(
                {
                    "result": {
                        "addressMatches": [
                            {
                                "matchedAddress": "GRAYSON BOUNDARY CONTROL",
                                "coordinates": {"x": self.lon, "y": self.lat},
                                "geographies": {
                                    "States": [{"GEOID": "48", "STATE": "48"}],
                                    "Counties": [{"GEOID": self.county_geoid, "COUNTY": self.county_code}],
                                },
                            }
                        ]
                    }
                }
            )
        return self.real.get(url, params=params, timeout=timeout)


def validate_roster_and_bundle(onboarding: Path) -> tuple[dict, dict, dict]:
    report = json.loads((onboarding / "fit-report.json").read_text(encoding="utf-8"))
    expected_fit = {
        "decision": "GO",
        "result": "SUPPORTED_V0_1",
        "stop_class": "NONE",
        "stop_classes": [],
        "architecture_change": "NO",
    }
    if {key: report.get(key) for key in expected_fit} != expected_fit:
        raise AssertionError(f"Grayson frozen fit result changed: {report}")

    release = json.loads((onboarding / "canonical-release-preview.json").read_text(encoding="utf-8"))
    release_without_hash = copy.deepcopy(release)
    recorded_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
    if recorded_sha != canonical_sha(release_without_hash):
        raise AssertionError("Grayson canonical release content SHA mismatch")
    offices = release.get("payload", {}).get("offices") or []
    holders = release.get("payload", {}).get("officeholders") or []
    if len(offices) != 18 or len(holders) != 18:
        raise AssertionError(f"Grayson roster must be 18 offices / 18 holders, got {len(offices)} / {len(holders)}")
    office_ids = {row.get("office_id") for row in offices}
    roster = {row.get("office_id"): row.get("canonical_name") for row in holders}
    if len(office_ids) != 18 or office_ids != set(roster) or roster != EXPECTED_ROSTER:
        raise AssertionError(f"Grayson canonical roster or identity join changed: {roster}")

    bundle = json.loads((onboarding / "base-bundle-plan.json").read_text(encoding="utf-8"))
    adapter_rows = {row.get("adapter_id"): row for row in bundle.get("district_adapters") or []}
    if set(adapter_rows) != set(ADAPTERS):
        raise AssertionError(f"Grayson adapter set changed: {sorted(adapter_rows)}")
    expected_sources = {
        A_COMM: (COMM_SERVICE, COMM_FIELD),
        A_JP: (JPC_SERVICE, JPC_FIELD),
        A_CONST: (JPC_SERVICE, JPC_FIELD),
    }
    for adapter_id, adapter in adapter_rows.items():
        if (adapter.get("service_url"), adapter.get("district_field")) != expected_sources[adapter_id]:
            raise AssertionError(f"{adapter_id} source contract changed: {adapter}")
        if adapter.get("failure_scope") != "ADAPTER":
            raise AssertionError(f"{adapter_id} failure scope changed")
        if adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY":
            raise AssertionError(f"{adapter_id} identity source changed")
        if adapter.get("boundary_policy") != POLICY or adapter.get("boundary_probe_distance_meters") != 1:
            raise AssertionError(f"{adapter_id} boundary contract changed")
    precedence = json.loads((onboarding / "source-precedence.json").read_text(encoding="utf-8"))
    if precedence.get("status") != "RESOLVED" or len(precedence.get("records") or []) != 1:
        raise AssertionError(f"Grayson source-precedence proof changed: {precedence}")
    return report, release, bundle


def validate_applicable(label: str, payload: dict, expected: dict[str, str]) -> None:
    matched = applicable(payload)
    wide = [row for row in matched if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in matched if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(matched), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(f"[{label}] expected 9 = 6 wide + 3 district, got {len(matched)} = {len(wide)} + {len(district)}")
    if {row.get("office_id") for row in wide} != COUNTYWIDE_IDS:
        raise AssertionError(f"[{label}] bounded countywide office set changed")
    district_ids = {
        f"office-us-tx-grayson-county-commissioner-{expected[A_COMM]}",
        f"office-us-tx-grayson-county-jp-{expected[A_JP]}",
        f"office-us-tx-grayson-county-constable-{expected[A_CONST]}",
    }
    if {row.get("office_id") for row in district} != district_ids:
        raise AssertionError(f"[{label}] district office set changed")
    release_layers = {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "RELEASE_BACKED" and str(row.get("layer") or "").startswith("grayson_county_")
    }
    if release_layers != set(EXPECTED_LAYERS.values()):
        raise AssertionError(f"[{label}] release-backed Grayson coverage changed: {release_layers}")
    action_coverage = [row for row in payload.get("coverage") or [] if row.get("layer") == "grayson_action_endpoints"]
    if not action_coverage or action_coverage[0].get("status") != "NOT_YET_RELEASED":
        raise AssertionError(f"[{label}] Grayson action coverage gap changed: {action_coverage}")
    assert_no_actions(label, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/civic-gps-grayson-cg08")
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    onboarding = output / "onboarding"
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
    report, release, bundle = validate_roster_and_bundle(onboarding)

    runtime_bytes = b"".join(part.read_bytes() for part in sorted(RUNTIME_PARTS.glob("part.*")))
    runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
    if runtime_sha != RUNTIME_SHA256:
        raise AssertionError(f"Production runtime SHA changed: {runtime_sha}")
    if service_keys(COMM_SERVICE, COMM_FIELD) != ["1", "2", "3", "4"]:
        raise AssertionError("Grayson live Commissioner key set changed")
    if service_keys(JPC_SERVICE, JPC_FIELD) != ["1", "2", "3", "4"]:
        raise AssertionError("Grayson live JP/Constable key set changed")

    with tempfile.TemporaryDirectory(prefix="civic-gps-grayson-cg08-") as temp_name:
        temp_root = Path(temp_name)
        with ZipFile(io.BytesIO(runtime_bytes)) as runtime_archive:
            runtime_archive.extractall(temp_root)
        runtime_gps = temp_root / "civic_gps"
        engine_mod = load_module("civic_gps_engine_grayson_cg08", runtime_gps / "engine.py")
        registry = json.loads((runtime_gps / "registry.json").read_text(encoding="utf-8"))
        if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.5.9":
            raise AssertionError(f"Grayson proof requires engine 0.6.2 / registry 0.5.9: {registry}")
        if any(row.get("adapter_id") == "ADAPTER-TX-GRAYSON" for row in registry.get("bundles") or []):
            raise AssertionError("Grayson must not already exist in the packaged production registry")
        active_registry = copy.deepcopy(registry)
        active_registry["bundles"].append(bundle)
        release_name = json.loads(SPEC_PATH.read_text(encoding="utf-8"))["county"]["release_filename"]
        write_json(runtime_gps / release_name, release)
        resolver = engine_mod.CivicGPSOverlayEngine(
            active_registry,
            registry_root=runtime_gps,
            timeout_seconds=45.0,
        )

        def resolve_live(label: str, address: str) -> dict:
            for attempt in range(1, 4):
                result = resolver.resolve(address, observed_on="2026-08-09")
                error = result.get("error") or {}
                if not transient_upstream(error) or attempt == 3:
                    if "error" in result:
                        raise AssertionError(f"[{label}] engine error: {result['error']}")
                    return result
                time.sleep(2 ** (attempt - 1))
            raise AssertionError(f"[{label}] unreachable retry state")

        interior_summaries = []
        commissioner_keys = set()
        jpc_keys = set()
        for case in CASES:
            result = resolve_live(case["id"], case["address"])
            write_json(output / f"{case['id']}.json", result)
            payload = result["payload"]
            if J not in {row.get("jurisdiction_id") for row in payload.get("jurisdictions") or []}:
                raise AssertionError(f"[{case['id']}] Grayson jurisdiction did not activate")
            assignments = assignment_map(payload)
            expected_jp = case["jp_key"]
            if (
                set(assignments) != set(ADAPTERS)
                or assignments[A_JP] != expected_jp
                or assignments[A_CONST] != expected_jp
                or assignments[A_COMM] not in {"1", "2", "3", "4"}
            ):
                raise AssertionError(f"[{case['id']}] unexpected assignments: {assignments}")
            representatives = representative_map(payload)
            expected_representatives = {
                adapter_id: EXPECTED_REPRESENTATIVES[adapter_id][district_key]
                for adapter_id, district_key in assignments.items()
            }
            if representatives != expected_representatives:
                raise AssertionError(f"[{case['id']}] canonical representative join changed: {representatives}")
            validate_applicable(case["id"], payload, assignments)
            commissioner_keys.add(assignments[A_COMM])
            jpc_keys.add(assignments[A_JP])
            interior_summaries.append(
                {
                    "case": case["id"],
                    "assignments": assignments,
                    "representatives": representatives,
                    "applicable_offices": 9,
                    "status": "PASS",
                }
            )
        if jpc_keys != {"1", "2", "3", "4"}:
            raise AssertionError(f"Grayson interiors missed JP/Constable keys: {sorted(jpc_keys)}")

        outside = resolve_live("grayson-outside-austin", "700 Lavaca Street, Austin, TX 78701")
        write_json(output / "grayson-outside-austin.json", outside)
        outside_payload = outside["payload"]
        outside_jurisdictions = {row.get("jurisdiction_id") for row in outside_payload.get("jurisdictions") or []}
        if J in outside_jurisdictions or TRAVIS not in outside_jurisdictions:
            raise AssertionError(f"Outside-Austin jurisdiction isolation failed: {outside_jurisdictions}")
        if any(
            row.get("jurisdiction_id") == J
            for row in (outside_payload.get("district_assignments") or [])
            + (outside_payload.get("applicable_offices") or [])
            + (outside_payload.get("action_links") or [])
        ):
            raise AssertionError("Outside-Austin control leaked Grayson assignments/offices/actions")
        if any(
            "grayson" in json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
            for row in outside_payload.get("coverage") or []
        ):
            raise AssertionError("Outside-Austin control leaked Grayson coverage")

        def resolve_point(label: str, point: tuple[float, float]) -> dict:
            for attempt in range(1, 4):
                fixed = engine_mod.CivicGPSOverlayEngine(
                    active_registry,
                    registry_root=runtime_gps,
                    session=FixedPointSession(point[0], point[1]),
                    timeout_seconds=45.0,
                )
                result = fixed.resolve(label, observed_on="2026-08-09")
                error = result.get("error") or {}
                if not transient_upstream(error) or attempt == 3:
                    if "error" in result:
                        raise AssertionError(f"[{label}] boundary engine error: {result['error']}")
                    write_json(output / f"{label}.json", result)
                    return result["payload"]
                time.sleep(2 ** (attempt - 1))
            raise AssertionError(f"[{label}] unreachable retry state")

        comm_boundary = find_isolated_boundary(
            (COMM_SERVICE, COMM_FIELD),
            (JPC_SERVICE, JPC_FIELD),
        )
        comm_other_key = comm_boundary["other"][0]
        comm_exact = resolve_point("grayson-commissioner-boundary-exact", comm_boundary["midpoint"])
        comm_assignments = assignment_map(comm_exact)
        expected_comm_exact = {A_JP: comm_other_key, A_CONST: comm_other_key}
        if comm_assignments != expected_comm_exact:
            raise AssertionError(f"Commissioner boundary must suppress only Commissioner: {comm_assignments}")
        if representative_map(comm_exact) != {
            adapter_id: EXPECTED_REPRESENTATIVES[adapter_id][key]
            for adapter_id, key in expected_comm_exact.items()
        }:
            raise AssertionError("Commissioner boundary preserved identities changed")
        if len(applicable(comm_exact)) != 8 or conflict_layers(comm_exact) != {EXPECTED_LAYERS[A_COMM]}:
            raise AssertionError(f"Commissioner boundary fail-closed proof changed: {conflict_layers(comm_exact)}")
        assert_no_actions("commissioner-boundary-exact", comm_exact)
        comm_sides = []
        for side, key_name in (("side-a", "side_a_key"), ("side-b", "side_b_key")):
            control_key = comm_boundary[key_name]
            payload = resolve_point(
                f"grayson-commissioner-boundary-{side}",
                comm_boundary[side.replace("-", "_")],
            )
            expected = {A_COMM: control_key, A_JP: comm_other_key, A_CONST: comm_other_key}
            if assignment_map(payload) != expected:
                raise AssertionError(f"Commissioner boundary {side} changed: {assignment_map(payload)}")
            validate_applicable(f"commissioner-boundary-{side}", payload, expected)
            comm_sides.append({"side": side, "commissioner_key": control_key, "status": "PASS"})

        jpc_boundary = find_isolated_boundary(
            (JPC_SERVICE, JPC_FIELD),
            (COMM_SERVICE, COMM_FIELD),
        )
        jpc_other_key = jpc_boundary["other"][0]
        jpc_exact = resolve_point("grayson-jp-constable-boundary-exact", jpc_boundary["midpoint"])
        jpc_assignments = assignment_map(jpc_exact)
        expected_jpc_exact = {A_COMM: jpc_other_key}
        if jpc_assignments != expected_jpc_exact:
            raise AssertionError(f"JP/Constable boundary must suppress only JP+Constable: {jpc_assignments}")
        if representative_map(jpc_exact) != {A_COMM: EXPECTED_REPRESENTATIVES[A_COMM][jpc_other_key]}:
            raise AssertionError("JP/Constable boundary preserved identity changed")
        if len(applicable(jpc_exact)) != 7 or conflict_layers(jpc_exact) != {
            EXPECTED_LAYERS[A_JP],
            EXPECTED_LAYERS[A_CONST],
        }:
            raise AssertionError(f"JP/Constable boundary fail-closed proof changed: {conflict_layers(jpc_exact)}")
        assert_no_actions("jp-constable-boundary-exact", jpc_exact)
        jpc_sides = []
        for side, key_name in (("side-a", "side_a_key"), ("side-b", "side_b_key")):
            control_key = jpc_boundary[key_name]
            payload = resolve_point(
                f"grayson-jp-constable-boundary-{side}",
                jpc_boundary[side.replace("-", "_")],
            )
            expected = {A_COMM: jpc_other_key, A_JP: control_key, A_CONST: control_key}
            if assignment_map(payload) != expected:
                raise AssertionError(f"JP/Constable boundary {side} changed: {assignment_map(payload)}")
            validate_applicable(f"jp-constable-boundary-{side}", payload, expected)
            jpc_sides.append({"side": side, "jp_constable_key": control_key, "status": "PASS"})

    summary = {
        "status": "PASS",
        "county": "Grayson County, TX",
        "geoid": "48181",
        "gates": {gate: "PASS" for gate in ("CG-04", "CG-05", "CG-06", "CG-07", "CG-08")},
        "fit_result": report["result"],
        "engine_version": "0.6.2",
        "registry_artifact_version": "0.5.9",
        "runtime_sha256": runtime_sha,
        "production_runtime_changed": False,
        "release_offices": 18,
        "release_holders": 18,
        "gis_key_sets": {"commissioner": ["1", "2", "3", "4"], "jp_constable": ["1", "2", "3", "4"]},
        "interior_controls": interior_summaries,
        "interior_commissioner_keys": sorted(commissioner_keys, key=int),
        "outside_negative": {"status": "PASS", "grayson_leakage": 0, "control_jurisdiction": "Travis County"},
        "boundaries": {
            "commissioner_only": {
                "status": "PASS",
                "midpoint": list(comm_boundary["midpoint"]),
                "exact_service_keys": comm_boundary["exact"],
                "topology_nearby_keys": comm_boundary["nearby"],
                "exact_assignments": comm_assignments,
                "exact_applicable_offices": 8,
                "conflict_layers": sorted(conflict_layers(comm_exact)),
                "sides": comm_sides,
            },
            "jp_constable_only": {
                "status": "PASS",
                "midpoint": list(jpc_boundary["midpoint"]),
                "exact_service_keys": jpc_boundary["exact"],
                "topology_nearby_keys": jpc_boundary["nearby"],
                "exact_assignments": jpc_assignments,
                "exact_applicable_offices": 7,
                "conflict_layers": sorted(conflict_layers(jpc_exact)),
                "sides": jpc_sides,
            },
            "distance_probe_meters": 1,
            "policy": POLICY,
        },
        "actions": "NOT_YET_RELEASED",
        "candidate_packaged": False,
        "next_gate": "CG-09",
        "stopped_before": "CG-09",
    }
    write_json(output / "grayson-cg08-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("GRAYSON CG-04 THROUGH CG-08 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
