#!/usr/bin/env python3
"""End-to-end governed address -> representation runtime.

Geocoding supplies candidate coordinates only. Governed geometry selects the
jurisdiction/division; the certified Representation Contract supplies civic
facts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.contract_v1 import (
    build_representation_from_civic_gps_result,
)
from tools.geocoding_boundary import (
    GeocodingBoundary,
    GeocodingBoundaryError,
    GeocodePolicy,
    GeocoderProvider,
)
from tools.governed_geography_resolver import (
    GovernedCoordinateResolver,
    GovernedGeographyError,
)

ROOT = Path(__file__).resolve().parents[2]
RESOLUTION_SOURCE = "GOVERNED_ADDRESS_GEOCODE_PIP"


class GovernedAddressRuntimeError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _package_index(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in sorted((root / "data" / "normalized").glob("**/jurisdiction.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        jurisdiction = package.get("jurisdiction", {})
        ocdid = (
            jurisdiction.get("ocd_jurisdiction_id")
            or jurisdiction.get("jurisdiction_ocdid")
        )
        if isinstance(ocdid, str) and ocdid:
            if ocdid in out:
                raise GovernedAddressRuntimeError(
                    "JURISDICTION_PACKAGE_DUPLICATE"
                )
            out[ocdid] = path
    return out


def build_representation_for_address(
    address: str,
    *,
    geocoder: GeocoderProvider,
    generated_at: str,
    root: Path = ROOT,
    policy: GeocodePolicy = GeocodePolicy(),
) -> dict[str, Any]:
    try:
        geocode = GeocodingBoundary(geocoder, policy=policy).resolve(address)
    except GeocodingBoundaryError as exc:
        return {
            "status": "FAIL-CLOSED",
            "error": str(exc),
            "input_address": address,
            "canonical_writes": 0,
        }

    geography = GovernedCoordinateResolver(root=root)
    try:
        resolved = geography.resolve_any(
            longitude=geocode["longitude"],
            latitude=geocode["latitude"],
        )
    except GovernedGeographyError as exc:
        return {
            "status": "FAIL-CLOSED",
            "error": str(exc),
            "input_address": address,
            "geocoding": geocode,
            "canonical_writes": 0,
        }

    packages = _package_index(root)
    package_path = packages.get(resolved["jurisdiction_ocdid"])
    if package_path is None:
        return {
            "status": "FAIL-CLOSED",
            "error": "GOVERNED_JURISDICTION_PACKAGE_MISSING",
            "input_address": address,
            "geocoding": geocode,
            "geography": resolved,
            "canonical_writes": 0,
        }

    package = json.loads(package_path.read_text(encoding="utf-8"))
    contract = export_factory_package(
        package,
        generated_at=generated_at,
        governed_package=True,
    )
    gps, binding = geography.civic_gps_payload_from_resolution(
        resolved,
        address=address,
        matched_address=geocode["matched_address"],
    )
    model = build_representation_from_civic_gps_result(
        contract,
        address,
        gps,
        binding=binding,
        resolution_source=RESOLUTION_SOURCE,
    )
    if model.get("status") != "PASS":
        return model

    model["geocoding"] = geocode
    model["governed_geography"] = resolved
    model["package_path"] = str(package_path.relative_to(root))
    model["canonical_writes"] = 0
    return model
