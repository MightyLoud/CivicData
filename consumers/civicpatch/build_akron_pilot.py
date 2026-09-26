#!/usr/bin/env python3
"""Build the committed Akron Factory → CivicPatch candidate integration artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from consumers.civicpatch.adapter import (
    ADAPTER_VERSION,
    CIVICPATCH_OPEN_DATA_COMMIT,
    CIVICPATCH_TOOLS_COMMIT,
    compare_current_civicpatch,
    export_core_to_civicpatch,
    render_civicpatch_yaml,
)
from tools.canonical_representation_core import from_jurisdiction_package, validate_core
from tools.snapshot_manifest import build_manifest, canonical_json_bytes

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data" / "normalized" / "co" / "jurisdiction-co-akron" / "jurisdiction.json"
CURRENT = ROOT / "acceptance" / "civicpatch" / "akron_current_pinned_69331c2.json"

GENERATED_AT = "2026-09-26T15:35:00Z"
BUNDLE_NAME = "akron_factory_candidate_bundle_v0.1.json"
YAML_NAME = "akron_factory_candidate_v0.1.yml"
MANIFEST_NAME = "akron_factory_candidate_bundle_v0.1.manifest.json"
DRIFT_NAME = "akron_factory_candidate_drift_v0.1.json"


def build_artifacts(output_dir: Path) -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    core = from_jurisdiction_package(package)
    errors = validate_core(core)
    if errors:
        raise SystemExit("core validation failed: " + ", ".join(errors))

    bundle = export_core_to_civicpatch(
        core,
        generated_at=GENERATED_AT,
        source_package_path=str(PACKAGE.relative_to(ROOT)),
    )
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    drift = compare_current_civicpatch(current["officials"], bundle["officials"])
    bundle["comparison"] = {
        "current_civicpatch_commit": current["source_commit"],
        "drift_report": DRIFT_NAME,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / BUNDLE_NAME).write_bytes(canonical_json_bytes(bundle))
    (output_dir / YAML_NAME).write_text(
        render_civicpatch_yaml(bundle["officials"]),
        encoding="utf-8",
    )
    (output_dir / DRIFT_NAME).write_bytes(canonical_json_bytes(drift))

    jurisdiction = core["jurisdictions"][0]
    manifest = build_manifest(
        payload=bundle,
        payload_locator=f"acceptance/civicpatch/{BUNDLE_NAME}",
        payload_media_type="application/json",
        schema_version="civicpatch-adapter-bundle/0.1",
        generated_at=GENERATED_AT,
        producer_system="civicdata",
        adapter_version=ADAPTER_VERSION,
        source_snapshots=[
            {
                "system": "jurisdiction_factory",
                "snapshot_id": core["snapshot_id"],
                "locator": str(PACKAGE.relative_to(ROOT)),
            }
        ],
        jurisdiction_ocdid=jurisdiction["jurisdiction_ocdid"],
        division_ocdids=sorted({post["division_ocdid"] for post in core["posts"]}),
        complete_jurisdiction=True,
        certification={
            "status": core["certification"]["status"],
            "raw_complete": core["certification"]["raw_complete"],
            "normalized_complete": core["certification"]["normalized_complete"],
            "qa_passed": core["certification"]["qa_passed"],
            "parity_ok": core["certification"]["parity_ok"],
            "verified_at": "2026-08-19T00:00:00Z",
        },
        canonical_data_versions={
            "canonical_core": "canonical-representation-core/0.1",
            "civicpatch_open_data": f"CivicPatch/open-data@{CIVICPATCH_OPEN_DATA_COMMIT}",
            "civicpatch_tools": f"CivicPatch/civicpatch-tools@{CIVICPATCH_TOOLS_COMMIT}",
            "identity_registry": "shared-identity/0.1",
        },
    )
    (output_dir / MANIFEST_NAME).write_bytes(canonical_json_bytes(manifest))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "acceptance" / "civicpatch",
    )
    args = parser.parse_args()
    build_artifacts(args.output_dir)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
