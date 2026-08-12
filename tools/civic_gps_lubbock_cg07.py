#!/usr/bin/env python3
"""Live, coordinate-only Lubbock County CG-07 outside-negative proof.

The proof freezes the U.S. Census Bureau's public internal point for Travis
County, requires the current official county layer to resolve it to GEOID
48453 exactly once, and requires the official Lubbock precinct layer to return
no features. No address, geocoder, office join, action route, package, or
production mutation is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


SCHEMA_VERSION = "civic-gps-lubbock-cg07-proof/0.1.0"
USER_AGENT = "Mozilla/5.0 CivicData-CivicGPS-CG07/0.1 (+https://github.com/MightyLoud/CivicData)"
EXPECTED_CANDIDATE_SHA = "20dad659a7bb3b9cfcd8ec5979827eed328aeb346bd42287dce2a6247b655fe2"
EXPECTED_CG04_PROOF_SHA = "d7d2b10a7837d651c21a2409d89de42c57bbb21d219f9ee9ee0ac35042cb3f45"
EXPECTED_CG05_PROOF_SHA = "dd03ed2106b9a00f4b3fb47add5c2136bb4e55490395714cae81b8763832438e"
EXPECTED_CG06_PROOF_SHA = "46cdf29a9164377dec9720a5587e03d8106a5e281fa5c7f004b6d9b3a27e0bf8"
EXPECTED_CG06_EVIDENCE_SHA = "7d92ad231256a62598e021588a8765db0a4ea1a413aaf03efd9e8c73fa3e118d"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_official(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in allowed_hosts:
        raise ValueError(f"non-official or unbound source URL: {url}")


def _fetch_json(url: str, allowed_hosts: set[str], *, attempts: int = 3) -> tuple[dict[str, Any], str, int]:
    _require_official(url, allowed_hosts)
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,*/*;q=0.8"})
            with urlopen(request, timeout=30) as response:
                body = response.read()
                status = int(getattr(response, "status", 200))
                final_url = response.geturl()
            _require_official(final_url, allowed_hosts)
            if status != 200 or not body:
                raise RuntimeError(f"HTTP {status} or empty response for {url}")
            value = json.loads(body)
            if not isinstance(value, dict) or value.get("error"):
                error = value.get("error") if isinstance(value, dict) else value
                raise RuntimeError(f"upstream JSON error from {url}: {error}")
            return value, final_url, status
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1 + attempt)
    raise RuntimeError(f"TRANSIENT_UPSTREAM_FAILURE: {url}: {last}")


def _query_url(service_url: str, params: dict[str, str]) -> str:
    return service_url.rstrip("/") + "/query?" + urlencode(params)


def _validate(
    candidate: dict[str, Any],
    roster_proof: dict[str, Any],
    gis_proof: dict[str, Any],
    interior_proof: dict[str, Any],
    proof: dict[str, Any],
) -> set[str]:
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"proof schema_version must be {SCHEMA_VERSION}")
    if proof.get("county") != candidate["county"]["name"] or str(proof.get("county_geoid")) != str(candidate["county"]["geoid"]):
        raise ValueError("candidate/proof county or GEOID mismatch")
    expected_shas = {
        "candidate_spec_sha256": (candidate, EXPECTED_CANDIDATE_SHA),
        "cg04_proof_spec_sha256": (roster_proof, EXPECTED_CG04_PROOF_SHA),
        "cg05_proof_spec_sha256": (gis_proof, EXPECTED_CG05_PROOF_SHA),
        "cg06_proof_spec_sha256": (interior_proof, EXPECTED_CG06_PROOF_SHA),
    }
    for field, (value, expected) in expected_shas.items():
        actual = _sha(value)
        if proof.get(field) != expected or actual != expected:
            raise ValueError(f"{field} mismatch: proof={proof.get(field)} actual={actual}")

    prior = proof.get("prior_cg06") or {}
    expected_prior = {
        "status": "PASS",
        "head_sha": "200680e2d19aa49f7195be47098d4078b7919b71",
        "run_id": 31565662082,
        "job_id": 94017079683,
        "evidence_sha256": EXPECTED_CG06_EVIDENCE_SHA,
    }
    if prior != expected_prior:
        raise ValueError(f"CG-07 requires the exact frozen CG-06 PASS baseline: {prior}")
    if proof.get("stop_before") != "CG-08":
        raise ValueError("CG-07 must stop before CG-08")
    if proof.get("input_mode") != "OFFICIAL_COUNTY_INTERNAL_POINT_COORDINATE_ONLY":
        raise ValueError("CG-07 input mode must remain coordinate-only")
    forbidden_flags = ("geocoder_used", "address_input_used", "personal_data_used")
    if any(proof.get(field) is not False for field in forbidden_flags):
        raise ValueError("CG-07 may not use a geocoder, address input, or personal data")

    census = proof.get("census_county_gis") or {}
    lubbock = proof.get("lubbock_gis") or {}
    allowed_hosts = {str(host).casefold() for host in proof.get("official_hosts") or []}
    if allowed_hosts != {"tigerweb.geo.census.gov", "gisserver.halff.com"}:
        raise ValueError("CG-07 official-host allowlist changed")
    for source in (census, lubbock):
        _require_official(str(source.get("service_url")), allowed_hosts)
    if census.get("layer_name") != "Counties" or census.get("geometry_type") != "esriGeometryPolygon":
        raise ValueError("Census county-layer contract changed")
    if census.get("out_sr") != 4326:
        raise ValueError("Census coordinate reference changed")
    if lubbock.get("service_url") != gis_proof["gis"]["service_url"] or lubbock.get("service_url") != interior_proof["gis"]["service_url"]:
        raise ValueError("CG-07/CG-05/CG-06 Lubbock service mismatch")
    if lubbock.get("district_field") != "District_ID" or lubbock.get("out_sr") != 4326:
        raise ValueError("Lubbock point-query contract changed")

    control = proof.get("control") or {}
    expected_control = {
        "id": "travis-county-census-internal-point",
        "source_mode": "OFFICIAL_COUNTY_INTERNAL_POINT_COORDINATE_ONLY",
        "state_fips": "48",
        "county_fips": "453",
        "expected_county_geoid": "48453",
        "expected_county_name": "Travis County",
        "internal_point": {
            "longitude": "-097.6910527",
            "latitude": "+30.2395263",
            "spatial_reference": 4326,
        },
    }
    if control != expected_control:
        raise ValueError(f"CG-07 outside control changed: {control}")
    expected_outcome = {
        "lubbock_feature_count": 0,
        "lubbock_jurisdiction_present": False,
        "lubbock_district_assignments": 0,
        "lubbock_applicable_offices": 0,
        "lubbock_coverage_rows": 0,
        "lubbock_district_office_joins": 0,
        "lubbock_actions": 0,
    }
    if proof.get("expected_lubbock_outcome") != expected_outcome:
        raise ValueError("CG-07 fail-closed outside outcome changed")

    records = (roster_proof.get("canonical_roster") or {}).get("records") or []
    if len(records) != 18 or len({row.get("office_id") for row in records}) != 18:
        raise ValueError("CG-07 requires the exact 18-record canonical roster contract")
    return allowed_hosts


def run(
    candidate_path: Path,
    roster_path: Path,
    gis_path: Path,
    interior_path: Path,
    proof_path: Path,
    output_dir: Path | None,
    *,
    validate_only: bool,
) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    roster_proof = json.loads(roster_path.read_text(encoding="utf-8"))
    gis_proof = json.loads(gis_path.read_text(encoding="utf-8"))
    interior_proof = json.loads(interior_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    allowed_hosts = _validate(candidate, roster_proof, gis_proof, interior_proof, proof)
    proof_sha = _sha(proof)
    if validate_only:
        summary = {
            "status": "VALID",
            "gate": "CG-07",
            "candidate_spec_sha256": _sha(candidate),
            "proof_spec_sha256": proof_sha,
            "input_mode": proof["input_mode"],
            "geocoder_used": False,
            "address_input_used": False,
            "personal_data_used": False,
            "stopped_before": "CG-08",
        }
        print(json.dumps(summary, sort_keys=True))
        return summary

    census = proof["census_county_gis"]
    lubbock = proof["lubbock_gis"]
    control = proof["control"]
    point = control["internal_point"]
    longitude = float(point["longitude"])
    latitude = float(point["latitude"])
    geometry = f"{longitude:.7f},{latitude:.7f}"

    census_url = str(census["service_url"]).rstrip("/")
    metadata, final_metadata_url, metadata_status = _fetch_json(census_url + "?f=json", allowed_hosts)
    field_names = {str(row.get("name")) for row in metadata.get("fields") or []}
    required_fields = {"GEOID", "STATE", "COUNTY", "BASENAME", "NAME", "INTPTLON", "INTPTLAT"}
    if metadata.get("name") != census["layer_name"] or metadata.get("geometryType") != census["geometry_type"]:
        raise ValueError("live Census county-layer identity changed")
    if not required_fields.issubset(field_names):
        raise ValueError(f"live Census county fields incomplete: {sorted(required_fields - field_names)}")

    out_fields = "GEOID,STATE,COUNTY,BASENAME,NAME,INTPTLON,INTPTLAT"
    record_url = _query_url(
        census_url,
        {
            "where": f"GEOID='{control['expected_county_geoid']}'",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
        },
    )
    record_result, final_record_url, record_status = _fetch_json(record_url, allowed_hosts)
    record_features = record_result.get("features") or []
    if len(record_features) != 1:
        raise ValueError(f"expected one official Travis County record, got {len(record_features)}")
    record = record_features[0].get("attributes") or {}
    expected_record = {
        "GEOID": control["expected_county_geoid"],
        "STATE": control["state_fips"],
        "COUNTY": control["county_fips"],
        "BASENAME": "Travis",
        "NAME": control["expected_county_name"],
        "INTPTLON": point["longitude"],
        "INTPTLAT": point["latitude"],
    }
    if record != expected_record:
        raise ValueError(f"official Travis County internal-point record changed: {record}")

    common_point_params = {
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": str(point["spatial_reference"]),
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "false",
        "f": "json",
    }
    county_point_url = _query_url(census_url, {**common_point_params, "outFields": out_fields})
    county_point_result, final_county_point_url, county_point_status = _fetch_json(county_point_url, allowed_hosts)
    county_matches = [feature.get("attributes") or {} for feature in county_point_result.get("features") or []]
    if county_matches != [expected_record]:
        raise ValueError(f"outside point must resolve exactly once to Travis County: {county_matches}")

    lubbock_url = str(lubbock["service_url"]).rstrip("/")
    lubbock_point_url = _query_url(
        lubbock_url,
        {**common_point_params, "outFields": lubbock["district_field"]},
    )
    lubbock_result, final_lubbock_url, lubbock_status = _fetch_json(lubbock_point_url, allowed_hosts)
    lubbock_features = lubbock_result.get("features") or []
    if lubbock_features:
        raise ValueError(f"CG-07 outside control leaked into Lubbock precincts: {lubbock_features}")

    outside_evidence = {
        "status": "PASS",
        "input_mode": proof["input_mode"],
        "test_data_class": "PUBLIC_OFFICIAL_COUNTY_INTERNAL_POINT_COORDINATES_ONLY",
        "control_id": control["id"],
        "point": [longitude, latitude],
        "spatial_reference": point["spatial_reference"],
        "geocoder_used": False,
        "address_input_used": False,
        "personal_data_used": False,
        "census_county_resolution": {
            "service_url": census_url,
            "layer_name": metadata["name"],
            "geometry_type": metadata["geometryType"],
            "required_fields_present": sorted(required_fields),
            "metadata_url": final_metadata_url,
            "metadata_http_status": metadata_status,
            "record_query_url": final_record_url,
            "record_query_http_status": record_status,
            "point_query_url": final_county_point_url,
            "point_query_http_status": county_point_status,
            "feature_count": len(county_matches),
            "geoid": expected_record["GEOID"],
            "name": expected_record["NAME"],
            "state_fips": expected_record["STATE"],
            "county_fips": expected_record["COUNTY"],
            "internal_point": {"longitude": expected_record["INTPTLON"], "latitude": expected_record["INTPTLAT"]},
        },
        "lubbock_isolation": {
            "service_url": lubbock_url,
            "district_field": lubbock["district_field"],
            "point_query_url": final_lubbock_url,
            "point_query_http_status": lubbock_status,
            "feature_count": 0,
            "live_matches": [],
            "jurisdiction_present": False,
            "district_assignments": 0,
            "applicable_offices": 0,
            "coverage_rows": 0,
            "district_office_joins": 0,
            "actions": 0,
        },
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "county": proof["county"],
        "county_geoid": proof["county_geoid"],
        "observed_on": proof["observed_on"],
        "candidate_spec_sha256": _sha(candidate),
        "cg04_proof_spec_sha256": _sha(roster_proof),
        "cg05_proof_spec_sha256": _sha(gis_proof),
        "cg06_proof_spec_sha256": _sha(interior_proof),
        "proof_spec_sha256": proof_sha,
        "prior_cg06": proof["prior_cg06"],
        "decision": "GO",
        "result": "SUPPORTED_V0_1",
        "stop_class": "NONE",
        "architecture_change": "NO",
        "gates": [
            {"gate": "CG-01", "status": "PASS"},
            {"gate": "CG-02", "status": "PASS"},
            {"gate": "CG-03", "status": "PASS"},
            {"gate": "CG-04", "status": "PASS"},
            {"gate": "CG-05", "status": "PASS"},
            {"gate": "CG-06", "status": "PASS"},
            {"gate": "CG-07", "status": "PASS"},
            {"gate": "CG-08", "status": "READY"},
            {"gate": "CG-09", "status": "READY"},
            {"gate": "CG-10", "status": "READY"},
        ],
        "cg07_outside_negative": outside_evidence,
        "stopped_before": "CG-08",
        "packaged": False,
        "actions": "NOT_YET_RELEASED",
        "production_runtime_changed": False,
    }
    if output_dir is None:
        raise ValueError("--output-dir is required unless --validate-only is set")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "lubbock-cg07-evidence.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CG-07",
                "census_county_geoid": expected_record["GEOID"],
                "census_county_matches": len(county_matches),
                "lubbock_precinct_matches": len(lubbock_features),
                "lubbock_applicable_offices": 0,
                "geocoder_used": False,
                "address_input_used": False,
                "stopped_before": "CG-08",
                "proof_spec_sha256": proof_sha,
                "evidence_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("cg04_roster_proof", type=Path)
    parser.add_argument("cg05_gis_proof", type=Path)
    parser.add_argument("cg06_interior_proof", type=Path)
    parser.add_argument("cg07_proof", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    run(
        args.candidate,
        args.cg04_roster_proof,
        args.cg05_gis_proof,
        args.cg06_interior_proof,
        args.cg07_proof,
        args.output_dir,
        validate_only=args.validate_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
