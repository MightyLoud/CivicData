#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_pr_request.py"
spec = importlib.util.spec_from_file_location("ev_onboarding_pr_request", TOOL)
if spec is None or spec.loader is None:
    raise ImportError("unable to load EV-IMP-012 tool")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run() -> None:
    preview = mod.promote_tool.generate(ROOT, "jurisdiction-co-akron", ROOT / ".ev-imp-012-test-preview")
    noop = mod.build_request(ROOT, "jurisdiction-co-akron", preview["bundle_sha256"])
    assert noop["status"] == "NOOP"
    assert noop["branch_creation_required"] is False
    assert noop["pull_request_creation_required"] is False
    assert noop["merge_authorized"] is False
    assert noop["canonical_writes"] == 0

    original_generate = mod.promote_tool.generate
    try:
        reviewed = "a" * 64
        mod.promote_tool.generate = lambda repo_root, package_jurisdiction_id, out: {
            "status": "READY_FOR_REVIEW",
            "bundle_sha256": reviewed,
            "changes_required": 3,
        }
        request = mod.build_request(ROOT, "jurisdiction-wa-example", reviewed)
        assert request["status"] == "READY_FOR_DRAFT_PR"
        assert request["branch"] == "onboarding/wa-example-aaaaaaaaaaaa"
        assert request["base_branch"] == "main"
        assert request["pull_request"]["draft"] is True
        assert request["merge_authorized"] is False
        assert request["publication_authorized"] is False
        assert request["canonical_writes"] == 0
        assert len(request["request_sha256"]) == 64

        try:
            mod.build_request(ROOT, "jurisdiction-wa-example", "b" * 64)
        except mod.PRRequestError as exc:
            assert "reviewed bundle drift" in str(exc)
        else:
            raise AssertionError("stale reviewed bundle must fail closed")
    finally:
        mod.promote_tool.generate = original_generate

    try:
        mod.validate_sha256("not-a-sha")
    except mod.PRRequestError:
        pass
    else:
        raise AssertionError("invalid hash must fail closed")

    print(json.dumps({
        "gate": "EV-IMP-012",
        "status": "PASS",
        "production_noop": "PASS",
        "review_binding": "PASS",
        "draft_pr_only": "PASS",
        "automatic_merge": False,
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
