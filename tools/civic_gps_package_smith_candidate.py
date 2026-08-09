#!/usr/bin/env python3
"""Build the deterministic Smith County CG-09 candidate runtime without mutating production."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "tests/fixtures/civic_gps_county_onboarding/smith_county9_candidate_v0.1.json"
ONBOARDING_TOOL = ROOT / "tools/civic_gps_county_onboarding.py"
RUNTIME_PARTS = ROOT / "civic_gps_runtime_parts"
BASE_RUNTIME_SHA256 = "bc40a0aa46fcdbd5b2c73976747ef702d9a64fd051832c615ba4aba1016a7427"
BASE_REGISTRY_VERSION = "0.5.8"
CANDIDATE_REGISTRY_VERSION = "0.5.9"
ENGINE_VERSION = "0.6.2"
RELEASE_NAME = "civic_gps_smith_county_v0.1.json"
RELEASE_ARCHIVE_PATH = f"civic_gps/{RELEASE_NAME}"
REGISTRY_ARCHIVE_PATH = "civic_gps/registry.json"
ZIP_TIMESTAMP = (2026, 8, 9, 0, 0, 0)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def build_release_and_bundle(output_dir: Path) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="civic-gps-smith-package-") as temp_name:
        onboarding = Path(temp_name) / "onboarding"
        subprocess.run(
            [
                sys.executable,
                str(ONBOARDING_TOOL),
                str(SPEC_PATH),
                "--output-dir",
                str(onboarding),
                "--expect",
                "SUPPORTED_V0_1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        release = json.loads(
            (onboarding / "canonical-release-preview.json").read_text(encoding="utf-8")
        )
        bundle = json.loads(
            (onboarding / "base-bundle-plan.json").read_text(encoding="utf-8")
        )
        for source in sorted(onboarding.glob("*.json")):
            (output_dir / "onboarding" / source.name).parent.mkdir(parents=True, exist_ok=True)
            (output_dir / "onboarding" / source.name).write_bytes(source.read_bytes())

    release["meta"]["release_status"] = "RELEASE_BACKED_CURRENT"
    release["meta"]["note"] = (
        "Smith County is County #9 and the fifth production candidate packaged through County "
        "Onboarding Pipeline v0.1. CG-01 through CG-08 passed on the unchanged Civic GPS v0.6.2 "
        "engine. The bounded release contains six countywide offices, Commissioner precincts 1-4, "
        "and Justice of the Peace / Constable precincts 1-5. Current official county-directory "
        "identity controls over historical GIS display labels. Civic-action routing and additional "
        "countywide or judicial offices remain explicitly outside v0.1 scope."
    )
    for jurisdiction in release.get("payload", {}).get("jurisdictions") or []:
        jurisdiction["status"] = "RELEASE_BACKED_CURRENT"
    release_without_hash = copy.deepcopy(release)
    release_without_hash["meta"].pop("canonical_content_sha256", None)
    release["meta"]["canonical_content_sha256"] = canonical_sha(release_without_hash)

    for adapter in bundle.get("district_adapters") or []:
        adapter["source_status"] = "LIVE_INTERIOR_NEGATIVE_BOUNDARY_PASS"
    bundle["known_gaps"] = [
        {
            "gap_id": "GAP-SMITH-GPS-001",
            "status": "NOT_YET_RELEASED",
            "summary": "Smith County civic-action routing is not included in this geography/office candidate package.",
        },
        {
            "gap_id": "GAP-SMITH-GPS-002",
            "status": "BOUNDED_V0_1_SCOPE",
            "summary": "The v0.1 countywide set is deliberately bounded to six countywide offices; additional countywide and judicial offices are not modeled.",
        },
        {
            "gap_id": "GAP-SMITH-GPS-003",
            "status": "SOURCE_PRECEDENCE_RESOLVED",
            "summary": "The current Smith County elected-officials directory controls identity; historical names embedded in the 2021 GIS remain geometry-only.",
        },
        {
            "gap_id": "GAP-SMITH-GPS-004",
            "status": "PROTECTED_PROMOTION_PENDING",
            "summary": "CG-01 through CG-08 passed; this deterministic v0.5.9 package is validated in CG-09 before the separate CG-10 protected promotion.",
        },
    ]
    if bundle.get("action_registry_files"):
        raise AssertionError("Smith action routing must remain absent from the candidate package")
    return release, bundle


def candidate_zip(base_bytes: bytes, release: dict, registry: dict) -> bytes:
    replacements = {
        RELEASE_ARCHIVE_PATH: canonical_json_bytes(release),
        REGISTRY_ARCHIVE_PATH: canonical_json_bytes(registry),
    }
    output = io.BytesIO()
    with ZipFile(io.BytesIO(base_bytes)) as base_archive, ZipFile(
        output, "w", compression=ZIP_DEFLATED, compresslevel=9
    ) as candidate_archive:
        base_names = base_archive.namelist()
        names = sorted(set(base_names) | set(replacements))
        if len(names) != len(base_names) + 1:
            raise AssertionError("Smith package must add exactly one release entry")
        for name in names:
            data = replacements.get(name)
            if data is None:
                data = base_archive.read(name)
            info = ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            candidate_archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    base_bytes = b"".join(
        part.read_bytes() for part in sorted(RUNTIME_PARTS.glob("part.*"))
    )
    base_sha = hashlib.sha256(base_bytes).hexdigest()
    if base_sha != BASE_RUNTIME_SHA256:
        raise AssertionError(f"Unexpected production runtime SHA: {base_sha}")

    release, bundle = build_release_and_bundle(output_dir)
    with ZipFile(io.BytesIO(base_bytes)) as archive:
        if RELEASE_ARCHIVE_PATH in archive.namelist():
            raise AssertionError("Smith is already present in the production runtime")
        registry = json.loads(archive.read(REGISTRY_ARCHIVE_PATH))
    if registry.get("engine_version") != ENGINE_VERSION:
        raise AssertionError(f"Unexpected production engine: {registry.get('engine_version')}")
    if registry.get("registry_artifact_version") != BASE_REGISTRY_VERSION:
        raise AssertionError(
            f"Unexpected production registry: {registry.get('registry_artifact_version')}"
        )
    if any(row.get("adapter_id") == "ADAPTER-TX-SMITH" for row in registry.get("bundles") or []):
        raise AssertionError("Smith bundle already exists in production registry")

    candidate_registry = copy.deepcopy(registry)
    candidate_registry["registry_artifact_version"] = CANDIDATE_REGISTRY_VERSION
    candidate_registry["bundles"].append(bundle)
    candidate_registry.pop("canonical_content_sha256", None)
    candidate_registry["canonical_content_sha256"] = canonical_sha(candidate_registry)

    package = candidate_zip(base_bytes, release, candidate_registry)
    package_sha = hashlib.sha256(package).hexdigest()
    package_path = output_dir / "civic_gps_smith_candidate_runtime.zip"
    package_path.write_bytes(package)
    write_json(output_dir / RELEASE_NAME, release)
    write_json(output_dir / "smith-registry-bundle.json", bundle)
    write_json(output_dir / "candidate-registry.json", candidate_registry)

    with ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        archived_registry = json.loads(archive.read(REGISTRY_ARCHIVE_PATH))
        archived_release = json.loads(archive.read(RELEASE_ARCHIVE_PATH))
    if len(names) != 20 or len(names) != len(set(names)):
        raise AssertionError(f"Expected 20 unique candidate entries, got {len(names)}")
    if archived_registry != candidate_registry or archived_release != release:
        raise AssertionError("Candidate archive content differs from emitted canonical artifacts")

    manifest = {
        "status": "PASS",
        "gate": "CG-09",
        "county": "Smith County, TX",
        "geoid": "48423",
        "base_runtime_sha256": base_sha,
        "candidate_runtime_sha256": package_sha,
        "production_runtime_changed": False,
        "engine_version": ENGINE_VERSION,
        "base_registry_artifact_version": BASE_REGISTRY_VERSION,
        "candidate_registry_artifact_version": CANDIDATE_REGISTRY_VERSION,
        "candidate_registry_canonical_sha256": candidate_registry["canonical_content_sha256"],
        "release_canonical_sha256": release["meta"]["canonical_content_sha256"],
        "release_file_sha256": hashlib.sha256(canonical_json_bytes(release)).hexdigest(),
        "bundle_file_sha256": hashlib.sha256(canonical_json_bytes(bundle)).hexdigest(),
        "package_entries": names,
        "package_entry_count": len(names),
        "release_offices": len(release["payload"]["offices"]),
        "release_holders": len(release["payload"]["officeholders"]),
        "bundle_count": len(candidate_registry["bundles"]),
        "smith_action_registry_files": bundle.get("action_registry_files") or [],
        "actions": "NOT_YET_RELEASED",
        "candidate_packaged": True,
        "next_gate": "CG-10",
        "stopped_before": "CG-10",
    }
    write_json(output_dir / "smith-candidate-package-manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    print("SMITH DETERMINISTIC CG-09 CANDIDATE PACKAGE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
