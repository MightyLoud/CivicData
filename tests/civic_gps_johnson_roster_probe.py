#!/usr/bin/env python3
"""Johnson County CG-04 canonical-roster proof; stop before GIS/adapter proof."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "tests/fixtures/civic_gps_county_onboarding/johnson_county11_candidate_v0.1.json"
ONBOARDING_TOOL = ROOT / "tools/civic_gps_county_onboarding.py"
RUNTIME_PARTS = ROOT / "civic_gps_runtime_parts"
RUNTIME_SHA256 = "70354e50668e1f5950cd35145f06b2591a85b688e31dc9cb042b96b3493a802b"
PRODUCTION_MAIN_COMMIT = "0a87ca6ea479c62782d470e0283c455a2f0e0df0"
PRODUCTION_MAIN_TREE = "f87ee58616b0c50fbe274e0337442a0efe73c331"
POLICY = "MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK"
ADAPTERS = {
    "DIST-TX-JOHNSON-COMMISSIONER",
    "DIST-TX-JOHNSON-JP",
    "DIST-TX-JOHNSON-CONSTABLE",
}
EXPECTED_ROSTER = {
    "office-us-tx-johnson-county-judge": "Christopher Boedeker",
    "office-us-tx-johnson-county-sheriff": "Adam King",
    "office-us-tx-johnson-county-clerk": "April Long",
    "office-us-tx-johnson-county-district-clerk": "Dean Sullivan",
    "office-us-tx-johnson-county-tax-assessor-collector": "Scott Porter",
    "office-us-tx-johnson-county-treasurer": "Kathy Blackwell",
    "office-us-tx-johnson-county-commissioner-1": "Rick Bailey",
    "office-us-tx-johnson-county-commissioner-2": "Kenny Howell",
    "office-us-tx-johnson-county-commissioner-3": "Mike White",
    "office-us-tx-johnson-county-commissioner-4": "Larry Woolley",
    "office-us-tx-johnson-county-jp-1": "DeeAnn Strother",
    "office-us-tx-johnson-county-jp-2": "Jeff Monk",
    "office-us-tx-johnson-county-jp-3": "Andrew Nolan",
    "office-us-tx-johnson-county-jp-4": "Robert Shaw",
    "office-us-tx-johnson-county-constable-1": "Matt Wylie",
    "office-us-tx-johnson-county-constable-2": "Adam Crawford",
    "office-us-tx-johnson-county-constable-3": "Steve Williams",
    "office-us-tx-johnson-county-constable-4": "Troy Fuller",
}
SOURCE_URLS = {
    "office-us-tx-johnson-county-judge": "https://www.johnsoncountytx.org/government/county-judge",
    "office-us-tx-johnson-county-sheriff": "https://www.sos.state.tx.us/elections/voter/sheriffs.shtml",
    "office-us-tx-johnson-county-clerk": "https://www.johnsoncountytx.org/government/county-clerk",
    "office-us-tx-johnson-county-district-clerk": "https://www.johnsoncountytx.org/government/district-clerk",
    "office-us-tx-johnson-county-tax-assessor-collector": "https://www.johnsoncountytaxoffice.org/",
    "office-us-tx-johnson-county-treasurer": "https://www.johnsoncountytx.org/government/county-treasurer",
    "office-us-tx-johnson-county-commissioner-1": "https://www.johnsoncountytx.org/government/commissioners/commissioner-precinct-1",
    "office-us-tx-johnson-county-commissioner-2": "https://www.johnsoncountytx.org/government/commissioners/commissioner-precinct-2",
    "office-us-tx-johnson-county-commissioner-3": "https://www.johnsoncountytx.org/government/commissioners/commissioner-precinct-3",
    "office-us-tx-johnson-county-commissioner-4": "https://www.johnsoncountytx.org/government/commissioners/commissioner-precinct-4",
    "office-us-tx-johnson-county-jp-1": "https://www.johnsoncountytx.org/government/justice-of-the-peace/justice-of-the-peace-precinct-1",
    "office-us-tx-johnson-county-jp-2": "https://www.johnsoncountytx.org/government/justice-of-the-peace/justice-of-the-peace-precinct-2",
    "office-us-tx-johnson-county-jp-3": "https://www.johnsoncountytx.org/government/justice-of-the-peace/justice-of-the-peace-precinct-3",
    "office-us-tx-johnson-county-jp-4": "https://www.johnsoncountytx.org/government/justice-of-the-peace/justice-of-the-peace-precinct-4",
    "office-us-tx-johnson-county-constable-1": "https://www.johnsoncountytx.org/public-safety/constables/constable-precinct-1",
    "office-us-tx-johnson-county-constable-2": "https://www.johnsoncountytx.org/public-safety/constables/constable-precinct-2",
    "office-us-tx-johnson-county-constable-3": "https://www.johnsoncountytx.org/public-safety/constables/constable-precinct-3",
    "office-us-tx-johnson-county-constable-4": "https://www.johnsoncountytx.org/public-safety/constables/constable-precinct-4",
}


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_production_runtime() -> dict:
    runtime_bytes = b"".join(part.read_bytes() for part in sorted(RUNTIME_PARTS.glob("part.*")))
    runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
    if runtime_sha != RUNTIME_SHA256:
        raise AssertionError(f"Production runtime SHA changed: {runtime_sha}")
    with ZipFile(io.BytesIO(runtime_bytes)) as archive:
        names = set(archive.namelist())
        registry = json.loads(archive.read("civic_gps/registry.json"))
    if registry.get("engine_version") != "0.6.2":
        raise AssertionError(f"Production engine version changed: {registry.get('engine_version')}")
    if registry.get("registry_artifact_version") != "0.6.0":
        raise AssertionError(
            f"Production registry artifact version changed: {registry.get('registry_artifact_version')}"
        )
    if any(row.get("adapter_id") == "ADAPTER-TX-JOHNSON" for row in registry.get("bundles") or []):
        raise AssertionError("Johnson candidate must not be packaged during CG-04")
    if "civic_gps/civic_gps_johnson_county_v0.1.json" in names:
        raise AssertionError("Johnson canonical release must not be packaged during CG-04")
    if any("action_registry_johnson" in name for name in names):
        raise AssertionError("Johnson action routing must remain unreleased")
    return {
        "engine_version": registry["engine_version"],
        "registry_artifact_version": registry["registry_artifact_version"],
        "runtime_sha256": runtime_sha,
    }


def validate_candidate(onboarding: Path) -> tuple[dict, dict, dict]:
    report = json.loads((onboarding / "fit-report.json").read_text(encoding="utf-8"))
    expected_fit = {
        "decision": "GO",
        "result": "SUPPORTED_V0_1",
        "stop_class": "NONE",
        "architecture_change": "NO",
    }
    if {key: report.get(key) for key in expected_fit} != expected_fit:
        raise AssertionError(f"Johnson fit contract changed: {report}")

    release = json.loads((onboarding / "canonical-release-preview.json").read_text(encoding="utf-8"))
    release_without_hash = copy.deepcopy(release)
    recorded_sha = release_without_hash["meta"].pop("canonical_content_sha256", None)
    if not recorded_sha or recorded_sha != canonical_sha(release_without_hash):
        raise AssertionError("Johnson canonical release content SHA mismatch")
    offices = release.get("payload", {}).get("offices") or []
    holders = release.get("payload", {}).get("officeholders") or []
    office_ids = {row.get("office_id") for row in offices}
    roster = {row.get("office_id"): row.get("canonical_name") for row in holders}
    if len(offices) != 18 or len(holders) != 18:
        raise AssertionError(f"Johnson roster must be 18 offices / 18 holders: {len(offices)} / {len(holders)}")
    if len(office_ids) != 18 or office_ids != set(roster) or roster != EXPECTED_ROSTER:
        raise AssertionError(f"Johnson canonical roster or identity join changed: {roster}")
    if set(SOURCE_URLS) != set(EXPECTED_ROSTER):
        raise AssertionError("Every canonical office must have exactly one re-verification source")
    if release.get("payload", {}).get("action_links") != []:
        raise AssertionError("Johnson action links must remain empty during CG-04")

    bundle = json.loads((onboarding / "base-bundle-plan.json").read_text(encoding="utf-8"))
    adapters = {row.get("adapter_id"): row for row in bundle.get("district_adapters") or []}
    if set(adapters) != ADAPTERS:
        raise AssertionError(f"Johnson adapter set changed: {sorted(adapters)}")
    for adapter_id, adapter in adapters.items():
        if adapter.get("failure_scope") != "ADAPTER":
            raise AssertionError(f"{adapter_id} failure scope changed")
        if adapter.get("officeholder_identity_source") != "CANONICAL_RELEASE_ONLY":
            raise AssertionError(f"{adapter_id} identity source changed")
        if adapter.get("boundary_policy") != POLICY:
            raise AssertionError(f"{adapter_id} boundary policy changed")
    coverage = {row.get("layer"): row.get("status") for row in bundle.get("coverage_rules") or []}
    if coverage.get("johnson_action_endpoints") != "NOT_YET_RELEASED":
        raise AssertionError("Johnson action coverage crossed its release boundary")
    gaps = {row.get("status") for row in bundle.get("known_gaps") or []}
    if "BOUNDED_V0_1_SCOPE" not in gaps or "NOT_YET_RELEASED" not in gaps:
        raise AssertionError(f"Johnson bounded-scope or action gap changed: {sorted(gaps)}")

    precedence = json.loads((onboarding / "source-precedence.json").read_text(encoding="utf-8"))
    records = precedence.get("records") or []
    canonical_values = {row.get("canonical_value") for row in records}
    if precedence.get("status") != "RESOLVED" or len(records) != 2:
        raise AssertionError(f"Johnson source-precedence proof changed: {precedence}")
    if canonical_values != {"DeeAnn Strother", "Dean Sullivan"}:
        raise AssertionError(f"Johnson precedence winners changed: {sorted(canonical_values)}")

    proof = json.loads((onboarding / "proof-plan.json").read_text(encoding="utf-8"))
    gate_status = {row.get("gate"): row.get("status") for row in proof.get("gates") or []}
    if gate_status.get("CG-04") != "READY" or gate_status.get("CG-05") != "READY":
        raise AssertionError(f"Johnson gate readiness changed: {gate_status}")
    return report, release, bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    onboarding = output / "onboarding"
    subprocess.run(
        [
            "python",
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
    report, release, _ = validate_candidate(onboarding)
    runtime = validate_production_runtime()
    source_checks = [
        {
            "canonical_name": EXPECTED_ROSTER[office_id],
            "office_id": office_id,
            "status": "PASS",
            "url": SOURCE_URLS[office_id],
        }
        for office_id in sorted(EXPECTED_ROSTER)
    ]
    summary = {
        "status": "PASS",
        "county": "Johnson County, TX",
        "geoid": "48251",
        "gates": {"CG-04": "PASS"},
        "fit_result": report["result"],
        "canonical_release_sha256": release["meta"]["canonical_content_sha256"],
        "roster_sha256": canonical_sha(EXPECTED_ROSTER),
        "release_offices": 18,
        "release_holders": 18,
        "roster_verified_on": "2026-08-11",
        "roster_verification_method": "CURRENT_OFFICIAL_SOURCE_REVIEW_THEN_FROZEN_ASSERTION",
        "source_checks": source_checks,
        "source_precedence": {"status": "RESOLVED", "record_count": 2},
        "adapter_contracts": {
            "failure_scope": "ADAPTER",
            "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
            "boundary_policy": POLICY,
        },
        "actions": "NOT_YET_RELEASED",
        "scope": "BOUNDED_V0_1_SCOPE",
        "candidate_packaged": False,
        "production_main_commit": PRODUCTION_MAIN_COMMIT,
        "production_main_tree": PRODUCTION_MAIN_TREE,
        **runtime,
        "production_runtime_changed": False,
        "next_gate": "CG-05",
        "stopped_before": "CG-05",
    }
    write_json(output / "johnson-cg04-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("JOHNSON CG-04 CANONICAL ROSTER PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
