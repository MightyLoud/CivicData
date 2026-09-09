#!/usr/bin/env python3
"""Fail-closed EV onboarding guard for EV-IMP-019 routing-only Hawaiʻi counties."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOOL = ROOT / "tools" / "ev_onboarding_proposal.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_proposal_hi_guard", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load EV onboarding proposal tool")
proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proposal)

ROUTING_ONLY = {
    "jurisdiction-hi-hawaii-county": "BASE-HI-HAWAII-COUNTY",
    "jurisdiction-hi-honolulu-county": "BASE-HI-HONOLULU-COUNTY",
    "jurisdiction-hi-kauai-county": "BASE-HI-KAUAI-COUNTY",
    "jurisdiction-hi-maui-county": "BASE-HI-MAUI-COUNTY",
}


def run() -> None:
    registry = json.loads(
        (ROOT / "civic_gps_extensions" / "registry_bundles.v0.1.json").read_text(encoding="utf-8")
    )
    bundles = {
        str(row.get("adapter_id")): row
        for row in registry.get("bundles", [])
        if isinstance(row, dict) and row.get("adapter_id")
    }

    for package_id, adapter_id in ROUTING_ONLY.items():
        bundle = bundles[adapter_id]
        assert bundle.get("ev_onboarding_status") == "ROUTING_ONLY"
        scope = bundle.get("scope_match") or {}
        assert isinstance(scope.get("all"), list) and len(scope["all"]) == 2
        assert any(
            row.get("geography") == "county"
            and str(row.get("equals")) in {"15001", "15003", "15007", "15009"}
            for row in scope["all"]
        )

        result = proposal.propose(ROOT, package_id)
        if package_id == "jurisdiction-hi-kauai-county":
            from consumers.empowered_vote import countywide_production
            installed = countywide_production.installed_spec(ROOT)
            assert installed is not None
            assert result["status"] == "READY" and result["production_spec"] == installed
            assert result["auto_promoted"] is False
            assert result["routing_candidate"]["status"] == "EXPLICIT_PRODUCTION_INSTALLATION"
        else:
            assert result["status"] == "REVIEW_REQUIRED", result
            assert result["production_spec"] is None
            assert result["routing_candidate"]["status"] == "RESEARCH_REQUIRED", result
        assert result["canonical_writes"] == 0

    assert "BASE-HI-KALAWAO-COUNTY" not in bundles
    kalawao = proposal.propose(ROOT, "jurisdiction-hi-kalawao-county")
    assert kalawao["status"] == "REVIEW_REQUIRED", kalawao
    assert kalawao["production_spec"] is None
    assert kalawao["canonical_writes"] == 0

    print(
        json.dumps(
            {
                "gate": "EV-IMP-019",
                "status": "PASS",
                "routing_only_counties": 4,
                "auto_promoted": 0,
                "explicit_kauai_installations": 1,
                "other_hi_production_holds": 3,
                "kalawao_touched": False,
                "canonical_writes": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    run()
