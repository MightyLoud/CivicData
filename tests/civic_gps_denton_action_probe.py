#!/usr/bin/env python3
"""Deterministic Denton action-selection contract for Civic GPS v0.6.1 / registry v0.5.6."""
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
ACTION_FILE = "civic_gps_action_registry_denton_v0.1.json"

spec = importlib.util.spec_from_file_location("civic_gps_engine_denton_actions", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("registry_artifact_version") != "0.5.6":
    raise AssertionError(f"Expected registry 0.5.6, got {registry.get('registry_artifact_version')}")
resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
action_registry = json.loads((GPS / ACTION_FILE).read_text(encoding="utf-8"))
if action_registry.get("meta", {}).get("route_count") != 27:
    raise AssertionError("Denton action registry must declare exactly 27 routes")

BASE_IDS = {
    "ACT-DENTON-COMMISSIONERS-AGENDAS",
    "ACT-DENTON-COMMISSIONERS-CALENDAR",
    "ACT-DENTON-COMMISSIONERS-PUBLIC-COMMENT",
    "ACT-DENTON-COMMISSIONERS-REMOTE-PARTICIPATION",
    "ACT-DENTON-COMMISSIONERS-WATCH",
    "ACT-DENTON-CONTACT-COUNTY-CLERK",
    "ACT-DENTON-CONTACT-COUNTY-JUDGE",
    "ACT-DENTON-CONTACT-DISTRICT-CLERK",
    "ACT-DENTON-CONTACT-SHERIFF",
    "ACT-DENTON-CONTACT-TAX-ASSESSOR",
    "ACT-DENTON-CONTACT-TREASURER",
}
if len(BASE_IDS) != 11:
    raise AssertionError("Expected 11 Denton body/countywide action IDs")


def divs(comm=None, jp=None, constable=None):
    out = set()
    if comm:
        out.add(f"div-us-tx-denton-county-commissioner-precinct-{comm}")
    if jp:
        out.add(f"div-us-tx-denton-county-jp-precinct-{jp}")
    if constable:
        out.add(f"div-us-tx-denton-county-constable-precinct-{constable}")
    return out


def resolve_ids(district_ids):
    rows = resolver._resolve_actions([ACTION_FILE], {J_DENTON}, district_ids)
    return {row["action_id"] for row in rows}


def expected(comm=None, jp=None, constable=None):
    ids = set(BASE_IDS)
    if comm:
        ids.add(f"ACT-DENTON-CONTACT-COMMISSIONER-P{comm}")
    if jp:
        ids.add(f"ACT-DENTON-CONTACT-JP-P{jp}")
    if constable:
        ids.add(f"ACT-DENTON-CONTACT-CONSTABLE-P{constable}")
    return ids

CASES = [
    ("interior-p2", divs("2", "2", "2"), expected("2", "2", "2"), 14),
    ("interior-p4", divs("4", "4", "4"), expected("4", "4", "4"), 14),
    # Exact Commissioner boundary: ambiguous Commissioner assignment is absent.
    ("commissioner-boundary", divs(None, "3", "3"), expected(None, "3", "3"), 13),
    # Exact JP/Constable boundary: both shared-geometry assignments are absent.
    ("jp-constable-boundary", divs("2", None, None), expected("2", None, None), 12),
    ("countywide-only", set(), BASE_IDS, 11),
]

summaries = []
for case_id, district_ids, expected_ids, expected_count in CASES:
    got = resolve_ids(district_ids)
    if got != expected_ids or len(got) != expected_count:
        raise AssertionError(
            f"[{case_id}] action selection mismatch; expected {expected_count}/{sorted(expected_ids)}, "
            f"got {len(got)}/{sorted(got)}"
        )
    summaries.append({
        "case": case_id,
        "status": "PASS",
        "district_division_ids": sorted(district_ids),
        "action_count": len(got),
    })

inactive = resolver._resolve_actions([ACTION_FILE], set(), set())
if inactive:
    raise AssertionError(f"Inactive Denton jurisdiction unexpectedly returned actions: {inactive}")
summaries.append({"case": "inactive-jurisdiction", "status": "PASS", "district_division_ids": [], "action_count": 0})

# _resolve_actions is called only after a bundle activates. Explicitly prove the
# action registry itself contains no non-Denton jurisdiction rows.
non_denton = [a for a in action_registry.get("actions", []) if a.get("jurisdiction_id") != J_DENTON]
if non_denton:
    raise AssertionError(f"Denton action registry leaked non-Denton rows: {non_denton}")

summary = {
    "status": "PASS",
    "registry_artifact_version": registry.get("registry_artifact_version"),
    "route_count": action_registry.get("meta", {}).get("route_count"),
    "cases": summaries,
}
(OUTPUT / "denton-action-selection-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print("PASS: Denton action selection / boundary suppression contract")
