#!/usr/bin/env python3
"""Johnson County CG-05 GIS/adapter proof; stop before interior controls."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from civic_gps_johnson_roster_probe import (
    ADAPTERS,
    ONBOARDING_TOOL,
    POLICY,
    PRODUCTION_MAIN_COMMIT,
    PRODUCTION_MAIN_TREE,
    SPEC_PATH,
    validate_candidate,
    validate_production_runtime,
    write_json,
)


SERVICE = (
    "https://services7.arcgis.com/gVohhGAlfFScDJGs/arcgis/rest/services/"
    "County_Precincts_2021/FeatureServer/0"
)
PROVENANCE_URL = (
    "https://www.johnsoncountytx.org/departments/geographic-information-system-gis/"
    "interactive-maps"
)
EXPECTED_LAYER_NAME = "JoCoGIS.DBO.County_Precincts_2021"
EXPECTED_FIELD = "ID"
EXPECTED_FIELD_TYPE = "esriFieldTypeInteger"
EXPECTED_KEYS = ["1", "2", "3", "4"]
EXPECTED_ADAPTER_LAYERS = {
    "DIST-TX-JOHNSON-COMMISSIONER": "johnson_county_commissioner_precinct",
    "DIST-TX-JOHNSON-JP": "johnson_county_jp_precinct",
    "DIST-TX-JOHNSON-CONSTABLE": "johnson_county_constable_precinct",
}
USER_AGENT = "CivicGPS/0.6.2 (+https://github.com/MightyLoud/CivicData)"


def get_json(url: str, params: dict[str, str], *, attempts: int = 3) -> dict:
    query_url = url.rstrip("/") + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(query_url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = json.loads(response.read())
            if body.get("error"):
                raise AssertionError(f"ArcGIS error from {url}: {body['error']}")
            return body
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)
    raise AssertionError(f"ArcGIS request failed after {attempts} attempts: {last_error}")


def normalize_key(raw: object) -> str:
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def validate_live_layer() -> dict:
    metadata = get_json(SERVICE, {"f": "json"})
    if metadata.get("name") != EXPECTED_LAYER_NAME:
        raise AssertionError(f"Johnson layer name changed: {metadata.get('name')}")
    if metadata.get("type") != "Feature Layer":
        raise AssertionError(f"Johnson layer type changed: {metadata.get('type')}")
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise AssertionError(f"Johnson geometry type changed: {metadata.get('geometryType')}")
    if "Query" not in str(metadata.get("capabilities") or ""):
        raise AssertionError(f"Johnson layer no longer supports Query: {metadata.get('capabilities')}")
    fields = {row.get("name"): row for row in metadata.get("fields") or []}
    if EXPECTED_FIELD not in fields or fields[EXPECTED_FIELD].get("type") != EXPECTED_FIELD_TYPE:
        raise AssertionError(f"Johnson district-field schema changed: {fields.get(EXPECTED_FIELD)}")
    spatial_reference = metadata.get("extent", {}).get("spatialReference") or {}
    if (spatial_reference.get("wkid"), spatial_reference.get("latestWkid")) != (103159, 6584):
        raise AssertionError(f"Johnson spatial reference changed: {spatial_reference}")

    features = get_json(
        SERVICE + "/query",
        {
            "where": "1=1",
            "outFields": EXPECTED_FIELD,
            "returnGeometry": "false",
            "orderByFields": f"{EXPECTED_FIELD} ASC",
            "f": "json",
        },
    ).get("features") or []
    keys = [normalize_key((feature.get("attributes") or {}).get(EXPECTED_FIELD)) for feature in features]
    if keys != EXPECTED_KEYS:
        raise AssertionError(f"Johnson live district-key set changed: {keys}")

    count_body = get_json(
        SERVICE + "/query",
        {"where": "1=1", "returnCountOnly": "true", "f": "json"},
    )
    if count_body.get("count") != 4 or len(features) != 4:
        raise AssertionError(f"Johnson layer must contain exactly four precinct polygons: {count_body}")
    return {
        "feature_count": 4,
        "field": EXPECTED_FIELD,
        "field_type": EXPECTED_FIELD_TYPE,
        "geometry_type": "esriGeometryPolygon",
        "keys": keys,
        "layer_name": EXPECTED_LAYER_NAME,
        "service_url": SERVICE,
        "spatial_reference": {"wkid": 103159, "latest_wkid": 6584},
        "status": "PASS",
    }


def validate_adapter_contracts(bundle: dict) -> list[dict]:
    adapters = {row.get("adapter_id"): row for row in bundle.get("district_adapters") or []}
    if set(adapters) != ADAPTERS:
        raise AssertionError(f"Johnson adapter set changed: {sorted(adapters)}")
    evidence = []
    for adapter_id in sorted(adapters):
        adapter = adapters[adapter_id]
        expected = {
            "service_url": SERVICE,
            "district_field": EXPECTED_FIELD,
            "district_key_normalization": "NUMERIC",
            "resolver_kind": "ARCGIS_POINT_INTERSECT",
            "failure_scope": "ADAPTER",
            "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
            "boundary_policy": POLICY,
            "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
            "endpoint_provenance_url": PROVENANCE_URL,
            "query_enabled": True,
            "required": True,
        }
        actual = {key: adapter.get(key) for key in expected}
        if actual != expected:
            raise AssertionError(f"{adapter_id} contract changed: {actual} != {expected}")
        if adapter.get("layer") != EXPECTED_ADAPTER_LAYERS[adapter_id]:
            raise AssertionError(f"{adapter_id} layer changed: {adapter.get('layer')}")
        evidence.append(
            {
                "adapter_id": adapter_id,
                "boundary_policy": adapter["boundary_policy"],
                "district_field": adapter["district_field"],
                "district_key_normalization": adapter["district_key_normalization"],
                "endpoint_authority_class": adapter["endpoint_authority_class"],
                "endpoint_provenance_url": adapter["endpoint_provenance_url"],
                "failure_scope": adapter["failure_scope"],
                "layer": adapter["layer"],
                "officeholder_identity_source": adapter["officeholder_identity_source"],
                "query_enabled": adapter["query_enabled"],
                "required": adapter["required"],
                "resolver_kind": adapter["resolver_kind"],
                "service_url": adapter["service_url"],
                "status": "PASS",
            }
        )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    onboarding = output / "onboarding"
    subprocess.run(
        [
            "python",
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
    report, _, bundle = validate_candidate(onboarding)
    runtime = validate_production_runtime()
    live_layer = validate_live_layer()
    adapter_evidence = validate_adapter_contracts(bundle)
    summary = {
        "status": "PASS",
        "county": "Johnson County, TX",
        "geoid": "48251",
        "gates": {"CG-05": "PASS"},
        "prerequisite_gates": {"CG-04": "PASS"},
        "fit_result": report["result"],
        "live_layer": live_layer,
        "adapters": adapter_evidence,
        "adapter_count": 3,
        "shared_geometry_families": ["commissioner", "justice_of_the_peace", "constable"],
        "authority": {
            "class": "OFFICIAL_COUNTY_GIS",
            "provenance_url": PROVENANCE_URL,
            "publisher": "Johnson County GIS and Mapping",
        },
        "network_queries": ["LAYER_METADATA", "DISTRICT_KEY_SET", "FEATURE_COUNT"],
        "address_geocoder_calls": 0,
        "point_intersection_calls": 0,
        "interior_controls_run": 0,
        "actions": "NOT_YET_RELEASED",
        "scope": "BOUNDED_V0_1_SCOPE",
        "candidate_packaged": False,
        "production_main_commit": PRODUCTION_MAIN_COMMIT,
        "production_main_tree": PRODUCTION_MAIN_TREE,
        **runtime,
        "production_runtime_changed": False,
        "next_gate": "CG-06",
        "stopped_before": "CG-06",
    }
    write_json(output / "johnson-cg05-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("JOHNSON CG-05 GIS/ADAPTER PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
