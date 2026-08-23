#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_batch.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_batch", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load batch onboarding tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    paths = mod.discover_specs(ROOT)
    names = [p.name for p in paths]
    assert "akron.v0.1.json" in names
    assert "fircrest.v0.1.json" in names
    assert all(not name.startswith("TEMPLATE") for name in names)

    rows = mod.load_specs(paths)
    mod.validate_batch(rows)

    with tempfile.TemporaryDirectory() as td:
        report = mod.run(ROOT, Path(td), verify_current=True)
        assert report["status"] == "PASS"
        assert report["gate"] == "EV-IMP-008"
        assert report["production_specs"] == len(paths)
        assert report["profiles"]["municipal_representation"] >= 1
        assert report["profiles"]["municipal_essentials"] >= 1
        assert report["routing_strategies"]["CENSUS_GEOID"] >= 1
        assert report["routing_strategies"]["MUNICIPAL_BOUNDARY_OVERLAY"] >= 1
        assert report["live_address_controls"] >= 4
        assert report["all_current_artifacts_match"] is True
        assert report["canonical_writes"] == 0
        assert (Path(td) / "acceptance-matrix.json").is_file()

    original_rows = mod.load_specs(paths)
    first_path, first_spec = original_rows[0]
    second_path, second_spec = original_rows[1]

    duplicate_entry = [(first_path, copy.deepcopy(first_spec)), (second_path, copy.deepcopy(second_spec))]
    duplicate_entry[1][1]["entry_id"] = duplicate_entry[0][1]["entry_id"]
    try:
        mod.validate_batch(duplicate_entry)
    except mod.BatchOnboardingError as exc:
        assert "duplicate entry_id" in str(exc)
    else:
        raise AssertionError("duplicate entry_id must fail closed")

    duplicate_geoid = [(first_path, copy.deepcopy(first_spec)), (second_path, copy.deepcopy(second_spec))]
    duplicate_geoid[1][1]["routing"]["geoid"] = duplicate_geoid[0][1]["routing"]["geoid"]
    try:
        mod.validate_batch(duplicate_geoid)
    except mod.BatchOnboardingError as exc:
        assert "duplicate governed GEOID" in str(exc)
    else:
        raise AssertionError("duplicate GEOID must fail closed")

    insufficient_live = [(first_path, copy.deepcopy(first_spec)), (second_path, copy.deepcopy(second_spec))]
    insufficient_live[0][1]["live_addresses"] = ["one address"]
    try:
        mod.validate_batch(insufficient_live)
    except mod.BatchOnboardingError as exc:
        assert "two live address controls" in str(exc)
    else:
        raise AssertionError("insufficient live controls must fail closed")

    print(json.dumps({
        "gate": "EV-IMP-008",
        "status": "PASS",
        "catalog_wide_replay": "PASS",
        "duplicate_entry": "FAIL-CLOSED",
        "duplicate_geoid": "FAIL-CLOSED",
        "insufficient_live_controls": "FAIL-CLOSED",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
