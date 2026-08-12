#!/usr/bin/env python3
"""Live, coordinate-only Lubbock County CG-08 boundary proof.

The proof derives a frozen shared segment from the official four-polygon
precinct layer. Its midpoint receives a one-meter topology probe that sees
Precincts 1 and 4, so all three shared district families fail closed without a
tie-break. Two opposite-side controls must restore distinct precincts. No
address, geocoder, package, action route, or production mutation is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


SCHEMA_VERSION = "civic-gps-lubbock-cg08-proof/0.1.0"
USER_AGENT = "Mozilla/5.0 CivicData-CivicGPS-CG08/0.1 (+https://github.com/MightyLoud/CivicData)"
EXPECTED_CANDIDATE_SHA = "20dad659a7bb3b9cfcd8ec5979827eed328aeb346bd42287dce2a6247b655fe2"
EXPECTED_CG04_PROOF_SHA = "d7d2b10a7837d651c21a2409d89de42c57bbb21d219f9ee9ee0ac35042cb3f45"
EXPECTED_CG05_PROOF_SHA = "dd03ed2106b9a00f4b3fb47add5c2136bb4e55490395714cae81b8763832438e"
EXPECTED_CG06_PROOF_SHA = "46cdf29a9164377dec9720a5587e03d8106a5e281fa5c7f004b6d9b3a27e0bf8"
EXPECTED_CG07_PROOF_SHA = "9566b47c55f8b4ff2fc82c3e94886acf4d1503169c6bb8de6379e12d704b43d7"
EXPECTED_CG07_EVIDENCE_SHA = "e569d97f26a862c154f95d7d111b4464a8665966476f51496e73d93202fd57d2"


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


def _point_key(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rounded_point(point: list[float] | tuple[float, float], decimals: int) -> tuple[float, float]:
    return (round(float(point[0]), decimals), round(float(point[1]), decimals))


def _point_query(
    service_url: str,
    field: str,
    point: tuple[float, float],
    allowed_hosts: set[str],
    *,
    distance_meters: int | None,
) -> tuple[list[str], str, int]:
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
    result, final_url, status = _fetch_json(_query_url(service_url, params), allowed_hosts)
    keys = sorted(
        {
            _point_key((feature.get("attributes") or {}).get(field))
            for feature in result.get("features") or []
            if (feature.get("attributes") or {}).get(field) not in (None, "")
        },
        key=int,
    )
    return keys, final_url, status


def _shared_segments(features: list[dict[str, Any]], field: str, decimals: int) -> list[dict[str, Any]]:
    index: dict[tuple[tuple[float, float], tuple[float, float]], list[tuple[str, tuple[float, float], tuple[float, float]]]] = {}
    for feature in features:
        district = _point_key((feature.get("attributes") or {}).get(field))
        for ring in (feature.get("geometry") or {}).get("rings") or []:
            for left_raw, right_raw in zip(ring, ring[1:]):
                left = (float(left_raw[0]), float(left_raw[1]))
                right = (float(right_raw[0]), float(right_raw[1]))
                rounded_left = _rounded_point(left, decimals)
                rounded_right = _rounded_point(right, decimals)
                if rounded_left == rounded_right:
                    continue
                key = tuple(sorted((rounded_left, rounded_right)))
                index.setdefault(key, []).append((district, left, right))
    shared: list[dict[str, Any]] = []
    for rounded_endpoints, rows in index.items():
        districts = sorted({row[0] for row in rows}, key=int)
        if len(districts) < 2:
            continue
        left, right = rows[0][1], rows[0][2]
        shared.append(
            {
                "rounded_endpoints": rounded_endpoints,
                "district_keys": districts,
                "left": left,
                "right": right,
                "length_degrees": math.hypot(right[0] - left[0], right[1] - left[1]),
            }
        )
    return sorted(shared, key=lambda row: row["length_degrees"], reverse=True)


def _validate(
    candidate: dict[str, Any],
    roster_proof: dict[str, Any],
    gis_proof: dict[str, Any],
    interior_proof: dict[str, Any],
    outside_proof: dict[str, Any],
    proof: dict[str, Any],
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"proof schema_version must be {SCHEMA_VERSION}")
    if proof.get("county") != candidate["county"]["name"] or str(proof.get("county_geoid")) != str(candidate["county"]["geoid"]):
        raise ValueError("candidate/proof county or GEOID mismatch")
    expected_shas = {
        "candidate_spec_sha256": (candidate, EXPECTED_CANDIDATE_SHA),
        "cg04_proof_spec_sha256": (roster_proof, EXPECTED_CG04_PROOF_SHA),
        "cg05_proof_spec_sha256": (gis_proof, EXPECTED_CG05_PROOF_SHA),
        "cg06_proof_spec_sha256": (interior_proof, EXPECTED_CG06_PROOF_SHA),
        "cg07_proof_spec_sha256": (outside_proof, EXPECTED_CG07_PROOF_SHA),
    }
    for field, (value, expected) in expected_shas.items():
        actual = _sha(value)
        if proof.get(field) != expected or actual != expected:
            raise ValueError(f"{field} mismatch: proof={proof.get(field)} actual={actual}")
    expected_prior = {
        "status": "PASS",
        "head_sha": "786730759180b8ddfc3c0bddacbee972a273048c",
        "run_id": 31567285269,
        "job_id": 94021819722,
        "evidence_sha256": EXPECTED_CG07_EVIDENCE_SHA,
    }
    if proof.get("prior_cg07") != expected_prior:
        raise ValueError("CG-08 requires the exact frozen CG-07 PASS baseline")
    if proof.get("stop_before") != "CG-09":
        raise ValueError("CG-08 must stop before CG-09")
    if proof.get("input_mode") != "OFFICIAL_POLYGON_TOPOLOGY_COORDINATE_ONLY":
        raise ValueError("CG-08 input mode must remain coordinate-only")
    if any(proof.get(field) is not False for field in ("geocoder_used", "address_input_used", "personal_data_used")):
        raise ValueError("CG-08 may not use a geocoder, address input, or personal data")

    gis = proof.get("gis") or {}
    allowed_hosts = {str(host).casefold() for host in gis.get("official_hosts") or []}
    if allowed_hosts != {"gisserver.halff.com"}:
        raise ValueError("CG-08 official-host allowlist changed")
    _require_official(str(gis.get("service_url")), allowed_hosts)
    if gis.get("service_url") != gis_proof["gis"]["service_url"] or gis.get("service_url") != interior_proof["gis"]["service_url"]:
        raise ValueError("CG-08/CG-05/CG-06 service mismatch")
    if gis.get("service_url") != outside_proof["lubbock_gis"]["service_url"]:
        raise ValueError("CG-08/CG-07 Lubbock service mismatch")
    if gis.get("district_field") != "District_ID" or gis.get("district_keys") != ["1", "2", "3", "4"]:
        raise ValueError("CG-08 district-field/key contract changed")
    if gis.get("boundary_policy") != "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK":
        raise ValueError("CG-08 boundary policy changed")
    if gis.get("boundary_probe_distance_meters") != 1 or gis.get("boundary_probe_units") != "esriSRUnit_Meter":
        raise ValueError("CG-08 one-meter topology probe changed")
    if gis.get("out_sr") != 4326 or gis.get("segment_match_decimals") != 8 or gis.get("point_precision_decimals") != 12:
        raise ValueError("CG-08 coordinate contract changed")

    families = candidate["district_families"]
    expected_families = ["commissioner", "justice_of_the_peace", "constable"]
    if [row["family"] for row in families] != expected_families:
        raise ValueError("CG-08 district-family scope changed")
    for family in families:
        if family["geometry"]["service_url"] != gis["service_url"] or family["geometry"]["district_field"] != gis["district_field"]:
            raise ValueError(f"CG-08 shared-geometry contract changed for {family['family']}")
    if candidate["controls"]["boundary"]["policy"] != gis["boundary_policy"]:
        raise ValueError("candidate/CG-08 boundary policy mismatch")
    if candidate["controls"]["boundary"]["shared_geometry_families"] != expected_families:
        raise ValueError("candidate/CG-08 shared-family contract mismatch")

    control = proof.get("control") or {}
    expected_control = {
        "id": "lubbock-pct1-pct4-longest-shared-segment",
        "shared_district_keys": ["1", "4"],
        "segment_a": [-102.02643885485786, 33.56141363989066],
        "segment_b": [-102.00910785105708, 33.561436640396856],
        "midpoint": [-102.01777335295748, 33.561425140143754],
        "expected_exact_point_keys": ["1"],
        "expected_one_meter_probe_keys": ["1", "4"],
        "side_offset_degrees": 0.00002,
        "side_a": {
            "point": [-102.01777337950007, 33.56144514012614],
            "expected_key": "4",
        },
        "side_b": {
            "point": [-102.01777332641488, 33.56140514016137],
            "expected_key": "1",
        },
    }
    if control != expected_control:
        raise ValueError("CG-08 frozen topology control changed")
    expected_outcome = {
        "conflict_family_count": 3,
        "district_assignments": 0,
        "district_office_joins": 0,
        "countywide_applicable_offices": 6,
        "total_applicable_offices": 6,
        "actions": 0,
        "side_applicable_offices_each": 9,
        "side_district_office_joins_each": 3,
    }
    if proof.get("expected_outcome") != expected_outcome:
        raise ValueError("CG-08 fail-closed outcome changed")

    records = (roster_proof.get("canonical_roster") or {}).get("records") or []
    roster_by_office = {str(row["office_id"]): row for row in records}
    if len(records) != 18 or len(roster_by_office) != 18:
        raise ValueError("CG-08 requires the exact 18-record canonical roster")
    return allowed_hosts, roster_by_office


def run(
    candidate_path: Path,
    roster_path: Path,
    gis_path: Path,
    interior_path: Path,
    outside_path: Path,
    proof_path: Path,
    output_dir: Path | None,
    *,
    validate_only: bool,
) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    roster_proof = json.loads(roster_path.read_text(encoding="utf-8"))
    gis_proof = json.loads(gis_path.read_text(encoding="utf-8"))
    interior_proof = json.loads(interior_path.read_text(encoding="utf-8"))
    outside_proof = json.loads(outside_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    allowed_hosts, roster_by_office = _validate(
        candidate, roster_proof, gis_proof, interior_proof, outside_proof, proof
    )
    proof_sha = _sha(proof)
    if validate_only:
        summary = {
            "status": "VALID",
            "gate": "CG-08",
            "candidate_spec_sha256": _sha(candidate),
            "proof_spec_sha256": proof_sha,
            "input_mode": proof["input_mode"],
            "boundary_probe_distance_meters": proof["gis"]["boundary_probe_distance_meters"],
            "geocoder_used": False,
            "address_input_used": False,
            "personal_data_used": False,
            "stopped_before": "CG-09",
        }
        print(json.dumps(summary, sort_keys=True))
        return summary

    gis = proof["gis"]
    control = proof["control"]
    service_url = str(gis["service_url"]).rstrip("/")
    polygon_url = _query_url(
        service_url,
        {
            "where": "1=1",
            "outFields": gis["district_field"],
            "returnGeometry": "true",
            "outSR": str(gis["out_sr"]),
            "orderByFields": f"{gis['district_field']} ASC",
            "f": "json",
        },
    )
    polygon_result, final_polygon_url, polygon_status = _fetch_json(polygon_url, allowed_hosts)
    features = polygon_result.get("features") or []
    live_keys = sorted(
        {_point_key((feature.get("attributes") or {}).get(gis["district_field"])) for feature in features},
        key=int,
    )
    if len(features) != 4 or live_keys != gis["district_keys"]:
        raise ValueError(f"CG-08 live polygon keys/features changed: {live_keys}/{len(features)}")
    normalized_geometry = sorted(
        [
            {
                "district_key": _point_key((feature.get("attributes") or {}).get(gis["district_field"])),
                "rings": (feature.get("geometry") or {}).get("rings"),
            }
            for feature in features
        ],
        key=lambda row: int(row["district_key"]),
    )
    shared = _shared_segments(features, gis["district_field"], gis["segment_match_decimals"])
    if not shared:
        raise ValueError("CG-08 live geometry has no shared precinct segments")
    frozen_key = tuple(
        sorted(
            (
                _rounded_point(control["segment_a"], gis["segment_match_decimals"]),
                _rounded_point(control["segment_b"], gis["segment_match_decimals"]),
            )
        )
    )
    matches = [row for row in shared if row["rounded_endpoints"] == frozen_key]
    if len(matches) != 1:
        raise ValueError(f"CG-08 frozen shared segment missing or duplicated: {len(matches)}")
    segment = matches[0]
    if segment["district_keys"] != control["shared_district_keys"]:
        raise ValueError("CG-08 frozen segment district topology changed")
    if segment["rounded_endpoints"] != shared[0]["rounded_endpoints"]:
        raise ValueError("CG-08 frozen segment is no longer the longest official shared segment")
    computed_midpoint = (
        (float(control["segment_a"][0]) + float(control["segment_b"][0])) / 2.0,
        (float(control["segment_a"][1]) + float(control["segment_b"][1])) / 2.0,
    )
    if _rounded_point(computed_midpoint, 12) != _rounded_point(control["midpoint"], 12):
        raise ValueError("CG-08 frozen midpoint is not the segment midpoint")

    midpoint = tuple(float(value) for value in control["midpoint"])
    exact_keys, exact_url, exact_status = _point_query(
        service_url, gis["district_field"], midpoint, allowed_hosts, distance_meters=None
    )
    probe_keys, probe_url, probe_status = _point_query(
        service_url,
        gis["district_field"],
        midpoint,
        allowed_hosts,
        distance_meters=gis["boundary_probe_distance_meters"],
    )
    if exact_keys != control["expected_exact_point_keys"]:
        raise ValueError(f"CG-08 exact midpoint behavior changed: {exact_keys}")
    if probe_keys != control["expected_one_meter_probe_keys"]:
        raise ValueError(f"CG-08 one-meter midpoint topology changed: {probe_keys}")
    if exact_keys == probe_keys or len(probe_keys) < 2:
        raise ValueError("CG-08 topology probe did not force a fail-closed conflict")

    families = candidate["district_families"]
    side_evidence: list[dict[str, Any]] = []
    restored_office_ids: set[str] = set()
    for side_name in ("side_a", "side_b"):
        frozen_side = control[side_name]
        point = tuple(float(value) for value in frozen_side["point"])
        expected_key = str(frozen_side["expected_key"])
        side_exact, side_exact_url, side_exact_status = _point_query(
            service_url, gis["district_field"], point, allowed_hosts, distance_meters=None
        )
        side_probe, side_probe_url, side_probe_status = _point_query(
            service_url,
            gis["district_field"],
            point,
            allowed_hosts,
            distance_meters=gis["boundary_probe_distance_meters"],
        )
        if side_exact != [expected_key] or side_probe != [expected_key]:
            raise ValueError(f"CG-08 {side_name} did not restore exactly key {expected_key}: {side_exact}/{side_probe}")
        joins = []
        for family in families:
            office_id = str(family["office_id_template"]).format(district=expected_key)
            title = str(family["office_title_template"]).format(district=expected_key)
            holder = str(family["holders"][expected_key])
            record = roster_by_office.get(office_id)
            if not record or record.get("title") != title or record.get("holder") != holder:
                raise ValueError(f"CG-08 {side_name} canonical roster join failed for {office_id}")
            restored_office_ids.add(office_id)
            joins.append(
                {
                    "family": family["family"],
                    "adapter_id": family["adapter_id"],
                    "district_key": expected_key,
                    "office_id": office_id,
                    "title": title,
                    "holder": holder,
                    "source_url": record["source_url"],
                }
            )
        side_evidence.append(
            {
                "side": side_name,
                "point": list(point),
                "expected_key": expected_key,
                "exact_keys": side_exact,
                "one_meter_probe_keys": side_probe,
                "district_assignments": 3,
                "district_office_joins": joins,
                "applicable_offices": 9,
                "applicable_composition": {"countywide": 6, "district": 3},
                "exact_query_url": side_exact_url,
                "exact_query_http_status": side_exact_status,
                "probe_query_url": side_probe_url,
                "probe_query_http_status": side_probe_status,
                "status": "PASS",
            }
        )
    if len(restored_office_ids) != 6:
        raise ValueError(f"CG-08 two-sided restoration must prove six unique district office joins, got {len(restored_office_ids)}")

    countywide_ids = [str(row["office_id"]) for row in candidate["scope"]["countywide_offices"]]
    if len(countywide_ids) != 6 or any(office_id not in roster_by_office for office_id in countywide_ids):
        raise ValueError("CG-08 countywide canonical join is incomplete")
    conflict_rows = [
        {
            "adapter_id": family["adapter_id"],
            "family": family["family"],
            "layer": family["layer"],
            "status": "CONFLICT",
            "matched_keys": probe_keys,
            "policy": gis["boundary_policy"],
        }
        for family in families
    ]
    boundary_evidence = {
        "status": "PASS",
        "input_mode": proof["input_mode"],
        "test_data_class": "PUBLIC_OFFICIAL_POLYGON_TOPOLOGY_COORDINATES_ONLY",
        "geocoder_used": False,
        "address_input_used": False,
        "personal_data_used": False,
        "service_url": service_url,
        "district_field": gis["district_field"],
        "boundary_policy": gis["boundary_policy"],
        "boundary_probe_distance_meters": gis["boundary_probe_distance_meters"],
        "boundary_probe_units": gis["boundary_probe_units"],
        "polygon_query_url": final_polygon_url,
        "polygon_query_http_status": polygon_status,
        "live_polygon_geometry_sha256": _sha(normalized_geometry),
        "feature_count": len(features),
        "keys_covered": live_keys,
        "shared_segment_count": len(shared),
        "control_id": control["id"],
        "shared_segment": {
            "segment_a": control["segment_a"],
            "segment_b": control["segment_b"],
            "length_degrees": round(segment["length_degrees"], 12),
            "district_keys": segment["district_keys"],
            "longest_shared_segment": True,
        },
        "exact_boundary": {
            "point": list(midpoint),
            "exact_point_keys": exact_keys,
            "one_meter_probe_keys": probe_keys,
            "exact_query_url": exact_url,
            "exact_query_http_status": exact_status,
            "probe_query_url": probe_url,
            "probe_query_http_status": probe_status,
            "decision": "CONFLICT",
            "tie_break_used": False,
            "conflict_rows": conflict_rows,
            "conflict_family_count": len(conflict_rows),
            "district_assignments": 0,
            "district_office_joins": 0,
            "countywide_applicable_office_ids": countywide_ids,
            "countywide_applicable_offices": 6,
            "total_applicable_offices": 6,
            "actions": 0,
        },
        "side_offset_degrees": control["side_offset_degrees"],
        "side_controls": side_evidence,
        "side_unique_restored_district_office_joins": len(restored_office_ids),
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
        "cg07_proof_spec_sha256": _sha(outside_proof),
        "proof_spec_sha256": proof_sha,
        "prior_cg07": proof["prior_cg07"],
        "decision": "GO",
        "result": "SUPPORTED_V0_1",
        "stop_class": "NONE",
        "architecture_change": "NO",
        "gates": [
            {"gate": f"CG-{gate:02d}", "status": "PASS" if gate <= 8 else "READY"}
            for gate in range(1, 11)
        ],
        "cg08_boundary_fail_closed": boundary_evidence,
        "stopped_before": "CG-09",
        "packaged": False,
        "actions": "NOT_YET_RELEASED",
        "production_runtime_changed": False,
    }
    if output_dir is None:
        raise ValueError("--output-dir is required unless --validate-only is set")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "lubbock-cg08-evidence.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CG-08",
                "exact_point_keys": exact_keys,
                "one_meter_probe_keys": probe_keys,
                "conflict_families": len(conflict_rows),
                "district_assignments": 0,
                "district_office_joins": 0,
                "countywide_applicable_offices": 6,
                "side_restored_keys": [row["expected_key"] for row in side_evidence],
                "geocoder_used": False,
                "address_input_used": False,
                "stopped_before": "CG-09",
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
    parser.add_argument("cg07_outside_proof", type=Path)
    parser.add_argument("cg08_proof", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    run(
        args.candidate,
        args.cg04_roster_proof,
        args.cg05_gis_proof,
        args.cg06_interior_proof,
        args.cg07_outside_proof,
        args.cg08_proof,
        args.output_dir,
        validate_only=args.validate_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
