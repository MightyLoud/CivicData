#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_proposal.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_proposal", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load onboarding proposal tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    akron = mod.propose(ROOT, "jurisdiction-co-akron")
    assert akron["status"] == "READY"
    assert akron["profile"] == "municipal_representation"
    assert akron["routing_candidate"] == {"status": "GOVERNED_MATCH", "strategy": "CENSUS_GEOID"}
    assert akron["expected"]["office_rows"] == 2
    assert akron["expected"]["current_holders"] == 7
    assert len(akron["live_addresses"]) == 2
    assert akron["production_spec"]["entry_id"] == "co-akron-municipal-representation-v0.1"
    assert akron["canonical_writes"] == 0

    fircrest = mod.propose(ROOT, "jurisdiction-wa-fircrest")
    assert fircrest["status"] == "READY"
    assert fircrest["profile"] == "municipal_essentials"
    assert fircrest["routing_candidate"] == {"status": "GOVERNED_MATCH", "strategy": "MUNICIPAL_BOUNDARY_OVERLAY"}
    assert fircrest["expected"]["office_rows"] == 7
    assert fircrest["expected"]["current_holders"] == 7
    assert fircrest["full_essentials_expected"] == {
        "elections": 2,
        "contests": 7,
        "candidacies": 19,
        "named_person_candidacies": 12,
        "write_in_buckets": 7,
    }
    assert len(fircrest["live_addresses"]) == 2
    assert fircrest["production_spec"]["entry_id"] == "wa-fircrest-municipal-essentials-v0.2"
    assert fircrest["canonical_writes"] == 0

    with tempfile.TemporaryDirectory() as td:
        report = mod.verify_all_production(ROOT, Path(td))
        assert report["status"] == "PASS"
        assert report["gate"] == "EV-IMP-009"
        assert report["production_specs_regenerated"] == 2
        assert report["routing_authority_inferred"] is False
        assert report["canonical_writes"] == 0
        assert (Path(td) / "proposal-roundtrip.json").is_file()

    assert mod.slug("Lake Forest Park") == "lake-forest-park"
    assert mod.normalize_spec({"routing": {"adapter_id": "BASE-X"}})["routing"]["strategy"] == "CENSUS_GEOID"

    print(json.dumps({
        "gate": "EV-IMP-009",
        "status": "PASS",
        "akron_spec_regenerated": "PASS",
        "fircrest_spec_regenerated": "PASS",
        "routing_authority_inferred": False,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
