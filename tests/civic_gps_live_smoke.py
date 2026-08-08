#!/usr/bin/env python3
"""Networked Civic GPS v0.6.0 smoke tests.

These tests intentionally exercise the real Census and ArcGIS upstreams from a
network-enabled runner. They validate geographic activation and consumer-facing
applicability without pinning unstable serialization timestamps or response hashes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
ENGINE_PATH = GPS / "engine.py"
REGISTRY_PATH = GPS / "registry.json"

spec = importlib.util.spec_from_file_location("civic_gps_engine", ENGINE_PATH)
engine_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine_mod
assert spec.loader is not None
spec.loader.exec_module(engine_mod)

J_TACOMA = "jur-us-wa-tacoma"
J_PIERCE = "jur-us-wa-pierce"
J_DENVER = "jur-us-co-denver"
J_RTD = "jur-us-co-regional-transportation-district"
J_D11 = "jur-us-co-colorado-springs-school-district-11"

CASES = [
    {
        "id": "tacoma-pierce",
        "address": "747 Market Street, Tacoma, WA 98402",
        "jurisdictions": {J_TACOMA, J_PIERCE},
        "assignments": {
            "DIST-WA-TACOMA-COUNCIL": "2",
            "DIST-WA-PIERCE-COUNCIL": "4",
        },
        "applicable_count": 11,
        "required_offices": {
            "office-tacoma-council-2",
            "office-pierce-council-4",
        },
    },
    {
        "id": "denver-rtd",
        "address": "1437 Bannock Street, Denver, CO 80202",
        "jurisdictions": {J_DENVER, J_RTD},
        "assignments": {
            "DIST-CO-DENVER-COUNCIL": "10",
            "DIST-CO-RTD-DIRECTOR": "A",
        },
        "applicable_count": 7,
        "required_offices": {
            "office-denver-co-council-district-10",
            "office-rtd-director-district-a",
        },
        "action_count": 23,
    },
    {
        "id": "boulder-rtd",
        "address": "1777 Broadway, Boulder, CO 80302",
        "jurisdictions": {J_RTD},
        "forbidden_jurisdictions": {J_DENVER},
        "assignments": {"DIST-CO-RTD-DIRECTOR": "O"},
        "applicable_count": 1,
        "required_offices": {"office-rtd-director-district-o"},
    },
    {
        "id": "d11-inside",
        "address": "1115 N El Paso St, Colorado Springs, CO 80903",
        "jurisdictions": {J_D11},
        "assignments": {},
        "applicable_count": 7,
        "required_offices": {
            f"office-colorado-springs-school-district-11-co-board-director-{n:02d}"
            for n in range(1, 8)
        },
        "action_count": 17,
    },
    {
        "id": "d11-outside-harrison",
        "address": "2755 Janitell Road, Colorado Springs, CO 80906",
        "jurisdictions": set(),
        "forbidden_jurisdictions": {J_D11},
        "assignments": {},
        "applicable_count": 0,
        "action_count": 0,
    },
]


def fail(case_id: str, message: str) -> None:
    raise AssertionError(f"[{case_id}] {message}")


def run_case(resolver, case: dict, output_dir: Path) -> dict:
    case_id = case["id"]
    result = resolver.resolve(case["address"], observed_on=None)
    (output_dir / f"{case_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    if "error" in result:
        fail(case_id, f"engine returned error: {result['error']}")

    payload = result["payload"]
    got_j = {x["jurisdiction_id"] for x in payload["jurisdictions"]}
    for jid in case.get("jurisdictions", set()):
        if jid not in got_j:
            fail(case_id, f"missing jurisdiction {jid}; got {sorted(got_j)}")
    for jid in case.get("forbidden_jurisdictions", set()):
        if jid in got_j:
            fail(case_id, f"unexpected jurisdiction {jid}; got {sorted(got_j)}")

    got_assignments = {
        x["adapter_id"]: str(x["district_key"])
        for x in payload["district_assignments"]
    }
    for adapter_id, expected_key in case.get("assignments", {}).items():
        if got_assignments.get(adapter_id) != str(expected_key):
            fail(
                case_id,
                f"{adapter_id} expected district {expected_key}, got {got_assignments.get(adapter_id)!r}",
            )

    applicable = payload["applicable_offices"]
    if len(applicable) != case["applicable_count"]:
        fail(case_id, f"expected {case['applicable_count']} applicable offices, got {len(applicable)}")
    got_offices = {x["office_id"] for x in applicable}
    missing = set(case.get("required_offices", set())) - got_offices
    if missing:
        fail(case_id, f"missing applicable offices: {sorted(missing)}")

    if "action_count" in case and len(payload["action_links"]) != case["action_count"]:
        fail(case_id, f"expected {case['action_count']} actions, got {len(payload['action_links'])}")

    return {
        "case": case_id,
        "status": "PASS",
        "matched_address": payload["input"].get("matched_address"),
        "jurisdictions": sorted(got_j),
        "district_assignments": got_assignments,
        "applicable_offices": len(applicable),
        "actions": len(payload["action_links"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="artifacts/civic-gps-live-smoke")
    args = parser.parse_args()
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Temporary non-main probe support: export the exact reconstructed runtime source
    # into the normal smoke artifact so Denton can be built against the real v0.6.0
    # engine/registry rather than an inferred copy.
    shutil.copy2(ENGINE_PATH, output_dir / "engine.py")
    shutil.copy2(REGISTRY_PATH, output_dir / "registry.json")

    resolver = engine_mod.CivicGPSOverlayEngine.from_file(REGISTRY_PATH, timeout_seconds=30.0)
    summaries = []
    try:
        for case in CASES:
            print(f"RUN {case['id']}: {case['address']}", flush=True)
            summary = run_case(resolver, case, output_dir)
            summaries.append(summary)
            print(f"PASS {case['id']}: {json.dumps(summary, sort_keys=True)}", flush=True)
    except Exception as exc:
        summary_path = output_dir / "summary.json"
        summary_path.write_text(
            json.dumps({"status": "FAIL", "passed": summaries, "error": str(exc)}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps({"status": "PASS", "cases": summaries}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: {len(summaries)}/{len(CASES)} live Civic GPS controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
