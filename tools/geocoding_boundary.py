#!/usr/bin/env python3
"""Provider-neutral governed geocoding boundary.

A geocoder proposes coordinates. This module decides whether a proposal is
strong and unambiguous enough to pass downstream to governed geography.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Mapping, Protocol, Sequence
import urllib.parse
import urllib.request

ARCGIS_ENDPOINT = (
    "https://geocode.arcgis.com/arcgis/rest/services/World/"
    "GeocodeServer/findAddressCandidates"
)
ARCGIS_PROVIDER = "ARCGIS_WORLD_GEOCODER"

DEFAULT_ALLOWED_TYPES = (
    "PointAddress",
    "StreetAddress",
    "Subaddress",
)


class GeocodingBoundaryError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GeocoderProvider(Protocol):
    provider_id: str

    def find_candidates(
        self,
        address: str,
        *,
        max_locations: int,
    ) -> Sequence[Mapping[str, Any]]:
        ...


@dataclass(frozen=True)
class GeocodePolicy:
    min_score: float = 95.0
    min_margin: float = 5.0
    allowed_addr_types: tuple[str, ...] = DEFAULT_ALLOWED_TYPES
    max_candidates: int = 5

    def __post_init__(self) -> None:
        if not (0 <= self.min_score <= 100):
            raise ValueError("min_score must be within 0..100")
        if not (0 <= self.min_margin <= 100):
            raise ValueError("min_margin must be within 0..100")
        if self.max_candidates < 2:
            raise ValueError("max_candidates must be >= 2")
        if not self.allowed_addr_types:
            raise ValueError("allowed_addr_types must not be empty")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _normalized_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise GeocodingBoundaryError("GEOCODER_CANDIDATE_INVALID")

    matched_address = _clean(row.get("address"))
    score = row.get("score")
    location = row.get("location")
    attributes = row.get("attributes")

    if not matched_address:
        raise GeocodingBoundaryError("GEOCODER_MATCHED_ADDRESS_INVALID")
    if not _finite_number(score) or not 0 <= float(score) <= 100:
        raise GeocodingBoundaryError("GEOCODER_SCORE_INVALID")
    if not isinstance(location, Mapping):
        raise GeocodingBoundaryError("GEOCODER_LOCATION_INVALID")
    longitude = location.get("x")
    latitude = location.get("y")
    if (
        not _finite_number(longitude)
        or not _finite_number(latitude)
        or not -180 <= float(longitude) <= 180
        or not -90 <= float(latitude) <= 90
    ):
        raise GeocodingBoundaryError("GEOCODER_COORDINATES_INVALID")
    if not isinstance(attributes, Mapping):
        raise GeocodingBoundaryError("GEOCODER_ATTRIBUTES_INVALID")
    addr_type = _clean(attributes.get("Addr_type"))
    if not addr_type:
        raise GeocodingBoundaryError("GEOCODER_ADDRESS_TYPE_INVALID")

    return {
        "matched_address": matched_address,
        "score": float(score),
        "longitude": float(longitude),
        "latitude": float(latitude),
        "addr_type": addr_type,
    }


def _candidate_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _clean(row.get("matched_address")).casefold(),
        round(float(row["longitude"]), 10),
        round(float(row["latitude"]), 10),
        _clean(row.get("addr_type")),
    )


def select_candidate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    policy: GeocodePolicy = GeocodePolicy(),
) -> dict[str, Any]:
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise GeocodingBoundaryError("GEOCODER_CANDIDATES_INVALID")
    if not candidates:
        raise GeocodingBoundaryError("ADDRESS_NOT_MATCHED")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for raw in candidates:
        row = _normalized_candidate(raw)
        identity = _candidate_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append(row)

    if not normalized:
        raise GeocodingBoundaryError("ADDRESS_NOT_MATCHED")

    normalized.sort(
        key=lambda row: (
            -float(row["score"]),
            str(row["matched_address"]).casefold(),
            float(row["longitude"]),
            float(row["latitude"]),
        )
    )
    top = normalized[0]

    if top["addr_type"] not in policy.allowed_addr_types:
        raise GeocodingBoundaryError("GEOCODER_ADDRESS_TYPE_NOT_ALLOWED")
    if top["score"] < policy.min_score:
        raise GeocodingBoundaryError("GEOCODER_SCORE_BELOW_POLICY")

    if len(normalized) > 1:
        runner_up = normalized[1]
        margin = top["score"] - runner_up["score"]
        if margin < policy.min_margin:
            raise GeocodingBoundaryError("AMBIGUOUS_ADDRESS")
    else:
        margin = None

    return {
        **top,
        "candidate_count": len(normalized),
        "runner_up_score": (
            normalized[1]["score"] if len(normalized) > 1 else None
        ),
        "score_margin": margin,
        "policy": {
            "min_score": policy.min_score,
            "min_margin": policy.min_margin,
            "allowed_addr_types": list(policy.allowed_addr_types),
            "max_candidates": policy.max_candidates,
        },
    }


class ArcGISWorldGeocoder:
    provider_id = ARCGIS_PROVIDER

    def __init__(
        self,
        *,
        endpoint: str = ARCGIS_ENDPOINT,
        timeout_seconds: float = 30.0,
        country_code: str = "USA",
    ):
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.country_code = country_code

    def find_candidates(
        self,
        address: str,
        *,
        max_locations: int,
    ) -> Sequence[Mapping[str, Any]]:
        query = _clean(address)
        if not query:
            raise GeocodingBoundaryError("ADDRESS_REQUIRED")
        params = urllib.parse.urlencode(
            {
                "SingleLine": query,
                "f": "json",
                "outFields": "Addr_type,Match_addr",
                "outSR": "4326",
                "forStorage": "false",
                "countryCode": self.country_code,
                "maxLocations": int(max_locations),
            }
        )
        try:
            with urllib.request.urlopen(
                self.endpoint + "?" + params,
                timeout=self.timeout_seconds,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise GeocodingBoundaryError(
                "GEOCODER_PROVIDER_REQUEST_FAILED"
            ) from exc

        if not isinstance(payload, Mapping):
            raise GeocodingBoundaryError("GEOCODER_RESPONSE_INVALID")
        if payload.get("error"):
            raise GeocodingBoundaryError("GEOCODER_PROVIDER_ERROR")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            raise GeocodingBoundaryError("GEOCODER_CANDIDATES_INVALID")
        return candidates


class GeocodingBoundary:
    def __init__(
        self,
        provider: GeocoderProvider,
        *,
        policy: GeocodePolicy = GeocodePolicy(),
    ):
        self.provider = provider
        self.policy = policy

    def resolve(self, address: str) -> dict[str, Any]:
        query = _clean(address)
        if not query:
            raise GeocodingBoundaryError("ADDRESS_REQUIRED")
        candidates = self.provider.find_candidates(
            query,
            max_locations=self.policy.max_candidates,
        )
        accepted = select_candidate(candidates, policy=self.policy)
        return {
            "status": "PASS",
            "provider": self.provider.provider_id,
            "input_address": query,
            **accepted,
            "canonical_writes": 0,
        }
