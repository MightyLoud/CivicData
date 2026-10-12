#!/usr/bin/env python3
"""Look up a street address through the governed geocoder, polygons and Contract v1."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote.address_runtime import build_representation_for_address
from tools.geocoding_boundary import ArcGISWorldGeocoder


def _address(value):
    query = " ".join(value.split())
    if not query or len(query) > 500:
        raise argparse.ArgumentTypeError("address must contain 1 through 500 characters after whitespace normalization")
    return query


def _timeout(value):
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a finite number greater than 0 and at most 120 seconds") from exc
    if not math.isfinite(seconds) or not 0 < seconds <= 120:
        raise argparse.ArgumentTypeError("timeout must be a finite number greater than 0 and at most 120 seconds")
    return seconds


def _failure(code, address):
    return {"status": "FAIL-CLOSED", "error": code,
        "input_address": address, "canonical_writes": 0}


def main(argv=None, *, geocoder=None):
    """Print the runtime JSON; provider injection is for in-process tests only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", type=_address, help="one quoted street address")
    parser.add_argument("--repo-root", type=Path, default=ROOT,
        help="repository containing the governed geometry and normalized packages")
    parser.add_argument("--timeout-seconds", type=_timeout, default=30.0,
        help="ArcGIS request timeout, greater than 0 and at most 120 (default: 30)")
    args = parser.parse_args(argv)
    try:
        root = args.repo_root.resolve()
        if not root.is_dir():
            parser.error("--repo-root must name an existing directory")
    except (OSError, RuntimeError):
        parser.error("--repo-root could not be resolved")

    interrupted = False
    try:
        provider = geocoder if geocoder is not None else ArcGISWorldGeocoder(timeout_seconds=args.timeout_seconds)
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        model = build_representation_for_address(args.address, geocoder=provider,
            generated_at=generated_at, root=root)
        if (not isinstance(model, dict) or model.get("status") not in {"PASS", "FAIL-CLOSED"}
                or type(model.get("canonical_writes")) is not int or model["canonical_writes"] != 0):
            model = _failure("LOOKUP_RUNTIME_RESULT_INVALID", args.address)
        # Serialize before emitting anything, so a malformed result cannot leave
        # partial JSON or non-standard NaN/Infinity output on stdout.
        encoded = json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    except KeyboardInterrupt:
        interrupted = True
        model = _failure("LOOKUP_INTERRUPTED", args.address)
        encoded = json.dumps(model, indent=2, sort_keys=True)
    except Exception:
        model = _failure("LOOKUP_EXECUTION_FAILED", args.address)
        encoded = json.dumps(model, indent=2, sort_keys=True)
    print(encoded)
    return 130 if interrupted else 0 if model["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
