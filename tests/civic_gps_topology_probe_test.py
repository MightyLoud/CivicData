#!/usr/bin/env python3
"""Offline acceptance tests for the generic Civic GPS boundary probe."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "civic_gps" / "engine.py"


def load_engine():
    spec = importlib.util.spec_from_file_location("civic_gps_engine_topology_test", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, body: dict):
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class ScenarioSession:
    def __init__(self, probe_keys: list[int]):
        self.probe_keys = probe_keys
        self.exact_queries = 0
        self.probe_queries = 0

    def get(self, url, *, params, timeout):
        if "geocoder.test" in url:
            return FakeResponse({
                "result": {
                    "addressMatches": [{
                        "matchedAddress": "BOUNDARY CONTROL",
                        "coordinates": {"x": -96.2, "y": 30.6},
                        "geographies": {
                            "States": [{"GEOID": "48", "STATE": "48"}],
                            "Counties": [{"GEOID": "48041", "COUNTY": "041"}],
                        },
                    }]
                }
            })
        if "district.test" in url:
            if "distance" in params:
                self.probe_queries += 1
                assert params["distance"] == "1"
                assert params["units"] == "esriSRUnit_Meter"
                keys = self.probe_keys
            else:
                self.exact_queries += 1
                keys = [1]
            return FakeResponse({
                "features": [{"attributes": {"ID": key}} for key in keys]
            })
        raise AssertionError(f"Unexpected URL: {url}")


def release() -> dict:
    offices = [
        {
            "coverage_class": "RELEASED_CURRENT",
            "jurisdiction_id": "jur-test",
            "office_id": "office-wide",
            "official_url": "https://official.test/wide",
            "title": "Countywide Office",
        },
        *[
            {
                "coverage_class": "RELEASED_CURRENT",
                "jurisdiction_id": "jur-test",
                "office_id": f"office-district-{key}",
                "official_url": f"https://official.test/{key}",
                "title": f"District {key}",
            }
            for key in (1, 2)
        ],
    ]
    return {
        "payload": {
            "jurisdictions": [{
                "division_id": "div-us-tx-test",
                "jurisdiction_id": "jur-test",
                "name": "Test County",
                "snapshot_ref": "https://official.test/roster",
            }],
            "offices": offices,
            "officeholders": [
                {"canonical_name": f"Holder {index}", "office_id": office["office_id"]}
                for index, office in enumerate(offices, 1)
            ],
        }
    }


def registry(probe_distance=1) -> dict:
    adapter = {
        "activation": {"jurisdiction_active": "jur-test"},
        "adapter_id": "DIST-TEST",
        "boundary_policy": "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK",
        "district_field": "ID",
        "district_key_normalization": "NUMERIC",
        "district_name_template": "District {key}",
        "division_id_template": "div-us-tx-test-{key}",
        "division_type": "county_district",
        "failure_scope": "ADAPTER",
        "jurisdiction_id": "jur-test",
        "layer": "test_district",
        "office_id_template": "office-district-{key}",
        "parent_division_id": "div-us-tx-test",
        "required": True,
        "resolution_method": "CENSUS_GEOCODE_PLUS_OFFICIAL_ARCGIS_POINT_INTERSECT",
        "service_url": "https://district.test/FeatureServer/0",
    }
    if probe_distance is not None:
        adapter["boundary_probe_distance_meters"] = probe_distance
    return {
        "schema_version": "civic-gps-adapter-registry/0.2.0",
        "consumer_schema_version": "civic-gps-response/0.3.0",
        "engine_version": "0.6.2",
        "registry_artifact_version": "0.5.7",
        "geocoder": {
            "url": "https://geocoder.test/geographies/onelineaddress",
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
        },
        "bundles": [{
            "action_registry_files": [],
            "adapter_id": "ADAPTER-TEST",
            "applicable_office_rules": [{
                "include_resolved_district_offices": True,
                "jurisdiction_id": "jur-test",
                "jurisdiction_wide_office_ids": ["office-wide"],
            }],
            "coverage_rules": [],
            "district_adapters": [adapter],
            "division_rules": [{
                "division_id": "div-us-tx-test",
                "name": "Test County",
                "parent_id": "div-us-tx",
                "type": "county",
                "when": {"equals": "48041", "fields": ["GEOID"], "geography": "county"},
            }],
            "jurisdictions": [{
                "activation": {"equals": "48041", "fields": ["GEOID"], "geography": "county"},
                "jurisdiction_id": "jur-test",
            }],
            "known_gaps": [],
            "mode": "BASE",
            "priority": 100,
            "release_files": ["release.json"],
            "scope_match": {"equals": "48041", "fields": ["GEOID"], "geography": "county"},
        }],
    }


def resolve_case(engine_mod, root: Path, probe_keys: list[int], probe_distance=1):
    session = ScenarioSession(probe_keys)
    engine = engine_mod.CivicGPSOverlayEngine(
        registry(probe_distance),
        registry_root=root,
        session=session,
    )
    result = engine.resolve("BOUNDARY CONTROL", observed_on="2026-08-08")
    if "error" in result:
        raise AssertionError(result["error"])
    return result["payload"], session


def main() -> int:
    engine_mod = load_engine()
    with tempfile.TemporaryDirectory(prefix="civic-gps-topology-") as tmp:
        root = Path(tmp)
        (root / "release.json").write_text(
            json.dumps(release(), sort_keys=True) + "\n",
            encoding="utf-8",
        )

        conflict, conflict_session = resolve_case(engine_mod, root, [1, 2])
        assert conflict["district_assignments"] == []
        assert [row["office_id"] for row in conflict["applicable_offices"]] == ["office-wide"]
        assert conflict_session.exact_queries == 1 and conflict_session.probe_queries == 1
        assert {
            row["layer"] for row in conflict["coverage"] if row.get("status") == "CONFLICT"
        } == {"test_district"}
        assert len([row for row in conflict["known_gaps"] if row.get("status") == "CONFLICT"]) == 1

        for probe_keys in ([], [2]):
            inconsistent, inconsistent_session = resolve_case(engine_mod, root, probe_keys)
            assert inconsistent["district_assignments"] == []
            assert [row["office_id"] for row in inconsistent["applicable_offices"]] == ["office-wide"]
            assert inconsistent_session.exact_queries == 1 and inconsistent_session.probe_queries == 1
            assert {
                row["layer"]
                for row in inconsistent["coverage"]
                if row.get("status") == "CONFLICT"
            } == {"test_district"}

        interior, interior_session = resolve_case(engine_mod, root, [1])
        assert {row["district_key"] for row in interior["district_assignments"]} == {"1"}
        assert {row["office_id"] for row in interior["applicable_offices"]} == {
            "office-wide", "office-district-1"
        }
        assert interior_session.exact_queries == 1 and interior_session.probe_queries == 1

        compatible, compatible_session = resolve_case(engine_mod, root, [1, 2], None)
        assert {row["district_key"] for row in compatible["district_assignments"]} == {"1"}
        assert compatible_session.exact_queries == 1 and compatible_session.probe_queries == 0

        for invalid in (0, -1, 10.1, True, "1"):
            try:
                engine_mod.CivicGPSOverlayEngine(
                    registry(invalid),
                    registry_root=root,
                    session=ScenarioSession([1]),
                )
            except engine_mod.CivicGPSResolverError as exc:
                assert exc.code == "REGISTRY_BOUNDARY_PROBE_INVALID"
            else:
                raise AssertionError(f"Invalid boundary probe was accepted: {invalid!r}")

    print(json.dumps({
        "status": "PASS",
        "engine_version": "0.6.2",
        "probe_distance_meters": 1,
        "topology_conflict": "ADAPTER_SCOPED",
        "empty_probe": "FAIL_CLOSED",
        "inconsistent_probe": "FAIL_CLOSED",
        "unconfigured_adapter_compatibility": "PASS",
        "invalid_registry_values": "REJECTED",
    }, sort_keys=True))
    print("CIVIC GPS TOPOLOGY PROBE v0.6.2 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
