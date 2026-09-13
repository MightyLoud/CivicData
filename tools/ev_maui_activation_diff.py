#!/usr/bin/env python3
"""Verify the proposed Maui installation preserves every other production entry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_production as production

CATALOG_PATH = "consumers/empowered_vote/package_catalog.v0.1.json"
ACTIVATION_PATHS = {str(production.SPEC_PATH), production.RECEIPT_PATH, production.REVIEW_REFERENCE["path"]}
PROTECTED = ["data", "previews", "candidates", "civic_gps_extensions", "civic_gps_runtime_parts", "civic_gps",
             "services", "railway.toml", "railway.json", "Dockerfile", "requirements-hosted-runtime.txt"]


def verify_catalog_delta(old, new, changed_paths):
    def other(value):
        return {**value, "entries": [r for r in value["entries"] if r.get("entry_id") != production.ENTRY_ID]}
    if (sum(r.get("entry_id") == production.ENTRY_ID for r in new["entries"]) != 1
            or other(old) != other(new)):
        raise ValueError("Other production catalog entries changed or Maui is missing/duplicated")
    if not set(changed_paths) <= ACTIVATION_PATHS:
        raise ValueError("Unrelated production spec or acceptance record changed")


def verify_diff(root, base_sha, head_sha):
    if not all(re.fullmatch(r"[a-f0-9]{40}", sha or "") for sha in (base_sha, head_sha)):
        raise ValueError("Exact base and head SHA required")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    if git("rev-parse", "HEAD").decode().strip() != head_sha:
        raise ValueError("Checkout differs from expected head")
    # The publication candidate adds only its immutable metadata/evidence contract.
    # It must pass an exact base/tree, nine-path allowlist, and all unchanged-input hashes.
    all_changed = git("diff", "--name-only", base_sha, "HEAD").decode().splitlines()
    if any(p.startswith("candidates/ev/maui_publication.v0.1/") for p in all_changed):
        from tools import ev_maui_publication_candidate as publication
        result = publication.verify_git(root, head_sha, base_sha)
        receipt = publication.verify_inputs(root)
        manifest_raw = (root / publication.MANIFEST).read_bytes()
        manifest = publication.load_json(manifest_raw)
        publication.validate_manifest(manifest, receipt)
        if manifest_raw != publication.encoded(manifest):
            raise ValueError("Publication manifest serialization drift")
        if publication.load_json((root / publication.SCHEMA).read_bytes()) != publication.schema_contract(manifest):
            raise ValueError("Publication schema drift")
        return {**result, "mode": "HELD_MAUI_PUBLICATION_CANDIDATE",
                "all_production_entries_preserved": 6, "protected_content_unchanged": True}
    git("diff", "--exit-code", base_sha, "HEAD", "--", *PROTECTED)
    old = json.loads(git("show", base_sha + ":" + CATALOG_PATH))
    new = json.loads((root / CATALOG_PATH).read_text())
    changed = git("diff", "--name-only", base_sha, "HEAD", "--", "onboarding/ev", "acceptance/ev").decode().splitlines()
    verify_catalog_delta(old, new, changed)
    if production.installed_spec(root) is None:
        raise ValueError("Validated Maui installation required")
    return {"status": "PASS", "base_sha": base_sha, "head_sha": head_sha,
            "other_catalog_entries_preserved": len(new["entries"]) - 1,
            "activation_paths": changed, "protected_content_unchanged": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_diff(args.repo_root.resolve(), args.base_sha, args.head_sha), sort_keys=True))


if __name__ == "__main__":
    main()
