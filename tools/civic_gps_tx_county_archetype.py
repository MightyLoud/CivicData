#!/usr/bin/env python3
"""Build existing Civic GPS artifacts for Texas county precinct archetypes.

This is a build helper, not a new resolver. It emits the same release payload and
BASE bundle consumed by CivicGPSOverlayEngine v0.6.0.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

CANON = "UTF-8 JSON; object keys sorted for hashing; arrays sorted by stable identifiers where applicable"


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _district_office_id(template: str, key: str) -> str:
    return template.replace("{district}", str(int(key)))


def build_texas_county_precinct_artifacts(spec: dict) -> tuple[dict, dict]:
    """Return (release, registry_bundle) from one bounded county spec."""
    required = [
        "county_name", "county_geoid", "jurisdiction_id", "division_id",
        "adapter_id", "response_id_prefix", "release_filename",
        "snapshot_ref", "observed_on", "countywide_offices", "district_families",
    ]
    missing = [key for key in required if not spec.get(key)]
    if missing:
        raise ValueError(f"Missing county archetype fields: {missing}")

    jurisdiction_id = spec["jurisdiction_id"]
    division_id = spec["division_id"]
    offices: list[dict] = []
    holders: list[dict] = []
    wide_ids: list[str] = []

    for row in spec["countywide_offices"]:
        office_id = row["office_id"]
        wide_ids.append(office_id)
        offices.append({
            "coverage_class": "RELEASED_CURRENT",
            "jurisdiction_id": jurisdiction_id,
            "office_id": office_id,
            "official_url": row["official_url"],
            "title": row["title"],
        })
        holders.append({
            "canonical_name": row["holder"],
            "leadership_role": row.get("leadership_role"),
            "office_id": office_id,
            "selection_type": row.get("selection_type", "election"),
        })

    district_adapters: list[dict] = []
    coverage_rules: list[dict] = [{
        "layer": "county_government",
        "reason": f"{spec['county_name']} current elected-office release is joined.",
        "status": "RELEASE_BACKED",
        "when": {"jurisdiction_active": jurisdiction_id},
    }]

    for family in spec["district_families"]:
        keys = sorted((str(k) for k in family["holders"]), key=lambda x: int(x))
        for key in keys:
            office_id = _district_office_id(family["office_id_template"], key)
            offices.append({
                "coverage_class": "RELEASED_CURRENT",
                "jurisdiction_id": jurisdiction_id,
                "office_id": office_id,
                "official_url": family["official_url"],
                "title": family["office_title_template"].replace("{district}", str(int(key))),
            })
            holders.append({
                "canonical_name": family["holders"][key],
                "leadership_role": None,
                "office_id": office_id,
                "selection_type": family.get("selection_type", "election"),
            })

        district_adapters.append({
            "activation": {"jurisdiction_active": jurisdiction_id},
            "adapter_id": family["adapter_id"],
            "boundary_policy": "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK",
            "district_field": family["district_field"],
            "district_key_normalization": "NUMERIC",
            "district_name_template": family["district_name_template"],
            "division_id_template": family["division_id_template"],
            "division_type": family["division_type"],
            "endpoint_authority_class": family["endpoint_authority_class"],
            "endpoint_provenance_url": family["endpoint_provenance_url"],
            "endpoint_publisher": family["endpoint_publisher"],
            "failure_scope": "ADAPTER",
            "jurisdiction_id": jurisdiction_id,
            "layer": family["layer"],
            "office_id_template": family["office_id_template"],
            "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
            "parent_division_id": division_id,
            "query_enabled": True,
            "required": True,
            "resolution_method": "CENSUS_GEOCODE_PLUS_OFFICIAL_ARCGIS_POINT_INTERSECT",
            "resolver_kind": "ARCGIS_POINT_INTERSECT",
            "service_url": family["service_url"],
            "source_status": spec.get("source_status", "LIVE_ARCHETYPE_PROOF_PENDING"),
        })
        coverage_rules.append({
            "layer": family["layer"],
            "reason": family["coverage_reason"],
            "status": "RELEASE_BACKED",
            "when": {"district_resolved": family["adapter_id"]},
        })

    offices.sort(key=lambda row: row["office_id"])
    holders.sort(key=lambda row: row["office_id"])
    wide_ids.sort()

    release = {
        "meta": {
            "canonicalization": CANON,
            "note": spec["release_note"],
            "observed_on": spec["observed_on"],
            "release_status": spec.get("release_status", "PROBE_CURRENT"),
            "schema_version": "civic-gps-response/0.3.0",
            "source_manifest": spec.get("source_manifest"),
            "source_repository": spec.get("source_repository", spec["snapshot_ref"]),
        },
        "payload": {
            "action_links": [], "applicable_offices": [], "coverage": [], "district_assignments": [], "evidence": [], "input": {},
            "jurisdictions": [{
                "division_id": division_id,
                "government_type": "county",
                "jurisdiction_id": jurisdiction_id,
                "name": spec["county_name"],
                "office_count": len(offices),
                "snapshot_ref": spec["snapshot_ref"],
                "status": spec.get("release_status", "PROBE_CURRENT"),
            }],
            "known_gaps": [], "matched_divisions": [], "officeholders": holders, "offices": offices,
        },
    }
    release_no_hash = copy.deepcopy(release)
    release["meta"]["canonical_content_sha256"] = _sha(release_no_hash)

    coverage_rules.append({
        "layer": "federal_state_municipal_school_and_special_districts",
        "reason": f"This {spec['county_name']} BASE release does not claim completeness for other government layers.",
        "status": "OUT_OF_SCOPE",
        "when": {"always": True},
    })

    bundle = {
        "adapter_id": spec["adapter_id"],
        "applicable_office_rules": [{
            "include_resolved_district_offices": True,
            "jurisdiction_id": jurisdiction_id,
            "jurisdiction_wide_office_ids": wide_ids,
        }],
        "coverage_rules": coverage_rules,
        "district_adapters": district_adapters,
        "division_rules": [
            {"division_id": "div-us-tx", "name": "Texas", "parent_id": None, "type": "state", "when": {"equals": "48", "fields": ["GEOID", "STATE"], "geography": "state"}},
            {"division_id": division_id, "name": spec["county_name"], "parent_id": "div-us-tx", "type": "county", "when": {"equals": spec["county_geoid"], "fields": ["GEOID"], "geography": "county"}},
        ],
        "failure_scope": "RESPONSE",
        "jurisdictions": [{"activation": {"equals": spec["county_geoid"], "fields": ["GEOID"], "geography": "county"}, "jurisdiction_id": jurisdiction_id}],
        "known_gaps": copy.deepcopy(spec.get("known_gaps", [])),
        "mode": "BASE",
        "priority": int(spec.get("priority", 100)),
        "release_files": [spec["release_filename"]],
        "response_id_prefix": spec["response_id_prefix"],
        "scope_match": {"all": [
            {"equals": "48", "fields": ["GEOID", "STATE"], "geography": "state"},
            {"equals": spec["county_geoid"], "fields": ["GEOID"], "geography": "county"},
        ]},
    }
    return release, bundle


def write_artifacts(spec: dict, output_dir: Path) -> tuple[Path, dict]:
    release, bundle = build_texas_county_precinct_artifacts(spec)
    output_dir.mkdir(parents=True, exist_ok=True)
    release_path = output_dir / spec["release_filename"]
    release_path.write_text(json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return release_path, bundle
