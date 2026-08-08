#!/usr/bin/env python3
"""Williamson County CG-07 outside-county negative control.

This onboarding probe reuses the exact CG-06 generated Williamson bundle, overlays
it onto a temporary copy of the currently released Civic GPS runtime, and proves
that a valid Travis County address does not activate or leak any Williamson data.
Williamson remains onboarding-only and unpackaged.
"""
from __future__ import annotations

import copy
import json
import runpy
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CG06 = ROOT / "tests" / "civic_gps_williamson_cg06_probe.py"

# Reuse the exact positive-fixture bundle and roster. Running CG-06 here also
# guards against the negative test drifting away from the proven interior spec.
ctx = runpy.run_path(str(CG06))
GPS: Path = ctx["GPS"]
OUTPUT: Path = ctx["OUTPUT"]
engine_mod = ctx["engine_mod"]
bundle = ctx["bundle"]
release = ctx["release"]
spec = ctx["spec"]
J = ctx["J"]

OUTSIDE_ADDRESS = "700 Lavaca Street, Austin, TX 78701"
EXPECTED_OTHER_JURISDICTION = "jur-us-tx-travis-county"

with tempfile.TemporaryDirectory(prefix="civic-gps-williamson-cg07-") as temp_root:
    temp_gps = Path(temp_root) / "civic_gps"
    shutil.copytree(GPS, temp_gps)
    registry_path = temp_gps / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.3":
        raise AssertionError(
            f"CG-07 expects released engine 0.6.1 / registry 0.5.3, got "
            f"{registry.get('engine_version')} / {registry.get('registry_artifact_version')}"
        )
    if any(row.get("adapter_id") == bundle["adapter_id"] for row in registry.get("bundles", [])):
        raise AssertionError("Williamson unexpectedly already exists in released registry")

    registry["bundles"] = copy.deepcopy(registry.get("bundles") or []) + [bundle]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (temp_gps / spec["release_filename"]).write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    resolver = engine_mod.CivicGPSOverlayEngine.from_file(registry_path, timeout_seconds=30.0)
    result = resolver.resolve(OUTSIDE_ADDRESS, observed_on=None)

(OUTPUT / "cg07-outside-negative.json").write_text(
    json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

if "error" in result:
    raise AssertionError(f"CG-07 outside address failed to resolve: {result['error']}")

payload = result["payload"]
jurisdictions = {row.get("jurisdiction_id") for row in payload.get("jurisdictions") or []}
if EXPECTED_OTHER_JURISDICTION not in jurisdictions:
    raise AssertionError(
        f"CG-07 control must resolve normally outside Williamson; expected {EXPECTED_OTHER_JURISDICTION}, got {sorted(jurisdictions)}"
    )
if J in jurisdictions:
    raise AssertionError("CG-07 outside control unexpectedly activated Williamson County")

williamson_assignments = [
    row for row in payload.get("district_assignments") or [] if row.get("jurisdiction_id") == J
]
williamson_offices = [
    row for row in payload.get("applicable_offices") or [] if row.get("jurisdiction_id") == J
]
williamson_actions = [
    row for row in payload.get("action_links") or [] if row.get("jurisdiction_id") == J
]
williamson_coverage = [
    row for row in payload.get("coverage") or []
    if str(row.get("layer") or "").startswith("williamson_")
]

if williamson_assignments:
    raise AssertionError(f"CG-07 leaked Williamson district assignments: {williamson_assignments}")
if williamson_offices:
    raise AssertionError(f"CG-07 leaked Williamson applicable offices: {williamson_offices}")
if williamson_actions:
    raise AssertionError(f"CG-07 leaked Williamson action links: {williamson_actions}")
if williamson_coverage:
    raise AssertionError(f"CG-07 leaked Williamson coverage rows: {williamson_coverage}")

summary = {
    "gate": "CG-07",
    "status": "PASS",
    "county": "Williamson County, TX",
    "geoid": "48491",
    "outside_address": OUTSIDE_ADDRESS,
    "control_jurisdiction_present": EXPECTED_OTHER_JURISDICTION in jurisdictions,
    "williamson_jurisdiction_present": False,
    "williamson_assignments": 0,
    "williamson_applicable_offices": 0,
    "williamson_actions": 0,
    "williamson_coverage_rows": 0,
    "engine_version": "0.6.1",
    "registry_artifact_version": "0.5.3",
    "packaged": False,
    "engine_change_required": False,
    "next_gate": "CG-08 exact-boundary controls",
}
(OUTPUT / "cg07-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
print("WILLIAMSON CG-07 PASS")
