#!/usr/bin/env python3
"""Smith County live proof for the CG-08 base runtime or CG-09 candidate package."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
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
SPEC_PATH = ROOT / "tests/fixtures/civic_gps_county_onboarding/smith_county9_candidate_v0.1.json"
ONBOARDING_TOOL = ROOT / "tools/civic_gps_county_onboarding.py"
RUNTIME_PARTS = ROOT / "civic_gps_runtime_parts"
RUNTIME_SHA256 = "bc40a0aa46fcdbd5b2c73976747ef702d9a64fd051832c615ba4aba1016a7427"
CANDIDATE_RUNTIME_SHA256 = "49b54af31cb4687936a2dddb6a91f6305aa7b4977756a3db203562971296a23a"
J = "jur-us-tx-smith-county"
TRAVIS = "jur-us-tx-travis-county"
A_COMM = "DIST-TX-SMITH-COMMISSIONER"
A_JP = "DIST-TX-SMITH-JP"
A_CONST = "DIST-TX-SMITH-CONSTABLE"
ADAPTERS = (A_COMM, A_JP, A_CONST)
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
COMM_SERVICE = "https://services3.arcgis.com/dPuMck04cWB2fx4h/arcgis/rest/services/EA_Districts3_WFL1/FeatureServer/6"
JPC_SERVICE = "https://services3.arcgis.com/dPuMck04cWB2fx4h/arcgis/rest/services/EA_Districts3_WFL1/FeatureServer/4"
COMM_FIELD = "DISTRICTID"
JPC_FIELD = "Precinct"
EXPECTED_LAYERS = {
    A_COMM: "smith_county_commissioner_precinct",
    A_JP: "smith_county_jp_precinct",
    A_CONST: "smith_county_constable_precinct",
}
COUNTYWIDE_IDS = {
    "office-us-tx-smith-county-judge",
    "office-us-tx-smith-county-sheriff",
    "office-us-tx-smith-county-clerk",
    "office-us-tx-smith-county-district-clerk",
    "office-us-tx-smith-county-tax-assessor-collector",
    "office-us-tx-smith-county-treasurer",
}
EXPECTED_ROSTER = {
    "office-us-tx-smith-county-judge": "Neal Franklin",
    "office-us-tx-smith-county-sheriff": "Larry Smith",
    "office-us-tx-smith-county-clerk": "Karen Phillips",
    "office-us-tx-smith-county-district-clerk": "Gaye Boynton",
    "office-us-tx-smith-county-tax-assessor-collector": "Gary Barber",
    "office-us-tx-smith-county-treasurer": "Kelli White",
    "office-us-tx-smith-county-commissioner-1": "Christina Drewry",
    "office-us-tx-smith-county-commissioner-2": "John Moore",
    "office-us-tx-smith-county-commissioner-3": "J Scott Herod",
    "office-us-tx-smith-county-commissioner-4": "Ralph Caraway, Sr.",
    "office-us-tx-smith-county-jp-1": "Derrick Choice",
    "office-us-tx-smith-county-jp-2": "Andy Dunklin",
    "office-us-tx-smith-county-jp-3": "James Meredith",
    "office-us-tx-smith-county-jp-4": "Curtis Wulf",
    "office-us-tx-smith-county-jp-5": "Danny Brown",
    "office-us-tx-smith-county-constable-1": "Ralph Caraway, Jr.",
    "office-us-tx-smith-county-constable-2": "Wayne Allen",
    "office-us-tx-smith-county-constable-3": "Jim Blackmon",
    "office-us-tx-smith-county-constable-4": "Josh Joplin",
    "office-us-tx-smith-county-constable-5": "Wesley Hicks",
}
CASES = [
    {
        "id": "smith-jp1",
        "address": "200 E Ferguson Street, Suite 500, Tyler, TX 75702",
        "expected": {A_COMM: "4", A_JP: "1", A_CONST: "1"},
        "representatives": {A_COMM: "Ralph Caraway, Sr.", A_JP: "Derrick Choice", A_CONST: "Ralph Caraway, Jr."},
    },
    {
        "id": "smith-jp2",
        "address": "15405 Highway 155 South, Tyler, TX 75703",
        "expected": {A_COMM: "1", A_JP: "2", A_CONST: "2"},
        "representatives": {A_COMM: "Christina Drewry", A_JP: "Andy Dunklin", A_CONST: "Wayne Allen"},
    },
    {
        "id": "smith-jp3",
        "address": "313 E Duval Street, Troup, TX 75789",
        "expected": {A_COMM: "2", A_JP: "3", A_CONST: "3"},
        "representatives": {A_COMM: "John Moore", A_JP: "James Meredith", A_CONST: "Jim Blackmon"},
    },
    {
        "id": "smith-jp4",
        "address": "13640 Highway 155 North, Winona, TX 75708",
        "expected": {A_COMM: "3", A_JP: "4", A_CONST: "4"},
        "representatives": {A_COMM: "J Scott Herod", A_JP: "Curtis Wulf", A_CONST: "Josh Joplin"},
    },
    {
        "id": "smith-jp5",
        "address": "2616 S Main Street, Lindale, TX 75771",
        "expected": {A_COMM: "3", A_JP: "5", A_CONST: "5"},
        "representatives": {A_COMM: "J Scott Herod", A_JP: "Danny Brown", A_CONST: "Wesley Hicks"},
    },
]
FROZEN_GEOCODES = {
    "smith-jp1": (-95.299517347969, 32.351785235677, "48423", "423"),
    "smith-jp2": (-95.384544724791, 32.257605605846, "48423", "423"),
    "smith-jp3": (-95.118267838911, 32.144615122508, "48423", "423"),
    "smith-jp4": (-95.18063215281, 32.461811032356, "48423", "423"),
    "smith-jp5": (-95.394903609865, 32.481569144318, "48423", "423"),
    "smith-outside-austin": (-97.744889426273, 30.269731431674, "48453", "453"),
}
COMM_BOUNDARY = {
    "midpoint": (-95.559167285, 32.49296178),
    "exact": ["4"],
    "nearby": ["3", "4"],
    "other": ["5"],
    "side_a": (-95.55916999409965, 32.49295215395309),
    "side_a_key": "4",
    "side_b": (-95.55916457590035, 32.49297140604691),
    "side_b_key": "3",
}
JPC_BOUNDARY = {
    "midpoint": (-95.38761714, 32.36079222),
    "exact": ["5"],
    "nearby": ["2", "5"],
    "other": ["1"],
    "side_a": (-95.38761496961943, 32.36080198163143),
    "side_a_key": "5",
    "side_b": (-95.38761931038057, 32.36078245836857),
    "side_b_key": "2",
}
TRANSIENT_CENSUS_MARKERS = (
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
        raise AssertionError(f"[{label}] Smith action routing must remain unreleased: {actions}")


def conflict_layers(payload: dict) -> set[str]:
    return {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "CONFLICT" and str(row.get("layer") or "").startswith("smith_county_")
    }


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"})


def get_json(url: str, params: dict) -> dict:
    response = SESSION.get(url, params=params, timeout=45)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
    return body


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


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class FixedPointSession:
    def __init__(self, lon: float, lat: float, county_geoid: str = "48423", county_code: str = "423"):
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
                                "matchedAddress": "SMITH BOUNDARY CONTROL",
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
        raise AssertionError(f"Smith frozen fit result changed: {report}")

    release = json.loads((onboarding / "canonical-release-preview.json").read_text(encoding="utf-8"))
    release_without_hash = copy.deepcopy(release)
    recorded_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
    if recorded_sha != canonical_sha(release_without_hash):
        raise AssertionError("Smith canonical release content SHA mismatch")
    offices = release.get("payload", {}).get("offices") or []
    holders = release.get("payload", {}).get("officeholders") or []
    if len(offices) != 20 or len(holders) != 20:
        raise AssertionError(f"Smith roster must be 20 offices / 20 holders, got {len(offices)} / {len(holders)}")
    office_ids = {row.get("office_id") for row in offices}
    roster = {row.get("office_id"): row.get("canonical_name") for row in holders}
    if len(office_ids) != 20 or office_ids != set(roster) or roster != EXPECTED_ROSTER:
        raise AssertionError(f"Smith canonical roster or identity join changed: {roster}")

    bundle = json.loads((onboarding / "base-bundle-plan.json").read_text(encoding="utf-8"))
    adapter_rows = {row.get("adapter_id"): row for row in bundle.get("district_adapters") or []}
    if set(adapter_rows) != set(ADAPTERS):
        raise AssertionError(f"Smith adapter set changed: {sorted(adapter_rows)}")
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
        raise AssertionError(f"Smith source-precedence proof changed: {precedence}")
    return report, release, bundle


def validate_packaged_candidate(runtime_gps: Path, registry: dict) -> dict:
    if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.5.9":
        raise AssertionError(f"Smith candidate requires engine 0.6.2 / registry 0.5.9: {registry}")
    registry_without_hash = copy.deepcopy(registry)
    recorded_registry_sha = registry_without_hash.pop("canonical_content_sha256", None)
    if not recorded_registry_sha or recorded_registry_sha != canonical_sha(registry_without_hash):
        raise AssertionError("Smith candidate registry canonical content SHA mismatch")
    smith_bundles = [
        row for row in registry.get("bundles") or [] if row.get("adapter_id") == "ADAPTER-TX-SMITH"
    ]
    if len(registry.get("bundles") or []) != 12 or len(smith_bundles) != 1:
        raise AssertionError("Smith candidate must contain exactly 12 bundles and one Smith bundle")
    bundle = smith_bundles[0]
    adapter_rows = {row.get("adapter_id"): row for row in bundle.get("district_adapters") or []}
    if set(adapter_rows) != set(ADAPTERS) or any(
        row.get("source_status") != "LIVE_INTERIOR_NEGATIVE_BOUNDARY_PASS"
        for row in adapter_rows.values()
    ):
        raise AssertionError(f"Smith candidate adapter proof status changed: {adapter_rows}")
    gap_statuses = {
        row.get("gap_id"): row.get("status") for row in bundle.get("known_gaps") or []
    }
    if gap_statuses != {
        "GAP-SMITH-GPS-001": "NOT_YET_RELEASED",
        "GAP-SMITH-GPS-002": "BOUNDED_V0_1_SCOPE",
        "GAP-SMITH-GPS-003": "SOURCE_PRECEDENCE_RESOLVED",
        "GAP-SMITH-GPS-004": "PROTECTED_PROMOTION_PENDING",
    }:
        raise AssertionError(f"Smith candidate known-gap states changed: {gap_statuses}")
    if any(path.name.startswith("civic_gps_action_registry_smith") for path in runtime_gps.glob("*.json")):
        raise AssertionError("Smith action routing must not be packaged in CG-09")

    release_path = runtime_gps / "civic_gps_smith_county_v0.1.json"
    if not release_path.is_file():
        raise AssertionError("Smith candidate release file is absent")
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release_without_hash = copy.deepcopy(release)
    recorded_release_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
    if not recorded_release_sha or recorded_release_sha != canonical_sha(release_without_hash):
        raise AssertionError("Packaged Smith release canonical content SHA mismatch")
    if release.get("meta", {}).get("release_status") != "RELEASE_BACKED_CURRENT":
        raise AssertionError("Packaged Smith release status must be RELEASE_BACKED_CURRENT")
    jurisdictions = release.get("payload", {}).get("jurisdictions") or []
    if len(jurisdictions) != 1 or jurisdictions[0].get("status") != "RELEASE_BACKED_CURRENT":
        raise AssertionError(f"Packaged Smith jurisdiction status changed: {jurisdictions}")
    offices = release.get("payload", {}).get("offices") or []
    holders = release.get("payload", {}).get("officeholders") or []
    roster = {row.get("office_id"): row.get("canonical_name") for row in holders}
    if len(offices) != 20 or len(holders) != 20 or roster != EXPECTED_ROSTER:
        raise AssertionError("Packaged Smith 20-office / 20-holder canonical roster changed")
    return bundle


def validate_applicable(label: str, payload: dict, expected: dict[str, str]) -> None:
    matched = applicable(payload)
    wide = [row for row in matched if row.get("applicability_scope") == "JURISDICTION_WIDE"]
    district = [row for row in matched if row.get("applicability_scope") == "DISTRICT_MATCH"]
    if (len(matched), len(wide), len(district)) != (9, 6, 3):
        raise AssertionError(f"[{label}] expected 9 = 6 wide + 3 district, got {len(matched)} = {len(wide)} + {len(district)}")
    if {row.get("office_id") for row in wide} != COUNTYWIDE_IDS:
        raise AssertionError(f"[{label}] bounded countywide office set changed")
    district_ids = {
        f"office-us-tx-smith-county-commissioner-{expected[A_COMM]}",
        f"office-us-tx-smith-county-jp-{expected[A_JP]}",
        f"office-us-tx-smith-county-constable-{expected[A_CONST]}",
    }
    if {row.get("office_id") for row in district} != district_ids:
        raise AssertionError(f"[{label}] district office set changed")
    release_layers = {
        str(row.get("layer"))
        for row in payload.get("coverage") or []
        if row.get("status") == "RELEASE_BACKED" and str(row.get("layer") or "").startswith("smith_county_")
    }
    if release_layers != set(EXPECTED_LAYERS.values()):
        raise AssertionError(f"[{label}] release-backed Smith coverage changed: {release_layers}")
    action_coverage = [row for row in payload.get("coverage") or [] if row.get("layer") == "smith_action_endpoints"]
    if not action_coverage or action_coverage[0].get("status") != "NOT_YET_RELEASED":
        raise AssertionError(f"[{label}] Smith action coverage gap changed: {action_coverage}")
    assert_no_actions(label, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/civic-gps-smith-cg08")
    parser.add_argument(
        "--packaged",
        action="store_true",
        help="Validate the deterministic CG-09 candidate already installed in runtime parts.",
    )
    parser.add_argument(
        "--expected-runtime-sha256",
        default=CANDIDATE_RUNTIME_SHA256,
        help="Exact candidate runtime SHA required in --packaged mode.",
    )
    parser.add_argument(
        "--use-frozen-geocodes",
        action="store_true",
        help="Use the live-verified Census coordinates for local restricted-sandbox validation.",
    )
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
    expected_runtime_sha = args.expected_runtime_sha256 if args.packaged else RUNTIME_SHA256
    if runtime_sha != expected_runtime_sha:
        mode = "candidate" if args.packaged else "production"
        raise AssertionError(f"Smith {mode} runtime SHA changed: {runtime_sha}")
    if args.packaged and runtime_sha == RUNTIME_SHA256:
        raise AssertionError("CG-09 packaged proof cannot run against the unchanged production runtime")

    if service_keys(COMM_SERVICE, COMM_FIELD) != ["1", "2", "3", "4"]:
        raise AssertionError("Smith live Commissioner key set changed")
    if service_keys(JPC_SERVICE, JPC_FIELD) != ["1", "2", "3", "4", "5"]:
        raise AssertionError("Smith live JP/Constable key set changed")

    gate = "CG-09" if args.packaged else "CG-08"
    gate_slug = "cg09" if args.packaged else "cg08"
    with tempfile.TemporaryDirectory(prefix=f"civic-gps-smith-{gate_slug}-") as temp_name:
        temp_root = Path(temp_name)
        with ZipFile(io.BytesIO(runtime_bytes)) as runtime_archive:
            runtime_archive.extractall(temp_root)
        runtime_gps = temp_root / "civic_gps"
        engine_mod = load_module(f"civic_gps_engine_smith_{gate_slug}", runtime_gps / "engine.py")
        registry = json.loads((runtime_gps / "registry.json").read_text(encoding="utf-8"))
        if args.packaged:
            active_registry = registry
            bundle = validate_packaged_candidate(runtime_gps, registry)
        else:
            if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.5.8":
                raise AssertionError(f"Smith proof requires engine 0.6.2 / registry 0.5.8: {registry}")
            if any(row.get("adapter_id") == "ADAPTER-TX-SMITH" for row in registry.get("bundles") or []):
                raise AssertionError("Smith must not already exist in the packaged production registry")
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
            active_resolver = resolver
            if args.use_frozen_geocodes:
                lon, lat, county_geoid, county_code = FROZEN_GEOCODES[label]
                active_resolver = engine_mod.CivicGPSOverlayEngine(
                    active_registry,
                    registry_root=runtime_gps,
                    session=FixedPointSession(lon, lat, county_geoid, county_code),
                    timeout_seconds=45.0,
                )
            for attempt in range(1, 4):
                result = active_resolver.resolve(address, observed_on="2026-08-09")
                error = result.get("error") or {}
                details = error.get("details") or {}
                upstream = str(details.get("error") or "").lower()
                transient = (
                    error.get("code") == "UPSTREAM_REQUEST_FAILED"
                    and error.get("message") == "GEOCODER request failed."
                    and str(details.get("url") or "").startswith("https://geocoding.geo.census.gov/geocoder/")
                    and any(marker in upstream for marker in TRANSIENT_CENSUS_MARKERS)
                )
                if not transient or attempt == 3:
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
                raise AssertionError(f"[{case['id']}] Smith jurisdiction did not activate")
            assignments = assignment_map(payload)
            representatives = representative_map(payload)
            if assignments != case["expected"]:
                raise AssertionError(f"[{case['id']}] expected {case['expected']}, got {assignments}")
            if representatives != case["representatives"]:
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
        if commissioner_keys != {"1", "2", "3", "4"} or jpc_keys != {"1", "2", "3", "4", "5"}:
            raise AssertionError(f"Smith interiors missed district keys: Commissioner={commissioner_keys}; JP={jpc_keys}")

        outside = resolve_live("smith-outside-austin", "700 Lavaca Street, Austin, TX 78701")
        write_json(output / "smith-outside-austin.json", outside)
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
            raise AssertionError("Outside-Austin control leaked Smith assignments/offices/actions")
        if any("smith" in json.dumps(row, ensure_ascii=False, sort_keys=True).lower() for row in outside_payload.get("coverage") or []):
            raise AssertionError("Outside-Austin control leaked Smith coverage")

        def resolve_point(label: str, point: tuple[float, float]) -> dict:
            fixed = engine_mod.CivicGPSOverlayEngine(
                active_registry,
                registry_root=runtime_gps,
                session=FixedPointSession(point[0], point[1]),
                timeout_seconds=45.0,
            )
            result = fixed.resolve(label, observed_on="2026-08-09")
            if "error" in result:
                raise AssertionError(f"[{label}] boundary engine error: {result['error']}")
            write_json(output / f"{label}.json", result)
            return result["payload"]

        def validate_service_boundary(primary: tuple[str, str], other: tuple[str, str], control: dict) -> None:
            if point_keys(*primary, control["midpoint"]) != control["exact"]:
                raise AssertionError(f"Boundary exact service keys changed: {control}")
            if point_keys(*primary, control["midpoint"], distance_meters=1) != control["nearby"]:
                raise AssertionError(f"Boundary 1m topology keys changed: {control}")
            if point_keys(*other, control["midpoint"], distance_meters=1) != control["other"]:
                raise AssertionError(f"Boundary isolation layer changed: {control}")
            for side, expected in (("side_a", control["side_a_key"]), ("side_b", control["side_b_key"])):
                if point_keys(*primary, control[side], distance_meters=1) != [expected]:
                    raise AssertionError(f"Boundary {side} topology key changed: {control}")
                if point_keys(*other, control[side], distance_meters=1) != control["other"]:
                    raise AssertionError(f"Boundary {side} isolation changed: {control}")

        validate_service_boundary((COMM_SERVICE, COMM_FIELD), (JPC_SERVICE, JPC_FIELD), COMM_BOUNDARY)
        comm_exact = resolve_point("smith-commissioner-boundary-exact", COMM_BOUNDARY["midpoint"])
        comm_assignments = assignment_map(comm_exact)
        if comm_assignments != {A_JP: "5", A_CONST: "5"}:
            raise AssertionError(f"Commissioner boundary must suppress only Commissioner: {comm_assignments}")
        if representative_map(comm_exact) != {A_JP: "Danny Brown", A_CONST: "Wesley Hicks"}:
            raise AssertionError("Commissioner boundary preserved identities changed")
        if len(applicable(comm_exact)) != 8 or conflict_layers(comm_exact) != {EXPECTED_LAYERS[A_COMM]}:
            raise AssertionError(f"Commissioner boundary fail-closed proof changed: {conflict_layers(comm_exact)}")
        assert_no_actions("commissioner-boundary-exact", comm_exact)
        comm_sides = []
        for side, key in (("side-a", "side_a_key"), ("side-b", "side_b_key")):
            control_key = COMM_BOUNDARY[key]
            payload = resolve_point(f"smith-commissioner-boundary-{side}", COMM_BOUNDARY[side.replace("-", "_")])
            expected = {A_COMM: control_key, A_JP: "5", A_CONST: "5"}
            if assignment_map(payload) != expected:
                raise AssertionError(f"Commissioner boundary {side} changed: {assignment_map(payload)}")
            validate_applicable(f"commissioner-boundary-{side}", payload, expected)
            comm_sides.append({"side": side, "commissioner_key": control_key, "status": "PASS"})

        validate_service_boundary((JPC_SERVICE, JPC_FIELD), (COMM_SERVICE, COMM_FIELD), JPC_BOUNDARY)
        jpc_exact = resolve_point("smith-jp-constable-boundary-exact", JPC_BOUNDARY["midpoint"])
        jpc_assignments = assignment_map(jpc_exact)
        if jpc_assignments != {A_COMM: "1"}:
            raise AssertionError(f"JP/Constable boundary must suppress only JP+Constable: {jpc_assignments}")
        if representative_map(jpc_exact) != {A_COMM: "Christina Drewry"}:
            raise AssertionError("JP/Constable boundary preserved identity changed")
        if len(applicable(jpc_exact)) != 7 or conflict_layers(jpc_exact) != {EXPECTED_LAYERS[A_JP], EXPECTED_LAYERS[A_CONST]}:
            raise AssertionError(f"JP/Constable boundary fail-closed proof changed: {conflict_layers(jpc_exact)}")
        assert_no_actions("jp-constable-boundary-exact", jpc_exact)
        jpc_sides = []
        for side, key in (("side-a", "side_a_key"), ("side-b", "side_b_key")):
            control_key = JPC_BOUNDARY[key]
            payload = resolve_point(f"smith-jp-constable-boundary-{side}", JPC_BOUNDARY[side.replace("-", "_")])
            expected = {A_COMM: "1", A_JP: control_key, A_CONST: control_key}
            if assignment_map(payload) != expected:
                raise AssertionError(f"JP/Constable boundary {side} changed: {assignment_map(payload)}")
            validate_applicable(f"jp-constable-boundary-{side}", payload, expected)
            jpc_sides.append({"side": side, "jp_constable_key": control_key, "status": "PASS"})

    summary = {
        "status": "PASS",
        "county": "Smith County, TX",
        "geoid": "48423",
        "gates": (
            {"CG-09": "PASS"}
            if args.packaged
            else {proof_gate: "PASS" for proof_gate in ("CG-04", "CG-05", "CG-06", "CG-07", "CG-08")}
        ),
        "fit_result": report["result"],
        "engine_version": "0.6.2",
        "registry_artifact_version": "0.5.9" if args.packaged else "0.5.8",
        "runtime_sha256": runtime_sha,
        "base_runtime_sha256": RUNTIME_SHA256,
        "candidate_runtime_sha256": runtime_sha if args.packaged else None,
        "production_runtime_changed": False,
        "release_offices": 20,
        "release_holders": 20,
        "gis_key_sets": {"commissioner": ["1", "2", "3", "4"], "jp_constable": ["1", "2", "3", "4", "5"]},
        "interior_controls": interior_summaries,
        "outside_negative": {"status": "PASS", "smith_leakage": 0, "control_jurisdiction": "Travis County"},
        "boundaries": {
            "commissioner_only": {
                "status": "PASS",
                "midpoint": list(COMM_BOUNDARY["midpoint"]),
                "exact_service_keys": COMM_BOUNDARY["exact"],
                "topology_nearby_keys": COMM_BOUNDARY["nearby"],
                "exact_assignments": comm_assignments,
                "exact_applicable_offices": 8,
                "conflict_layers": sorted(conflict_layers(comm_exact)),
                "sides": comm_sides,
            },
            "jp_constable_only": {
                "status": "PASS",
                "midpoint": list(JPC_BOUNDARY["midpoint"]),
                "exact_service_keys": JPC_BOUNDARY["exact"],
                "topology_nearby_keys": JPC_BOUNDARY["nearby"],
                "exact_assignments": jpc_assignments,
                "exact_applicable_offices": 7,
                "conflict_layers": sorted(conflict_layers(jpc_exact)),
                "sides": jpc_sides,
            },
            "distance_probe_meters": 1,
            "policy": POLICY,
        },
        "actions": "NOT_YET_RELEASED",
        "candidate_packaged": args.packaged,
        "next_gate": "CG-10" if args.packaged else "CG-09",
        "stopped_before": "CG-10" if args.packaged else "CG-09",
    }
    write_json(output / f"smith-{gate_slug}-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("SMITH CG-09 PACKAGED PROOF PASS" if args.packaged else "SMITH CG-04 THROUGH CG-08 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
