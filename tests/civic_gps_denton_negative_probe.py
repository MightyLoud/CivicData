#!/usr/bin/env python3
"""Packaged Denton County outside-scope negative control."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-live-smoke"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
J_DENTON = "jur-us-tx-denton-county"
ADDRESS = "1500 Marilla Street, Dallas, TX 75201"

spec = importlib.util.spec_from_file_location("civic_gps_engine_denton_negative", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)

resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
result = resolver.resolve(ADDRESS, observed_on=None)
(OUTPUT / "denton-outside-dallas.json").write_text(
    json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
if "error" in result:
    raise AssertionError(f"outside-county control must geocode cleanly; engine returned {result['error']}")
payload = result["payload"]
jurisdictions = {x["jurisdiction_id"] for x in payload["jurisdictions"]}
denton_assignments = [x for x in payload["district_assignments"] if x.get("jurisdiction_id") == J_DENTON]
denton_offices = [x for x in payload["applicable_offices"] if x.get("jurisdiction_id") == J_DENTON]
denton_actions = [x for x in payload["action_links"] if x.get("jurisdiction_id") == J_DENTON]

if J_DENTON in jurisdictions:
    raise AssertionError(f"Denton incorrectly activated for Dallas address; jurisdictions={sorted(jurisdictions)}")
if denton_assignments or denton_offices or denton_actions:
    raise AssertionError(
        f"Denton leaked outside county: assignments={len(denton_assignments)}, "
        f"offices={len(denton_offices)}, actions={len(denton_actions)}"
    )

summary = {
    "case": "denton-outside-dallas",
    "address": ADDRESS,
    "status": "PASS",
    "denton_jurisdiction_present": False,
    "denton_assignments": 0,
    "denton_applicable_offices": 0,
    "denton_actions": 0,
}
(OUTPUT / "denton-negative-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(summary, sort_keys=True))
print("PASS: packaged Denton outside-county negative control")
