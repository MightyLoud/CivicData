#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_jurisdiction_onboarding.py"
spec = importlib.util.spec_from_file_location("ev_jurisdiction_onboarding", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load onboarding tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    akron = ROOT / "onboarding" / "ev" / "akron.v0.1.json"
    with tempfile.TemporaryDirectory() as tmp:
        report = mod.run(akron, ROOT, Path(tmp), True)
        assert report["status"] == "PASS"
        assert report["entry_id"] == "co-akron-municipal-representation-v0.1"
        assert report["profile"] == "municipal_representation"
        assert report["package_schema_version"] == "0.1"
        assert report["matches_current_governed_artifacts"] is True
        assert report["observed"]["office_rows"] == 2
        assert report["observed"]["current_holders"] == 7
        assert report["observed"]["address_controls"] == 2
        assert report["routing_only"] is True
        assert report["civic_gps_civic_fact_rows"] == 0
        assert report["canonical_writes"] == 0
        for name in ("package_catalog_entry.json", "civic_gps_routing_bundle.json", "acceptance.json"):
            assert (Path(tmp) / name).is_file()

    original = json.loads(akron.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        bad = copy.deepcopy(original)
        bad["routing"]["geoid"] = "0800926"
        path = Path(td) / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            mod.run(path, ROOT, Path(td) / "out", False)
        except mod.OnboardingError as exc:
            assert "GEOID" in str(exc)
        else:
            raise AssertionError("routing/package GEOID drift must fail closed")

    with tempfile.TemporaryDirectory() as td:
        bad = copy.deepcopy(original)
        bad["profile"] = "municipal_essentials"
        path = Path(td) / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            mod.run(path, ROOT, Path(td) / "out", False)
        except mod.OnboardingError as exc:
            assert "full_essentials" in str(exc)
        else:
            raise AssertionError("v0.1 package must not be promoted to full essentials")

    with tempfile.TemporaryDirectory() as td:
        bad = copy.deepcopy(original)
        bad["expected"]["current_holders"] = 8
        path = Path(td) / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            mod.run(path, ROOT, Path(td) / "out", False)
        except mod.OnboardingError as exc:
            assert "current_holders" in str(exc)
        else:
            raise AssertionError("acceptance-count drift must fail closed")

    print(json.dumps({
        "gate": "EV-IMP-006",
        "status": "PASS",
        "akron_replay": "PASS",
        "current_artifact_match": "PASS",
        "routing_geoid_drift": "FAIL-CLOSED",
        "capability_overclaim": "FAIL-CLOSED",
        "acceptance_count_drift": "FAIL-CLOSED",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
