"""HTTP surface for the bounded Texas House 49 / Senate 14 hosted candidate."""
from __future__ import annotations

import os
from pathlib import Path
import re
import threading
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from services.texas_bounded_api.runtime import HostedRuntimeError, TexasBoundedRuntime

ROOT = Path(__file__).resolve().parents[2]
HEAD_SHA = os.environ.get("CIVICDATA_SERVICE_HEAD_SHA", "").strip().lower()
ENVIRONMENT = os.environ.get("CIVICDATA_SERVICE_ENVIRONMENT", "candidate").strip().lower()

app = FastAPI(
    title="CivicData bounded Texas legislative API",
    version="0.1",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_runtime: TexasBoundedRuntime | None = None
_runtime_error: str | None = None
_lock = threading.Lock()


def _runtime_instance() -> TexasBoundedRuntime:
    global _runtime, _runtime_error
    if _runtime is not None:
        return _runtime
    with _lock:
        if _runtime is not None:
            return _runtime
        try:
            _runtime = TexasBoundedRuntime.build(
                ROOT,
                head_sha=HEAD_SHA,
                environment=ENVIRONMENT,
                timeout_seconds=30.0,
            )
            _runtime_error = None
            return _runtime
        except Exception as exc:
            _runtime_error = str(exc)
            raise


def _static_service() -> dict[str, Any]:
    return {
        "service_id": "civicdata-tx-legislative-two-office-v0.1",
        "environment": ENVIRONMENT,
        "head_sha": HEAD_SHA,
        "profile_id": "tx_legislative_two_office_v0.1",
        "repository_activation": "NOT_ACTIVATED",
        "activation_authorized": False,
        "canonical_writes": 0,
    }


@app.get("/healthz")
def healthz() -> JSONResponse:
    valid_head = re.fullmatch(r"[a-f0-9]{40}", HEAD_SHA) is not None
    body = {
        "status": "PASS" if valid_head and bool(ENVIRONMENT) else "FAIL",
        "service": _static_service(),
    }
    if not valid_head:
        body["error"] = "CIVICDATA_SERVICE_HEAD_SHA_INVALID"
    return JSONResponse(body, status_code=200 if body["status"] == "PASS" else 503)


@app.get("/readyz")
def readyz() -> JSONResponse:
    try:
        runtime = _runtime_instance()
        return JSONResponse(runtime.readiness(), status_code=200)
    except Exception as exc:
        return JSONResponse(
            {
                "status": "FAIL-CLOSED",
                "error": getattr(exc, "code", "HOSTED_RUNTIME_NOT_READY"),
                "detail": str(exc),
                "service": _static_service(),
            },
            status_code=503,
        )


@app.get("/v1/representation")
def representation(address: str = Query(..., min_length=1, max_length=500)) -> JSONResponse:
    try:
        runtime = _runtime_instance()
        return JSONResponse(runtime.represent(address), status_code=200)
    except HostedRuntimeError as exc:
        return JSONResponse(
            {
                "service": _static_service(),
                "result": {
                    "status": "FAIL-CLOSED",
                    "error": exc.code,
                    "detail": exc.detail,
                    "canonical_writes": 0,
                },
            },
            status_code=503,
        )
    except Exception as exc:
        return JSONResponse(
            {
                "service": _static_service(),
                "result": {
                    "status": "FAIL-CLOSED",
                    "error": "HOSTED_RUNTIME_NOT_READY",
                    "detail": str(exc),
                    "canonical_writes": 0,
                },
            },
            status_code=503,
        )
