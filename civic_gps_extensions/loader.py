#!/usr/bin/env python3
"""Load governed geography-only extensions into the exact Civic GPS engine.

Extensions may add normal registry bundles or authoritative municipal-boundary
overlays. They never create offices, officeholders, actions, or other civic facts.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

EXTENSION_VERSION = "0.1"
DEFAULT_EXTENSION = Path(__file__).with_name("registry_bundles.v0.1.json")


def _load_extension(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"extension_version": EXTENSION_VERSION, "bundles": [], "municipal_boundary_overlays": []}
    extension = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(extension, dict) or str(extension.get("extension_version")) != EXTENSION_VERSION:
        raise ValueError("unsupported Civic GPS registry extension version")
    if not isinstance(extension.get("bundles", []), list):
        raise ValueError("Civic GPS registry extension bundles must be a list")
    overlays = extension.get("municipal_boundary_overlays", [])
    if not isinstance(overlays, list):
        raise ValueError("municipal_boundary_overlays must be a list")
    seen: set[str] = set()
    for row in overlays:
        if not isinstance(row, dict):
            raise ValueError("invalid municipal boundary overlay")
        for key in ("overlay_id", "parent_jurisdiction_id", "service_url", "where", "identity_field", "identity_value", "jurisdiction_id", "division_id", "division_name", "release_file"):
            if not row.get(key):
                raise ValueError(f"municipal boundary overlay missing {key}")
        oid = str(row["overlay_id"])
        if oid in seen:
            raise ValueError(f"duplicate municipal boundary overlay: {oid}")
        seen.add(oid)
    return extension


def load_registry_with_extensions(
    repo_root: str | Path,
    *,
    extension_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    root = Path(repo_root)
    registry_path = root / "civic_gps" / "registry.json"
    if not registry_path.is_file():
        raise FileNotFoundError("reconstructed Civic GPS registry is not present")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        raise ValueError("Civic GPS registry must be an object")

    ext_path = Path(extension_path) if extension_path is not None else root / "civic_gps_extensions" / "registry_bundles.v0.1.json"
    extension = _load_extension(ext_path)
    bundles = extension.get("bundles", [])

    merged = copy.deepcopy(registry)
    merged.setdefault("bundles", [])
    existing = {str(row.get("adapter_id")) for row in merged["bundles"] if isinstance(row, dict)}
    for bundle in bundles:
        if not isinstance(bundle, dict) or not bundle.get("adapter_id"):
            raise ValueError("invalid Civic GPS registry extension bundle")
        adapter_id = str(bundle["adapter_id"])
        if adapter_id in existing:
            raise ValueError(f"duplicate Civic GPS adapter extension: {adapter_id}")
        merged["bundles"].append(copy.deepcopy(bundle))
        existing.add(adapter_id)
    return merged, registry_path


def _rehash(result: dict[str, Any]) -> None:
    stable = copy.deepcopy(result)
    stable.get("meta", {}).pop("serialized_at", None)
    stable.get("meta", {}).pop("canonical_content_sha256", None)
    result.setdefault("meta", {})["canonical_content_sha256"] = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class CivicGPSBoundaryOverlayResolver:
    """Compose authoritative municipality polygons after the exact core resolver.

    The core engine remains responsible for address geocoding and its normal
    geography stack. An overlay is considered only when its configured parent
    jurisdiction already resolved, then an official polygon service confirms
    point-in-polygon. The overlay contributes jurisdiction/division geography
    only; it cannot contribute civic facts.
    """

    def __init__(self, engine: Any, overlays: list[dict[str, Any]]):
        self.engine = engine
        self.overlays = copy.deepcopy(overlays)

    def resolve(self, address: str, *, observed_on: str | None = None) -> dict[str, Any]:
        result = self.engine.resolve(address, observed_on=observed_on)
        if "error" in result or not self.overlays:
            return result
        payload = result.get("payload", {})
        active = {str(row.get("jurisdiction_id")) for row in payload.get("jurisdictions", []) if row.get("jurisdiction_id")}
        candidates = [row for row in self.overlays if str(row["parent_jurisdiction_id"]) in active and str(row["jurisdiction_id"]) not in active]
        if not candidates:
            return result

        try:
            geocode = self.engine._geocode(address)
        except Exception as exc:
            payload.setdefault("known_gaps", []).append({"gap_id":"GAP-MUNICIPAL-BOUNDARY-GEOCODE","status":"WAIT","summary":f"Municipal boundary overlay could not re-use the core geocoder: {exc}"})
            _rehash(result)
            return result

        lon, lat = geocode["longitude"], geocode["latitude"]
        for overlay in candidates:
            overlay_id = str(overlay["overlay_id"])
            service = str(overlay["service_url"]).rstrip("/")
            query_url = service + "/query"
            params = {
                "where": str(overlay["where"]),
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": str(overlay["identity_field"]),
                "returnGeometry": "false",
                "f": "json",
            }
            try:
                body = self.engine._get_json(query_url, params, overlay_id)
            except Exception as exc:
                payload.setdefault("coverage", []).append({"layer":"municipal_boundary","status":"NOT_RESOLVED","reason":f"{overlay_id} official boundary query failed."})
                payload.setdefault("known_gaps", []).append({"gap_id":f"GAP-{overlay_id}-SOURCE","status":"WAIT","summary":str(exc),"reference_url":service})
                continue
            features = body.get("features") or []
            if not features:
                continue
            if len(features) != 1:
                payload.setdefault("coverage", []).append({"layer":"municipal_boundary","status":"CONFLICT","reason":f"{overlay_id} returned multiple intersecting municipality polygons."})
                payload.setdefault("known_gaps", []).append({"gap_id":f"GAP-{overlay_id}-AMBIGUOUS","status":"CONFLICT","summary":"Multiple municipality polygons intersected the geocoded point.","reference_url":service})
                continue
            attrs = features[0].get("attributes") or {}
            actual = attrs.get(str(overlay["identity_field"]))
            if str(actual) != str(overlay["identity_value"]):
                payload.setdefault("known_gaps", []).append({"gap_id":f"GAP-{overlay_id}-IDENTITY","status":"CONFLICT","summary":"Official boundary response identity did not match the configured municipality.","reference_url":service})
                continue

            release = self.engine._load(str(overlay["release_file"])).get("payload") or {}
            jurisdiction_id = str(overlay["jurisdiction_id"])
            rows = [copy.deepcopy(row) for row in release.get("jurisdictions", []) if row.get("jurisdiction_id") == jurisdiction_id]
            if len(rows) != 1 or release.get("offices") or release.get("officeholders"):
                payload.setdefault("known_gaps", []).append({"gap_id":f"GAP-{overlay_id}-RELEASE","status":"CONFLICT","summary":"Boundary overlay release must contain exactly one jurisdiction and zero civic-fact rows."})
                continue
            payload.setdefault("jurisdictions", []).extend(rows)
            payload.setdefault("matched_divisions", []).append({"division_id":overlay["division_id"],"name":overlay["division_name"],"parent_id":overlay.get("parent_division_id"),"type":overlay.get("division_type","municipality")})
            payload.setdefault("evidence", []).append({"evidence_id":f"EVID-MUNI-{overlay_id}","supports":[f"jurisdictions.{jurisdiction_id}",f"matched_divisions.{overlay['division_id']}"],"url":f"{query_url}?{urlencode(params)}","verified_on":observed_on})
            payload.setdefault("coverage", []).append({"layer":"municipal_boundary","status":"GEOGRAPHY_ONLY","reason":f"{overlay_id} resolved through authoritative point-in-polygon; civic facts remain package-governed."})
            active.add(jurisdiction_id)

        for key, id_key in (("jurisdictions","jurisdiction_id"),("matched_divisions","division_id"),("evidence","evidence_id"),("known_gaps","gap_id")):
            dedup = {}
            for row in payload.get(key, []):
                if isinstance(row, dict) and row.get(id_key) is not None:
                    dedup[str(row[id_key])] = row
            payload[key] = [dedup[k] for k in sorted(dedup)]
        payload["coverage"] = sorted(payload.get("coverage", []), key=lambda row:(str(row.get("layer","")),str(row.get("status","")),str(row.get("reason",""))))
        _rehash(result)
        return result


def load_resolver_with_extensions(
    repo_root: str | Path,
    *,
    timeout_seconds: float = 30.0,
    extension_path: str | Path | None = None,
):
    root = Path(repo_root)
    engine_path = root / "civic_gps" / "engine.py"
    if not engine_path.is_file():
        raise FileNotFoundError("reconstructed Civic GPS engine is not present")
    ext_path = Path(extension_path) if extension_path is not None else root / "civic_gps_extensions" / "registry_bundles.v0.1.json"
    extension = _load_extension(ext_path)
    registry, registry_path = load_registry_with_extensions(root, extension_path=ext_path)
    spec = importlib.util.spec_from_file_location("civic_gps_engine_with_extensions", engine_path)
    if spec is None or spec.loader is None:
        raise ImportError("unable to load Civic GPS engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    engine = module.CivicGPSOverlayEngine(registry, registry_root=registry_path.parent, timeout_seconds=timeout_seconds)
    overlays = extension.get("municipal_boundary_overlays", [])
    return CivicGPSBoundaryOverlayResolver(engine, overlays) if overlays else engine
