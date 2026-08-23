#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_materialize.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_materialize", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load onboarding materializer")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    with tempfile.TemporaryDirectory() as td:
        akron = mod.materialize(ROOT, "jurisdiction-co-akron", Path(td) / "akron")
        assert akron["status"] == "PASS"
        assert akron["routing_strategy"] == "CENSUS_GEOID"
        assert akron["changes_required"] == 0
        assert akron["repository_mutated"] is False
        assert akron["canonical_writes"] == 0
        assert all(row["action"] == "NOOP" for row in akron["changes"])

        fircrest = mod.materialize(ROOT, "jurisdiction-wa-fircrest", Path(td) / "fircrest")
        assert fircrest["status"] == "PASS"
        assert fircrest["routing_strategy"] == "MUNICIPAL_BOUNDARY_OVERLAY"
        assert fircrest["changes_required"] == 0
        assert fircrest["repository_mutated"] is False
        assert fircrest["canonical_writes"] == 0
        assert all(row["action"] == "NOOP" for row in fircrest["changes"])

        report = mod.verify_all_production(ROOT, Path(td) / "all")
        assert report["status"] == "PASS"
        assert report["production_specs_verified"] == 2
        assert report["all_idempotent"] is True
        assert report["repository_mutated"] is False
        assert report["canonical_writes"] == 0

    print(json.dumps({
        "gate": "EV-IMP-010",
        "status": "PASS",
        "akron_materialization": "NOOP",
        "fircrest_materialization": "NOOP",
        "all_production_idempotent": True,
        "repository_mutated": False,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
