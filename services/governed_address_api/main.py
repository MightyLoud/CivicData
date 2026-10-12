"""Local HTTP surface for the existing governed address-to-representation runtime."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from consumers.empowered_vote.address_runtime import build_representation_for_address
from tools.geocoding_boundary import ArcGISWorldGeocoder

ROOT = Path(__file__).resolve().parents[2]
SERVICE_ID = "civicdata-governed-address-local-v0.1"
NOT_FOUND = {"ADDRESS_NOT_MATCHED", "POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY",
    "POINT_OUTSIDE_GOVERNED_GEOMETRY"}
UNPROCESSABLE = {"ADDRESS_REQUIRED", "AMBIGUOUS_ADDRESS", "GEOCODER_SCORE_BELOW_POLICY",
    "GEOCODER_ADDRESS_TYPE_NOT_ALLOWED", "GEOCODER_ALIAS_TYPE_CONFLICT",
    "POINT_GEOMETRY_AMBIGUOUS", "POINT_GOVERNED_JURISDICTION_AMBIGUOUS"}


class AddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: StrictStr = Field(min_length=1, max_length=500)

    @field_validator("address", mode="before")
    @classmethod
    def normalize_whitespace(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


def _failure(code):
    return {"status": "FAIL-CLOSED", "error": code, "canonical_writes": 0}


def _response(model, status_code):
    return JSONResponse(model, status_code=status_code, headers={"Cache-Control": "no-store"})


def create_app(*, repo_root=ROOT, geocoder=None, timeout_seconds=30.0):
    """Build an independent app; provider injection is an in-process test seam."""
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120):
        raise ValueError("ADDRESS_API_TIMEOUT_INVALID")
    root = Path(repo_root).resolve()
    app = FastAPI(title="CivicData local governed address lookup", version="0.1",
        docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return _response(_failure("ADDRESS_REQUEST_INVALID"), 422)

    @app.get("/healthz")
    def healthz():
        return _response({"status": "PASS", "service_id": SERVICE_ID,
            "scope": "LOCAL_GOVERNED_MUNICIPAL_REPRESENTATION", "canonical_writes": 0}, 200)

    @app.post("/v1/representation")
    def representation(payload: AddressRequest):
        try:
            provider = geocoder if geocoder is not None else ArcGISWorldGeocoder(timeout_seconds=timeout_seconds)
            generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            model = build_representation_for_address(payload.address, geocoder=provider,
                generated_at=generated_at, root=root)
            if (not isinstance(model, dict) or model.get("status") not in {"PASS", "FAIL-CLOSED"}
                    or type(model.get("canonical_writes")) is not int or model["canonical_writes"] != 0):
                return _response(_failure("ADDRESS_API_RUNTIME_RESULT_INVALID"), 503)
            if model["status"] == "FAIL-CLOSED" and (not isinstance(model.get("error"), str) or not model["error"]):
                return _response(_failure("ADDRESS_API_RUNTIME_RESULT_INVALID"), 503)
            if model["status"] == "PASS":
                return _response(model, 200)
            error = model.get("error")
            code = 404 if error in NOT_FOUND else 422 if error in UNPROCESSABLE else 503
            return _response(model, code)
        except Exception:
            return _response(_failure("ADDRESS_API_EXECUTION_FAILED"), 503)

    return app
