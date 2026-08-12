#!/usr/bin/env python3
"""Live, coordinate-only Lubbock County CG-06 interior-control proof.

The proof downloads the four official precinct polygons, recomputes a stable
area centroid for each polygon, and requires every frozen coordinate to resolve
back to exactly one matching District_ID. It then joins that district key to
the already-governed canonical Commissioner, JP, and Constable records. No
address, geocoder, packaged runtime, action route, or production mutation is
used.
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


SCHEMA_VERSION = "civic-gps-lubbock-cg06-proof/0.1.0"
USER_AGENT = "Mozilla/5.0 CivicData-CivicGPS-CG06/0.1 (+https://github.com/MightyLoud/CivicData)"
EXPECTED_CANDIDATE_SHA = "20dad659a7bb3b9cfcd8ec5979827eed328aeb346bd42287dce2a6247b655fe2"
EXPECTED_CG04_PROOF_SHA = "d7d2b10a7837d651c21a2409d89de42c57bbb21d219f9ee9ee0ac35042cb3f45"
EXPECTED_CG05_PROOF_SHA = "dd03ed2106b9a00f4b3fb47add5c2136bb4e55490395714cae81b8763832438e"
EXPECTED_CG05_EVIDENCE_SHA = "6cb9e93249137da6e7c00b694f4d9203127abcbde8858095cecf53adea9d25e2"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _same_url(left: str, right: str) -> bool:
    return left.rstrip("/").casefold() == right.rstrip("/").casefold()


def _require_official(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in allowed_hosts:
        raise ValueError(f"non-official or unbound source URL: {url}")


def _fetch_json(url: str, allowed_hosts: set[str], *, attempts: int = 3) -> tuple[dict[str, Any], str, int]:
    _require_official(url, allowed_hosts)
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json,*/*;q=0.8",
                    "Referer": "https://www.lubbockcounty.gov/",
                },
            )
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


def _area_centroid(ring: list[list[float]]) -> tuple[float, float]:
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("CG-06 requires a closed polygon ring")
    twice_area = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for left, right in zip(ring, ring[1:]):
        cross = left[0] * right[1] - right[0] * left[1]
        twice_area += cross
        x_sum += (left[0] + right[0]) * cross
        y_sum += (left[1] + right[1]) * cross
    if abs(twice_area) < 1e-15:
        raise ValueError("CG-06 polygon ring has zero area")
    return x_sum / (3.0 * twice_area), y_sum / (3.0 * twice_area)


def _point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    x, y = point
    inside = False
    for left, right in zip(ring, ring[1:]):
        x1, y1 = left
        x2, y2 = right
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def _segment_distance(point: tuple[float, float], left: list[float], right: list[float]) -> float:
    x, y = point
    vx = right[0] - left[0]
    vy = right[1] - left[1]
    denominator = vx * vx + vy * vy
    if denominator == 0:
        return math.hypot(x - left[0], y - left[1])
    projection = ((x - left[0]) * vx + (y - left[1]) * vy) / denominator
    projection = max(0.0, min(1.0, projection))
    near_x = left[0] + projection * vx
    near_y = left[1] + projection * vy
    return math.hypot(x - near_x, y - near_y)


def _boundary_clearance(point: tuple[float, float], ring: list[list[float]]) -> float:
    return min(_segment_distance(point, left, right) for left, right in zip(ring, ring[1:]))


def _validate(
    candidate: dict[str, Any],
    roster_proof: dict[str, Any],
    gis_proof: dict[str, Any],
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
    }
    for field, (value, expected) in expected_shas.items():
        actual = _sha(value)
        if proof.get(field) != expected or actual != expected:
            raise ValueError(f"{field} mismatch: proof={proof.get(field)} actual={actual}")
    prior = proof.get("prior_cg05") or {}
    if prior.get("status") != "PASS" or prior.get("evidence_sha256") != EXPECTED_CG05_EVIDENCE_SHA:
        raise ValueError("CG-06 requires the frozen CG-05 PASS evidence")
    if prior.get("head_sha") != "6ff5f5f192428b43fdd467ab0588903355e41b6d" or prior.get("run_id") != 31564494846:
        raise ValueError("unexpected CG-05 exact-head baseline")
    if proof.get("stop_before") != "CG-07":
        raise ValueError("CG-06 must stop before CG-07")
    if proof.get("input_mode") != "OFFICIAL_POLYGON_COORDINATE_ONLY":
        raise ValueError("CG-06 input mode must remain coordinate-only")
    if proof.get("geocoder_used") is not False or proof.get("address_input_used") is not False:
        raise ValueError("CG-06 may not use a geocoder or address input")

    gis = proof["gis"]
    prior_gis = gis_proof["gis"]
    for field in ("service_url", "district_field", "district_keys"):
        if gis[field] != prior_gis[field]:
            raise ValueError(f"CG-06/CG-05 GIS contract mismatch: {field}")
    if gis.get("out_sr") != 4326 or gis.get("point_precision_decimals") != 8:
        raise ValueError("CG-06 coordinate reference or precision changed")
    if gis.get("point_generation_method") != "ESRI_RING_SIGNED_AREA_CENTROID":
        raise ValueError("CG-06 point-generation method changed")
    if float(gis.get("minimum_boundary_clearance_degrees", 0)) < 0.01:
        raise ValueError("CG-06 frozen controls are not sufficiently interior")

    allowed_hosts = {str(host).casefold() for host in gis["official_hosts"]}
    _require_official(str(gis["service_url"]), allowed_hosts)
    families = candidate["district_families"]
    expected_families = ["commissioner", "justice_of_the_peace", "constable"]
    if [row["family"] for row in families] != expected_families:
        raise ValueError("CG-06 district-family order or scope changed")
    for family in families:
        if not _same_url(str(family["geometry"]["service_url"]), str(gis["service_url"])):
            raise ValueError(f"CG-06 service mismatch for {family['family']}")
        if family["geometry"]["district_field"] != gis["district_field"]:
            raise ValueError(f"CG-06 field mismatch for {family['family']}")
        if [str(value) for value in family["district_keys"]] != list(gis["district_keys"]):
            raise ValueError(f"CG-06 key mismatch for {family['family']}")
        if family["resolver_kind"] != "ARCGIS_POINT_INTERSECT":
            raise ValueError(f"CG-06 resolver mismatch for {family['family']}")

    controls = proof.get("controls") or []
    expected_keys = list(gis["district_keys"])
    if [str(row.get("district_key")) for row in controls] != expected_keys:
        raise ValueError("CG-06 must freeze exactly one ordered control for keys 1-4")
    if len({row.get("id") for row in controls}) != 4:
        raise ValueError("CG-06 control IDs must be unique")
    for row in controls:
        point = row.get("point") or []
        if len(point) != 2 or not all(isinstance(value, (int, float)) for value in point):
            raise ValueError(f"invalid CG-06 point for {row.get('id')}")
        if row.get("expected_ring_count") != 1:
            raise ValueError("CG-06 frozen geometry contract must remain one ring per precinct")

    canonical = roster_proof.get("canonical_roster") or {}
    records = canonical.get("records") or []
    by_office = {str(row["office_id"]): row for row in records}
    if canonical.get("identity_source_rule") != "CANONICAL_RELEASE_ONLY":
        raise ValueError("CG-06 canonical identity-source rule changed")
    if len(records) != 18 or len(by_office) != 18:
        raise ValueError("CG-06 requires the exact 18-record canonical roster")
    return allowed_hosts, by_office


def run(
    candidate_path: Path,
    roster_path: Path,
    gis_path: Path,
    proof_path: Path,
    output_dir: Path | None,
    *,
    validate_only: bool,
) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    roster_proof = json.loads(roster_path.read_text(encoding="utf-8"))
    gis_proof = json.loads(gis_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    allowed_hosts, roster_by_office = _validate(candidate, roster_proof, gis_proof, proof)
    proof_sha = _sha(proof)
    if validate_only:
        summary = {
            "status": "VALID",
            "gate": "CG-06",
            "candidate_spec_sha256": _sha(candidate),
            "proof_spec_sha256": proof_sha,
            "control_count": len(proof["controls"]),
            "input_mode": proof["input_mode"],
            "geocoder_used": False,
            "stopped_before": "CG-07",
        }
        print(json.dumps(summary, sort_keys=True))
        return summary

    gis = proof["gis"]
    service_url = str(gis["service_url"]).rstrip("/")
    polygon_params = {
        "where": "1=1",
        "outFields": gis["district_field"],
        "returnGeometry": "true",
        "outSR": str(gis["out_sr"]),
        "orderByFields": f"{gis['district_field']} ASC",
        "f": "json",
    }
    polygon_query_url = service_url + "/query?" + urlencode(polygon_params)
    polygon_result, final_polygon_url, polygon_status = _fetch_json(polygon_query_url, allowed_hosts)
    features = polygon_result.get("features") or []
    feature_by_key: dict[str, dict[str, Any]] = {}
    normalized_geometry: list[dict[str, Any]] = []
    for feature in features:
        key = str((feature.get("attributes") or {}).get(gis["district_field"]))
        if key in feature_by_key:
            raise ValueError(f"duplicate live precinct key: {key}")
        feature_by_key[key] = feature
        normalized_geometry.append({"district_key": key, "rings": (feature.get("geometry") or {}).get("rings")})
    expected_keys = list(gis["district_keys"])
    if sorted(feature_by_key, key=int) != expected_keys or len(features) != 4:
        raise ValueError(f"CG-06 live polygon keys/features changed: {sorted(feature_by_key)}/{len(features)}")

    countywide_ids = [str(row["office_id"]) for row in candidate["scope"]["countywide_offices"]]
    if len(countywide_ids) != 6 or any(office_id not in roster_by_office for office_id in countywide_ids):
        raise ValueError("CG-06 countywide canonical join is incomplete")

    families = candidate["district_families"]
    control_evidence: list[dict[str, Any]] = []
    joined_office_ids: set[str] = set()
    for control in proof["controls"]:
        key = str(control["district_key"])
        geometry = feature_by_key[key].get("geometry") or {}
        rings = geometry.get("rings") or []
        if len(rings) != control["expected_ring_count"]:
            raise ValueError(f"[{control['id']}] ring count changed: {len(rings)}")
        ring = rings[0]
        centroid = _area_centroid(ring)
        rounded = tuple(round(value, gis["point_precision_decimals"]) for value in centroid)
        frozen = tuple(float(value) for value in control["point"])
        if tuple(f"{value:.8f}" for value in rounded) != tuple(f"{value:.8f}" for value in frozen):
            raise ValueError(f"[{control['id']}] official polygon centroid changed: {rounded} != {frozen}")
        if not _point_in_ring(frozen, ring):
            raise ValueError(f"[{control['id']}] frozen control is not inside its official polygon")
        clearance = _boundary_clearance(frozen, ring)
        if clearance < float(gis["minimum_boundary_clearance_degrees"]):
            raise ValueError(f"[{control['id']}] boundary clearance fell below the governed minimum: {clearance}")

        point_params = {
            "geometry": f"{frozen[0]:.8f},{frozen[1]:.8f}",
            "geometryType": "esriGeometryPoint",
            "inSR": str(gis["out_sr"]),
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": gis["district_field"],
            "returnGeometry": "false",
            "f": "json",
        }
        point_query_url = service_url + "/query?" + urlencode(point_params)
        point_result, final_point_url, point_status = _fetch_json(point_query_url, allowed_hosts)
        matches = sorted(
            {
                str((feature.get("attributes") or {}).get(gis["district_field"]))
                for feature in point_result.get("features") or []
            },
            key=int,
        )
        if matches != [key]:
            raise ValueError(f"[{control['id']}] expected exactly key {key}, got {matches}")

        joins: list[dict[str, Any]] = []
        for family in families:
            office_id = str(family["office_id_template"]).format(district=key)
            title = str(family["office_title_template"]).format(district=key)
            holder = str(family["holders"][key])
            record = roster_by_office.get(office_id)
            if not record or record.get("title") != title or record.get("holder") != holder:
                raise ValueError(f"[{control['id']}] canonical roster join failed for {office_id}")
            joined_office_ids.add(office_id)
            joins.append(
                {
                    "family": family["family"],
                    "adapter_id": family["adapter_id"],
                    "district_key": key,
                    "office_id": office_id,
                    "title": title,
                    "holder": holder,
                    "source_url": record["source_url"],
                }
            )
        control_evidence.append(
            {
                "id": control["id"],
                "district_key": key,
                "point": [frozen[0], frozen[1]],
                "point_source": gis["point_generation_method"],
                "local_polygon_contains_point": True,
                "boundary_clearance_degrees": round(clearance, 8),
                "live_matches": matches,
                "canonical_joins": joins,
                "applicable_offices": 9,
                "applicable_composition": {"countywide": 6, "district": 3},
                "point_query_url": final_point_url,
                "http_status": point_status,
                "status": "PASS",
            }
        )

    if len(joined_office_ids) != 12:
        raise ValueError(f"CG-06 must prove 12 unique district office joins, got {len(joined_office_ids)}")
    geometry_sha = _sha(sorted(normalized_geometry, key=lambda row: int(row["district_key"])))
    interior_evidence = {
        "status": "PASS",
        "input_mode": proof["input_mode"],
        "test_data_class": "PUBLIC_OFFICIAL_GEOMETRY_COORDINATES_ONLY",
        "geocoder_used": False,
        "address_input_used": False,
        "service_url": service_url,
        "district_field": gis["district_field"],
        "point_generation_method": gis["point_generation_method"],
        "point_precision_decimals": gis["point_precision_decimals"],
        "polygon_query_url": final_polygon_url,
        "polygon_query_http_status": polygon_status,
        "live_polygon_geometry_sha256": geometry_sha,
        "feature_count": len(features),
        "keys_covered": expected_keys,
        "families": [row["family"] for row in families],
        "control_count": len(control_evidence),
        "canonical_join_count": len(joined_office_ids),
        "normal_applicable_offices": 9,
        "normal_composition": {"countywide": 6, "district": 3},
        "boundary_policy": gis_proof["gis"]["boundary_policy"],
        "controls": control_evidence,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "county": proof["county"],
        "county_geoid": proof["county_geoid"],
        "observed_on": proof["observed_on"],
        "candidate_spec_sha256": _sha(candidate),
        "cg04_proof_spec_sha256": _sha(roster_proof),
        "cg05_proof_spec_sha256": _sha(gis_proof),
        "proof_spec_sha256": proof_sha,
        "prior_cg05": proof["prior_cg05"],
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
            {"gate": "CG-07", "status": "READY"},
            {"gate": "CG-08", "status": "READY"},
            {"gate": "CG-09", "status": "READY"},
            {"gate": "CG-10", "status": "READY"},
        ],
        "cg06_interior_controls": interior_evidence,
        "stopped_before": "CG-07",
        "packaged": False,
        "actions": "NOT_YET_RELEASED",
        "production_runtime_changed": False,
    }
    if output_dir is None:
        raise ValueError("--output-dir is required unless --validate-only is set")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "lubbock-cg06-evidence.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CG-06",
                "controls": len(control_evidence),
                "district_keys": expected_keys,
                "canonical_joins": len(joined_office_ids),
                "geocoder_used": False,
                "stopped_before": "CG-07",
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
    parser.add_argument("cg06_proof", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    run(
        args.candidate,
        args.cg04_roster_proof,
        args.cg05_gis_proof,
        args.cg06_proof,
        args.output_dir,
        validate_only=args.validate_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
