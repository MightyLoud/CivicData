#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_promote.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_promote", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load onboarding promotion tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "preview"
        akron = mod.generate(ROOT, "jurisdiction-co-akron", out)
        assert akron["status"] == "NOOP"
        assert akron["changes_required"] == 0
        assert len(akron["bundle_sha256"]) == 64
        assert akron["repository_mutated"] is False
        assert akron["canonical_writes"] == 0

        applied = mod.apply_reviewed(
            ROOT,
            "jurisdiction-co-akron",
            akron["bundle_sha256"],
            Path(td) / "apply-noop",
        )
        assert applied["status"] == "NOOP"
        assert applied["changes_applied"] == 0
        assert applied["post_apply_idempotence"] is True
        assert applied["repository_mutated"] is False

        try:
            mod.apply_reviewed(
                ROOT,
                "jurisdiction-co-akron",
                "0" * 64,
                Path(td) / "drift",
            )
        except mod.PromotionError as exc:
            assert "reviewed bundle drift" in str(exc)
        else:
            raise AssertionError("stale reviewed bundle must fail closed")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        (root / "onboarding" / "ev").mkdir(parents=True)
        (root / "consumers" / "empowered_vote").mkdir(parents=True)
        (root / "civic_gps_extensions").mkdir(parents=True)

        catalog = root / "consumers" / "empowered_vote" / "package_catalog.v0.1.json"
        registry = root / "civic_gps_extensions" / "registry_bundles.v0.1.json"
        catalog.write_text('{"catalog_version":"0.1","entries":[]}\n', encoding="utf-8")
        registry.write_text('{"extension_version":"0.1","bundles":[],"municipal_boundary_overlays":[]}\n', encoding="utf-8")

        stage = Path(td) / "stage"
        spec_rel = "onboarding/ev/example.v0.1.json"
        catalog_rel = "consumers/empowered_vote/package_catalog.v0.1.json"
        registry_rel = "civic_gps_extensions/registry_bundles.v0.1.json"
        for rel, content in {
            spec_rel: '{"spec_version":"0.1"}\n',
            catalog_rel: '{"catalog_version":"0.1","entries":[{"entry_id":"x"}]}\n',
            registry_rel: '{"extension_version":"0.1","bundles":[{"adapter_id":"BASE-X"}],"municipal_boundary_overlays":[]}\n',
        }.items():
            path = stage / "staged" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        manifest = {
            "gate": "EV-IMP-010",
            "status": "PASS",
            "package_jurisdiction_id": "jurisdiction-x",
            "entry_id": "x",
            "routing_strategy": "CENSUS_GEOID",
            "changes": [
                {"path": spec_rel, "action": "ADD"},
                {"path": catalog_rel, "action": "ADD"},
                {"path": registry_rel, "action": "ADD"},
            ],
            "changes_required": 3,
            "conflicts": 0,
            "repository_mutated": False,
            "canonical_writes": 0,
            "publication_authorized": False,
        }
        (stage / "materialization-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        descriptor = mod.bundle_descriptor(stage)
        assert descriptor["changes_required"] == 3
        assert len(descriptor["bundle_sha256"]) == 64

        assert mod._allowed_path(spec_rel)
        assert mod._allowed_path(catalog_rel)
        assert mod._allowed_path(registry_rel)
        assert not mod._allowed_path("README.md")
        assert not mod._allowed_path("../escape.json")

    print(json.dumps({
        "gate": "EV-IMP-011",
        "status": "PASS",
        "production_noop": "PASS",
        "review_hash_binding": "PASS",
        "stale_review": "FAIL-CLOSED",
        "path_allowlist": "PASS",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
