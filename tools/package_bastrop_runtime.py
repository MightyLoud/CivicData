#!/usr/bin/env python3
"""One-shot deterministic packager for Civic GPS v0.6.1 + Bastrop County."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
ZIP_PATH = ROOT / "civic_gps_runtime.zip"
PARTS = ROOT / "civic_gps_runtime_parts"
ONBOARDING = ROOT / "tools" / "civic_gps_county_onboarding.py"
SPEC = ROOT / "tests" / "fixtures" / "civic_gps_county_onboarding" / "bastrop_county5_candidate_v0.1.json"
OUT = ROOT / "artifacts" / "civic-gps-bastrop-package"
GENERATED = OUT / "onboarding"
OLD_SHA = "567c809839a2bcbafff7da432e28bf7e6fa23e5c2dff9639cf11ad4f87759d60"
EXPECTED_SPEC_SHA = "f91f98ec040c153f12cff82bf5be91ac32dbee3e9616048120a95d6f0c8f0077"
RELEASE_NAME = "civic_gps_bastrop_county_v0.1.json"
BOUNDARY_POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_onboarding_candidate() -> tuple[dict, dict]:
    if GENERATED.exists():
        shutil.rmtree(GENERATED)
    subprocess.run(
        [
            sys.executable,
            str(ONBOARDING),
            str(SPEC),
            "--output-dir",
            str(GENERATED),
            "--expect",
            "SUPPORTED_V0_1",
        ],
        cwd=ROOT,
        check=True,
    )
    report = json.loads((GENERATED / "fit-report.json").read_text(encoding="utf-8"))
    if report.get("decision") != "GO" or report.get("result") != "SUPPORTED_V0_1":
        raise SystemExit(f"Bastrop onboarding fit changed: {report}")
    if report.get("spec_sha256") != EXPECTED_SPEC_SHA:
        raise SystemExit(f"Bastrop frozen spec SHA changed: {report.get('spec_sha256')}")

    release = json.loads((GENERATED / "canonical-release-preview.json").read_text(encoding="utf-8"))
    bundle = json.loads((GENERATED / "base-bundle-plan.json").read_text(encoding="utf-8"))

    # Promote only the generated package copy. The frozen onboarding input remains
    # unchanged as the CG-01 -> CG-08 provenance record.
    release["meta"]["release_status"] = "RELEASE_BACKED_CURRENT"
    release["meta"]["note"] = (
        "Bastrop County is County #6 and the second production candidate generated through "
        "County Onboarding Pipeline v0.1. CG-01 through CG-08 passed on the unchanged Civic "
        "GPS v0.6.1 engine. The bounded release contains six countywide offices plus shared "
        "Commissioner, Justice of the Peace, and Constable precincts 1-4. Civic-action routing "
        "and additional countywide or judicial offices remain explicitly outside v0.1 scope."
    )
    for jurisdiction in release.get("payload", {}).get("jurisdictions", []):
        if jurisdiction.get("jurisdiction_id") == "jur-us-tx-bastrop-county":
            jurisdiction["status"] = "RELEASE_BACKED_CURRENT"
    release_without_hash = copy.deepcopy(release)
    release_without_hash["meta"].pop("canonical_content_sha256", None)
    release["meta"]["canonical_content_sha256"] = canonical_sha(release_without_hash)

    for adapter in bundle.get("district_adapters", []):
        adapter["source_status"] = "LIVE_INTERIOR_NEGATIVE_BOUNDARY_PASS"
    for gap in bundle.get("known_gaps", []):
        if gap.get("gap_id") == "GAP-BASTROP-GPS-003":
            gap["status"] = "PROTECTED_PROMOTION_PENDING"
            gap["summary"] = (
                "CG-01 through CG-08 passed; this deterministic v0.5.6 package is validated in "
                "CG-09 before the separate CG-10 protected promotion."
            )
    return release, bundle


def patch_registry_and_release() -> str:
    release, bundle = build_onboarding_candidate()
    release_path = GPS / RELEASE_NAME
    release_path.write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    registry_path = GPS / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.5":
        raise SystemExit(
            f"unexpected base registry: {registry.get('engine_version')} / "
            f"{registry.get('registry_artifact_version')}"
        )
    if any(row.get("adapter_id") == "ADAPTER-TX-BASTROP" for row in registry.get("bundles", [])):
        raise SystemExit("Bastrop is already present in the base registry")
    engine_sha = sha256(GPS / "engine.py")
    registry["registry_artifact_version"] = "0.5.6"
    registry.setdefault("bundles", []).append(bundle)
    registry["bundles"].sort(key=lambda row: row["adapter_id"])
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return engine_sha


def patch_readme() -> None:
    path = GPS / "README.md"
    text = path.read_text(encoding="utf-8")
    replacements = (
        ("registry artifact v0.5.5", "registry artifact v0.5.6"),
        (
            "The packaged registry now includes nine jurisdiction bundles:",
            "The packaged registry now includes ten jurisdiction bundles:",
        ),
        (
            "8. Williamson County\n9. Tacoma / Pierce County",
            "8. Williamson County\n9. Bastrop County\n10. Tacoma / Pierce County",
        ),
    )
    for old, new in replacements:
        if text.count(old) != 1:
            raise SystemExit(f"README packaging marker changed or is ambiguous: {old!r}")
        text = text.replace(old, new)
    text += (
        "\nBastrop County is County #6 and the second production candidate generated by County "
        "Onboarding Pipeline v0.1. Four permanent interiors cover shared Commissioner, Justice "
        "of the Peace, and Constable precinct keys 1-4; the Austin negative proves county "
        "isolation; and one live-derived shared boundary suppresses all three ambiguous district "
        "families while preserving the six countywide offices. Bastrop action routing and "
        "additional countywide or judicial offices remain explicitly outside the bounded v0.1 "
        "release scope.\n"
    )
    path.write_text(text, encoding="utf-8")


def build_zip() -> None:
    with ZipFile(ZIP_PATH, "w") as archive:
        for path in sorted(GPS.iterdir(), key=lambda item: item.name):
            if path.is_file() and not path.name.startswith("."):
                info = ZipInfo(f"civic_gps/{path.name}", date_time=(2026, 8, 9, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


def verify_candidate(expected_engine_sha: str, runtime_sha: str) -> dict:
    if sha256(GPS / "engine.py") != expected_engine_sha:
        raise SystemExit("Civic GPS engine changed during Bastrop packaging")
    registry = json.loads((GPS / "registry.json").read_text(encoding="utf-8"))
    release = json.loads((GPS / RELEASE_NAME).read_text(encoding="utf-8"))
    if registry.get("engine_version") != "0.6.1" or registry.get("registry_artifact_version") != "0.5.6":
        raise SystemExit("new registry metadata mismatch")
    bundle = next(
        (row for row in registry.get("bundles", []) if row.get("adapter_id") == "ADAPTER-TX-BASTROP"),
        None,
    )
    if not bundle or bundle.get("release_files") != [RELEASE_NAME]:
        raise SystemExit("Bastrop bundle/release linkage mismatch")
    if bundle.get("action_registry_files"):
        raise SystemExit("Bastrop actions must remain unreleased")
    adapters = bundle.get("district_adapters", [])
    if len(adapters) != 3:
        raise SystemExit(f"Bastrop must contain three district adapters, got {len(adapters)}")
    for adapter in adapters:
        if adapter.get("failure_scope") != "ADAPTER":
            raise SystemExit("Bastrop district adapters must remain ADAPTER-scoped")
        if adapter.get("boundary_policy") != BOUNDARY_POLICY:
            raise SystemExit("Bastrop boundary policy changed")
        if adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY":
            raise SystemExit("Bastrop identity source changed")
    offices = release.get("payload", {}).get("offices", [])
    holders = release.get("payload", {}).get("officeholders", [])
    if len(offices) != 18 or len(holders) != 18:
        raise SystemExit("Bastrop release must contain exactly 26 offices/officeholders")
    if {row.get("office_id") for row in offices} != {row.get("office_id") for row in holders}:
        raise SystemExit("Bastrop office/officeholder joins changed")
    release_without_hash = copy.deepcopy(release)
    recorded_release_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
    if recorded_release_sha != canonical_sha(release_without_hash):
        raise SystemExit("Bastrop canonical content SHA mismatch")
    return {
        "status": "PASS",
        "gate": "CG-09",
        "runtime_sha256": runtime_sha,
        "engine_version": "0.6.1",
        "engine_sha256": expected_engine_sha,
        "registry_artifact_version": "0.5.6",
        "bastrop_offices": 18,
        "bastrop_holders": 18,
        "bastrop_actions": "NOT_YET_RELEASED",
        "frozen_spec_sha256": EXPECTED_SPEC_SHA,
        "candidate_packaged": True,
    }


def split_runtime(runtime_sha: str) -> list[dict]:
    for part in PARTS.glob("part.*"):
        part.unlink()
    data = ZIP_PATH.read_bytes()
    for offset in range(0, len(data), 8000):
        (PARTS / f"part.{offset // 8000:02d}").write_bytes(data[offset : offset + 8000])
    reconstructed = hashlib.sha256(
        b"".join(part.read_bytes() for part in sorted(PARTS.glob("part.*")))
    ).hexdigest()
    if reconstructed != runtime_sha:
        raise SystemExit("chunk reconstruction SHA mismatch")
    return [
        {"name": part.name, "size": part.stat().st_size}
        for part in sorted(PARTS.glob("part.*"))
    ]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    current = b"".join(part.read_bytes() for part in sorted(PARTS.glob("part.*")))
    ZIP_PATH.write_bytes(current)
    old_actual = sha256(ZIP_PATH)
    if old_actual != OLD_SHA:
        raise SystemExit(f"old runtime SHA mismatch: {old_actual}")
    if GPS.exists():
        shutil.rmtree(GPS)
    with ZipFile(ZIP_PATH) as archive:
        archive.extractall(ROOT)

    engine_sha = patch_registry_and_release()
    patch_readme()
    build_zip()
    first = sha256(ZIP_PATH)
    build_zip()
    second = sha256(ZIP_PATH)
    if first != second:
        raise SystemExit(f"deterministic build mismatch: {first} != {second}")

    summary = verify_candidate(engine_sha, first)
    summary["deterministic_rebuild_sha256"] = second
    summary["parts"] = split_runtime(first)
    (OUT / "package-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print(f"BASTROP_RUNTIME_SHA={first}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
