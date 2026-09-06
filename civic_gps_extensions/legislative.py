"""Opt-in legislative geography. Each group resolves atomically, without civic facts."""
from __future__ import annotations

import copy
import re
from urllib.parse import urlencode, urlsplit


class GeographyFailure(ValueError):
    def __init__(self, code, status, message):
        self.code, self.status = code, status
        super().__init__(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_legislative_groups(groups, reserved_adapter_ids=(), reserved_jurisdiction_ids=()):
    if not isinstance(groups, list):
        raise ValueError("legislative_boundary_overlays must be a list")
    group_ids, adapter_ids, jurisdiction_ids, division_ids = set(), set(reserved_adapter_ids), set(reserved_jurisdiction_ids), set()
    for group in groups:
        if not isinstance(group, dict) or set(group) != {
            "group_id", "state_geoid", "jurisdiction", "district_adapters", "scope", "publication_eligible"
        }:
            raise ValueError("invalid legislative group fields")
        if group["scope"] != "INTERNAL_REVIEW" or group["publication_eligible"] is not False:
            raise ValueError("legislative groups are internal review only")
        gid = group["group_id"]
        if not _text(gid) or gid in group_ids:
            raise ValueError("duplicate or invalid legislative group ID")
        group_ids.add(gid)
        if not isinstance(group["state_geoid"], str) or not re.fullmatch(r"\d{2}", group["state_geoid"]):
            raise ValueError("state_geoid must be an exact two-digit string")
        jurisdiction = group["jurisdiction"]
        if not isinstance(jurisdiction, dict) or set(jurisdiction) != {"jurisdiction_id", "name"}:
            raise ValueError("legislative jurisdiction must contain geography fields only")
        jid = jurisdiction["jurisdiction_id"]
        if not _text(jid) or not _text(jurisdiction["name"]) or jid in jurisdiction_ids:
            raise ValueError("duplicate or invalid legislative jurisdiction")
        jurisdiction_ids.add(jid)
        adapters = group["district_adapters"]
        if not isinstance(adapters, list) or not adapters:
            raise ValueError("legislative district adapters are required")
        for adapter in adapters:
            required = {"adapter_id", "service_url", "district_field", "division_type",
                        "districts", "boundary_probe_distance_meters", "source"}
            if not isinstance(adapter, dict) or set(adapter) != required:
                raise ValueError("invalid legislative adapter fields")
            aid = adapter["adapter_id"]
            if not _text(aid) or aid in adapter_ids:
                raise ValueError("duplicate or invalid district adapter ID")
            adapter_ids.add(aid)
            if not _text(adapter["service_url"]):
                raise ValueError("legislative source URL is required")
            url = urlsplit(adapter["service_url"])
            if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
                raise ValueError("legislative source must be an HTTPS layer URL")
            if not _text(adapter["district_field"]) or adapter["division_type"] not in {"state_house_district", "state_senate_district"}:
                raise ValueError("invalid legislative district field/type")
            distance = adapter["boundary_probe_distance_meters"]
            if type(distance) not in (int, float) or not 0 < distance <= 10:
                raise ValueError("boundary probe must be greater than zero and at most 10 meters")
            source = adapter["source"]
            if not isinstance(source, dict) or set(source) != {"plan_id", "authority_url", "vintage_status"} or not all(_text(v) for v in source.values()):
                raise ValueError("explicit plan authority and vintage status are required")
            districts = adapter["districts"]
            if not isinstance(districts, dict) or not districts:
                raise ValueError("explicit canonical district map is required")
            for key, district in districts.items():
                if not isinstance(key, str) or not re.fullmatch(r"[1-9]\d*", key):
                    raise ValueError("district map keys must be canonical positive integer strings")
                if not isinstance(district, dict) or set(district) != {"division_id", "name"}:
                    raise ValueError("district mapping must contain geography fields only")
                did = district["division_id"]
                if not _text(did) or not _text(district["name"]) or did in division_ids:
                    raise ValueError("duplicate or invalid canonical district")
                division_ids.add(did)


def _one_key(body, field):
    features = body.get("features")
    if body.get("exceededTransferLimit") or not isinstance(features, list):
        raise GeographyFailure("INVALID_FEATURE_RESPONSE", "NOT_RESOLVED", "District response is malformed or truncated.")
    if len(features) == 0:
        raise GeographyFailure("DISTRICT_NOT_RESOLVED", "NOT_RESOLVED", "No polygon intersects the point.")
    if len(features) != 1:
        raise GeographyFailure("AMBIGUOUS_DISTRICT", "CONFLICT", "Multiple polygons intersect the point.")
    feature = features[0]
    attrs = feature.get("attributes") if isinstance(feature, dict) else None
    value = attrs.get(field) if isinstance(attrs, dict) else None
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()) and int(value) > 0:
        return str(int(value))
    raise GeographyFailure("DISTRICT_FIELD_INVALID", "NOT_RESOLVED", "District key is not a positive integer.")


def _query_adapter(engine, adapter, geocode):
    url = adapter["service_url"].rstrip("/") + "/query"
    params = {"where": "1=1", "geometry": f"{geocode['longitude']},{geocode['latitude']}",
              "geometryType": "esriGeometryPoint", "inSR": "4326",
              "spatialRel": "esriSpatialRelIntersects", "outFields": adapter["district_field"],
              "returnGeometry": "false", "f": "json"}
    key = _one_key(engine._get_json(url, params, adapter["adapter_id"]), adapter["district_field"])
    probe = dict(params, distance=adapter["boundary_probe_distance_meters"], units="esriSRUnit_Meter")
    probe_key = _one_key(engine._get_json(url, probe, adapter["adapter_id"]), adapter["district_field"])
    if key != probe_key:
        raise GeographyFailure("BOUNDARY_PROBE_INCONSISTENT", "CONFLICT", "Exact point and boundary probe disagree.")
    if key not in adapter["districts"]:
        raise GeographyFailure("DISTRICT_OUT_OF_SCOPE", "OUT_OF_SCOPE", "Resolved district is outside the configured canonical slice.")
    return key, [url + "?" + urlencode(params), url + "?" + urlencode(probe)]


def _failure(payload, group, failure):
    payload.setdefault("coverage", []).append({
        "layer": group["group_id"], "status": failure.status,
        "scope": "INTERNAL_REVIEW", "reason": str(failure),
    })
    payload.setdefault("known_gaps", []).append({
        "gap_id": "GAP-" + group["group_id"] + "-" + failure.code,
        "status": failure.status, "summary": str(failure),
    })


def apply_legislative_groups(engine, result, geocode, groups):
    """Add all geography in a group or none; preserve every existing civic fact."""
    out = copy.deepcopy(result)
    payload = out["payload"]
    for group in groups:
        states = geocode.get("geographies", {}).get("States")
        if not isinstance(states, list) or len(states) != 1 or not isinstance(states[0], dict):
            _failure(payload, group, GeographyFailure("STATE_UNRESOLVED", "NOT_RESOLVED", "Exactly one state geography is required."))
            continue
        state_keys = [states[0][key] for key in ("GEOID", "STATE") if states[0].get(key) not in (None, "")]
        if (not state_keys or any(not isinstance(key, str) or not re.fullmatch(r"\d{2}", key) for key in state_keys)
                or len(set(state_keys)) != 1):
            _failure(payload, group, GeographyFailure("STATE_UNRESOLVED", "NOT_RESOLVED", "State identity is missing or malformed."))
            continue
        state = state_keys[0]
        if state != group["state_geoid"]:
            _failure(payload, group, GeographyFailure("STATE_OUT_OF_SCOPE", "OUT_OF_SCOPE", "Address is outside the legislative group state."))
            continue
        pending_assignments, pending_divisions, pending_evidence = [], [], []
        jid = group["jurisdiction"]["jurisdiction_id"]
        try:
            for adapter in group["district_adapters"]:
                key, query_urls = _query_adapter(engine, adapter, geocode)
                district = adapter["districts"][key]
                pending_divisions.append({"division_id": district["division_id"], "name": district["name"],
                                          "parent_id": None, "type": adapter["division_type"]})
                pending_assignments.append({
                    "adapter_id": adapter["adapter_id"], "district_key": key,
                    "district_division_id": district["division_id"], "district_name": district["name"],
                    "jurisdiction_id": jid, "layer": adapter["division_type"], "status": "GEOGRAPHY_ONLY",
                    "resolution_method": "CENSUS_GEOCODE_PLUS_OFFICIAL_ARCGIS_POINT_INTERSECT",
                    "scope": "INTERNAL_REVIEW", "source_plan_id": adapter["source"]["plan_id"],
                    "source_vintage_status": adapter["source"]["vintage_status"],
                })
                for index, url in enumerate(query_urls):
                    pending_evidence.append({
                        "evidence_id": f"EVID-LEGISLATIVE-{adapter['adapter_id']}-{index}",
                        "supports": [f"district_assignments.{district['division_id']}"],
                        "url": url, "verified_on": result.get("meta", {}).get("observed_on"),
                        "source_plan_id": adapter["source"]["plan_id"],
                        "authority_url": adapter["source"]["authority_url"],
                    })
            existing_jids = {r.get("jurisdiction_id") for r in payload.get("jurisdictions", [])}
            existing_dids = {r.get("division_id") for r in payload.get("matched_divisions", [])}
            existing_aids = {r.get("adapter_id") for r in payload.get("district_assignments", [])}
            existing_eids = {r.get("evidence_id") for r in payload.get("evidence", [])}
            if (jid in existing_jids
                    or existing_dids & {r["division_id"] for r in pending_divisions}
                    or existing_aids & {r["adapter_id"] for r in pending_assignments}
                    or existing_eids & {r["evidence_id"] for r in pending_evidence}):
                raise GeographyFailure("IDENTITY_COLLISION", "CONFLICT", "Legislative geography collides with an existing result identity.")
        except GeographyFailure as exc:
            _failure(payload, group, exc)
            continue
        except Exception:
            _failure(payload, group, GeographyFailure("SOURCE_REQUEST_FAILED", "NOT_RESOLVED", "Legislative source request failed; no partial group was added."))
            continue
        payload.setdefault("jurisdictions", []).append(dict(group["jurisdiction"], coverage_class="GEOGRAPHY_ONLY"))
        payload.setdefault("matched_divisions", []).extend(pending_divisions)
        payload.setdefault("district_assignments", []).extend(pending_assignments)
        payload.setdefault("evidence", []).extend(pending_evidence)
        payload.setdefault("coverage", []).append({
            "layer": group["group_id"], "status": "GEOGRAPHY_ONLY", "scope": "INTERNAL_REVIEW",
            "complete_jurisdiction": False, "publication_eligible": False,
            "reason": "All configured legislative districts resolved; civic facts remain package-governed.",
        })
        payload.setdefault("known_gaps", []).append({
            "gap_id": "GAP-" + group["group_id"] + "-RELEASE", "status": "NOT_YET_RELEASED",
            "summary": "Internal geography candidate; geometry vintage and live integration gates remain separate.",
        })
        for row in payload["coverage"]:
            if row.get("layer") == "adapter_scope" and row.get("status") == "OUT_OF_SCOPE":
                row["reason"] = "No core BASE/OVERLAY adapter resolved; separately configured geography extensions may still apply."
    payload.setdefault("input", {})["matched_address"] = geocode.get("matched_address")
    for key, field in (("jurisdictions", "jurisdiction_id"), ("matched_divisions", "division_id"),
                       ("district_assignments", "adapter_id"), ("evidence", "evidence_id"), ("known_gaps", "gap_id")):
        payload[key] = sorted(payload.get(key, []), key=lambda row: str(row.get(field, "")))
    payload["coverage"] = sorted(payload.get("coverage", []), key=lambda r: (r.get("layer", ""), r.get("status", ""), r.get("reason", "")))
    return out
