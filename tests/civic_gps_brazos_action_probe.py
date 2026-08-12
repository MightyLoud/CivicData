#!/usr/bin/env python3
"""Deterministic Brazos action-selection contract for Civic GPS v0.6.2 / registry v0.6.1."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
OUTPUT = ROOT / "artifacts" / "civic-gps-brazos-cg09"
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"
RELEASE_FILE = "civic_gps_brazos_county_v0.1.json"
J_BRAZOS = "jur-us-tx-brazos-county"
ACTION_FILE = "civic_gps_action_registry_brazos_v0.1.json"
EXPECTED_REGISTRY_VERSION = os.environ.get("CIVIC_GPS_EXPECTED_REGISTRY_VERSION", "0.6.1")


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


spec = importlib.util.spec_from_file_location("civic_gps_engine_brazos_actions", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
if registry.get("registry_artifact_version") != EXPECTED_REGISTRY_VERSION:
    raise AssertionError(
        f"Expected registry {EXPECTED_REGISTRY_VERSION}, got {registry.get('registry_artifact_version')}"
    )
resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
action_registry = json.loads((GPS / ACTION_FILE).read_text(encoding="utf-8"))
action_without_hash = copy.deepcopy(action_registry)
recorded_sha = action_without_hash["meta"].pop("canonical_content_sha256", None)
if not recorded_sha or recorded_sha != canonical_sha(action_without_hash):
    raise AssertionError("Brazos action registry canonical content SHA mismatch")
if action_registry.get("meta", {}).get("route_count") != 23:
    raise AssertionError("Brazos action registry must declare exactly 23 routes")
actions = action_registry.get("actions") or []
action_ids = [row.get("action_id") for row in actions]
if len(set(action_ids)) != 23:
    raise AssertionError("Brazos action registry must contain 23 unique action IDs")
meta_counts = action_registry["meta"]
if sum(
    meta_counts[key]
    for key in (
        "body_routes",
        "countywide_contact_routes",
        "commissioner_contact_routes",
        "justice_court_contact_routes",
        "constable_contact_routes",
    )
) != 23:
    raise AssertionError("Brazos action registry route buckets must sum to 23")
release = json.loads((GPS / RELEASE_FILE).read_text(encoding="utf-8"))
release_office_ids = {
    row.get("office_id") for row in release.get("payload", {}).get("offices") or []
}
contact_office_ids = {row.get("office_id") for row in actions if row.get("office_id")}
if contact_office_ids != release_office_ids or len(contact_office_ids) != 18:
    raise AssertionError("Every canonical Brazos release office must have exactly one governed contact route")

BASE_IDS = {
    "ACT-BRAZOS-COMMISSIONERS-AGENDAS",
    "ACT-BRAZOS-COMMISSIONERS-CALENDAR",
    "ACT-BRAZOS-COMMISSIONERS-CONTACT",
    "ACT-BRAZOS-COMMISSIONERS-PUBLIC-COMMENT",
    "ACT-BRAZOS-COMMISSIONERS-WATCH",
    "ACT-BRAZOS-CONTACT-COUNTY-CLERK",
    "ACT-BRAZOS-CONTACT-COUNTY-JUDGE",
    "ACT-BRAZOS-CONTACT-DISTRICT-CLERK",
    "ACT-BRAZOS-CONTACT-SHERIFF",
    "ACT-BRAZOS-CONTACT-TAX-ASSESSOR",
    "ACT-BRAZOS-CONTACT-TREASURER",
}
if len(BASE_IDS) != 11:
    raise AssertionError("Expected 11 Brazos body/countywide action IDs")


def divs(comm=None, jp=None, constable=None):
    out = set()
    if comm:
        out.add(f"div-us-tx-brazos-county-commissioner-{comm}")
    if jp:
        out.add(f"div-us-tx-brazos-county-jp-{jp}")
    if constable:
        out.add(f"div-us-tx-brazos-county-constable-{constable}")
    return out


def resolve_ids(district_ids):
    rows = resolver._resolve_actions([ACTION_FILE], {J_BRAZOS}, district_ids)
    return {row["action_id"] for row in rows}


def expected(comm=None, jp=None, constable=None):
    ids = set(BASE_IDS)
    if comm:
        ids.add(f"ACT-BRAZOS-CONTACT-COMMISSIONER-P{comm}")
    if jp:
        ids.add(f"ACT-BRAZOS-CONTACT-JP-P{jp}")
    if constable:
        ids.add(f"ACT-BRAZOS-CONTACT-CONSTABLE-P{constable}")
    return ids


CASES = [
    (f"interior-p{key}", divs(key, key, key), expected(key, key, key), 14)
    for key in ("1", "2", "3", "4")
] + [
    # All three families share one geometry; exact ambiguity suppresses all three.
    ("shared-boundary", set(), BASE_IDS, 11),
]

summaries = []
for case_id, district_ids, expected_ids, expected_count in CASES:
    got = resolve_ids(district_ids)
    if got != expected_ids or len(got) != expected_count:
        raise AssertionError(
            f"[{case_id}] action selection mismatch; expected {expected_count}/{sorted(expected_ids)}, "
            f"got {len(got)}/{sorted(got)}"
        )
    summaries.append(
        {
            "case": case_id,
            "status": "PASS",
            "district_division_ids": sorted(district_ids),
            "action_count": len(got),
        }
    )

inactive = resolver._resolve_actions([ACTION_FILE], set(), set())
if inactive:
    raise AssertionError(f"Inactive Brazos jurisdiction unexpectedly returned actions: {inactive}")
summaries.append(
    {"case": "inactive-jurisdiction", "status": "PASS", "district_division_ids": [], "action_count": 0}
)

non_brazos = [
    action
    for action in actions
    if action.get("jurisdiction_id") != J_BRAZOS
]
if non_brazos:
    raise AssertionError(f"Brazos action registry leaked non-Brazos rows: {non_brazos}")

summary = {
    "status": "PASS",
    "registry_artifact_version": registry.get("registry_artifact_version"),
    "action_registry_sha256": recorded_sha,
    "route_count": action_registry.get("meta", {}).get("route_count"),
    "cases": summaries,
}
(OUTPUT / "brazos-action-selection-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
print("PASS: Brazos action selection / shared-boundary suppression contract")
