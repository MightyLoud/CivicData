#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "aa0df8386a4f3a30985d1623c623cbb547821b92"
ACTION = "civic_gps_action_registry_brazos_v0.1.json"
ACTION_PATH = f"civic_gps/{ACTION}"
CURRENT_VERSION = "0.6.2"
CANDIDATE_VERSION = "0.6.3"
CURRENT_RUNTIME_SHA = "1969e0e6760bdf4e479bd01fa6976f2ea25dd5fdc14e53d0f4b861cde97549ba"
ACTION_SHA = "3a278953be5461e508b85837a1494b8a4779aa9b11f2631d56b5371a2bb0fbdb"
PART_SIZE = 8000


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def old_runtime_bytes() -> bytes:
    return b"".join(
        subprocess.check_output(["git", "show", f"{OLD}:civic_gps_runtime_parts/part.{i:02d}"])
        for i in range(8)
    )


def must_replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"expected text missing: {label}")
    return text.replace(old, new)


# Recover exact governed Brazos action payload from PR #18.
old_zip = Path("/tmp/old-brazos.zip")
old_zip.write_bytes(old_runtime_bytes())
with zipfile.ZipFile(old_zip) as archive:
    action_bytes = archive.read(ACTION_PATH)
    action_obj = json.loads(action_bytes)
if action_obj.get("meta", {}).get("route_count") != 23:
    raise RuntimeError("historical Brazos route count drift")
action_check = copy.deepcopy(action_obj)
recorded_action_sha = action_check["meta"].pop("canonical_content_sha256", None)
if recorded_action_sha != ACTION_SHA or recorded_action_sha != canonical_sha(action_check):
    raise RuntimeError("historical Brazos action canonical hash drift")

# Reconstruct current governed runtime and prove exact starting point.
part_dir = ROOT / "civic_gps_runtime_parts"
current_parts = sorted(part_dir.glob("part.*"))
if not current_parts:
    raise RuntimeError("current runtime parts missing")
current_bytes = b"".join(part.read_bytes() for part in current_parts)
if hashlib.sha256(current_bytes).hexdigest() != CURRENT_RUNTIME_SHA:
    raise RuntimeError("current runtime SHA drift before build")
current_zip = Path("/tmp/current-runtime.zip")
current_zip.write_bytes(current_bytes)
with zipfile.ZipFile(current_zip) as archive:
    infos = archive.infolist()
    payload = {info.filename: archive.read(info.filename) for info in infos}
registry = json.loads(payload["civic_gps/registry.json"])
if registry.get("engine_version") != "0.6.2":
    raise RuntimeError("current engine version drift")
if registry.get("registry_artifact_version") != CURRENT_VERSION:
    raise RuntimeError("current registry version drift")
if len(registry.get("bundles", [])) != 14:
    raise RuntimeError("current bundle count drift")

bundle = next(row for row in registry["bundles"] if row.get("adapter_id") == "ADAPTER-TX-BRAZOS")
if bundle.get("action_registry_files"):
    raise RuntimeError("Brazos action routing already exists unexpectedly")

# Apply only the governed action-routing delta to the current Brazos bundle.
bundle["action_registry_files"] = [ACTION]
action_coverage = [row for row in bundle.get("coverage_rules", []) if row.get("layer") == "brazos_action_endpoints"]
if len(action_coverage) != 1 or action_coverage[0].get("status") != "NOT_YET_RELEASED":
    raise RuntimeError("current Brazos action coverage drift")
action_coverage[0]["status"] = "RELEASE_BACKED"
action_coverage[0]["reason"] = (
    "Brazos County action routing v0.1 provides 23 verified official routes: five Commissioners Court routes, "
    "six countywide contacts, and twelve precinct contacts."
)
gaps = {row.get("gap_id"): row for row in bundle.get("known_gaps", [])}
for required in ("GAP-BRAZOS-GPS-001", "GAP-BRAZOS-GPS-002", "GAP-BRAZOS-GPS-003"):
    if required not in gaps:
        raise RuntimeError(f"missing Brazos gap {required}")
gaps["GAP-BRAZOS-GPS-001"].update(
    status="CLOSED",
    summary=(
        "Brazos County action routing v0.1 is release-backed with 23 verified routes; normal interiors return 14 "
        "and shared boundaries suppress the three ambiguous precinct routes."
    ),
)
gaps["GAP-BRAZOS-GPS-003"].update(
    status="CLOSED",
    summary=(
        "Brazos geography and office applicability were promoted through PR #15; action routing is governed by "
        "the maintained packaged release gate."
    ),
)
registry["registry_artifact_version"] = CANDIDATE_VERSION
payload["civic_gps/registry.json"] = (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
payload[ACTION_PATH] = action_bytes

# Deterministically repack, preserving current entry order/metadata and appending only the new action file.
out_zip = Path("/tmp/civic_gps_runtime_candidate.zip")
with zipfile.ZipFile(out_zip, "w") as output:
    for info in infos:
        clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        clone.compress_type = info.compress_type
        clone.comment = info.comment
        clone.extra = info.extra
        clone.internal_attr = info.internal_attr
        clone.external_attr = info.external_attr
        clone.create_system = info.create_system
        output.writestr(clone, payload[info.filename])
    new_info = zipfile.ZipInfo(ACTION_PATH, date_time=(2026, 8, 11, 0, 0, 0))
    new_info.compress_type = zipfile.ZIP_DEFLATED
    new_info.create_system = 3
    new_info.external_attr = 0o100644 << 16
    output.writestr(new_info, action_bytes)
candidate_bytes = out_zip.read_bytes()
candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()

for part in current_parts:
    part.unlink()
for index, start in enumerate(range(0, len(candidate_bytes), PART_SIZE)):
    (part_dir / f"part.{index:02d}").write_bytes(candidate_bytes[start : start + PART_SIZE])

# Recover exact deterministic action-selection proof and bind it to registry 0.6.3.
action_probe = subprocess.check_output(["git", "show", f"{OLD}:tests/civic_gps_brazos_action_probe.py"]).decode("utf-8")
action_probe = action_probe.replace("registry v0.6.1", "registry v0.6.3")
action_probe = action_probe.replace('"0.6.1")', '"0.6.3")')
(ROOT / "tests/civic_gps_brazos_action_probe.py").write_text(action_probe, encoding="utf-8")

# Patch the current, newer Brazos packaged/live proof without replacing its topology logic.
probe_path = ROOT / "tests/civic_gps_brazos_live_probe.py"
text = probe_path.read_text(encoding="utf-8")
text = must_replace(
    text,
    '"""Packaged Brazos County regression for Civic GPS v0.6.2 / registry v0.5.9."""',
    '"""Packaged Brazos County regression for Civic GPS v0.6.2 / registry v0.6.3."""',
    "Brazos probe docstring",
)
text = must_replace(
    text,
    'RELEASE_PATH = GPS / "civic_gps_brazos_county_v0.1.json"\n',
    'RELEASE_PATH = GPS / "civic_gps_brazos_county_v0.1.json"\nACTION_FILE = "civic_gps_action_registry_brazos_v0.1.json"\n',
    "action file constant",
)
text = must_replace(
    text,
    'EXPECTED_REGISTRY_VERSION = os.environ.get("CIVIC_GPS_EXPECTED_REGISTRY_VERSION", "0.5.9")',
    'EXPECTED_REGISTRY_VERSION = os.environ.get("CIVIC_GPS_EXPECTED_REGISTRY_VERSION", "0.6.3")',
    "registry default",
)
text, n = re.subn(
    r'EXPECTED_RUNTIME_SHA256 = os\.environ\.get\(\n    "CIVIC_GPS_EXPECTED_RUNTIME_SHA256",\n    "[0-9a-f]{64}",\n\)',
    f'EXPECTED_RUNTIME_SHA256 = os.environ.get(\n    "CIVIC_GPS_EXPECTED_RUNTIME_SHA256",\n    "{candidate_sha}",\n)',
    text,
    count=1,
)
if n != 1:
    raise RuntimeError("runtime SHA default replacement failed")
countywide = '''COUNTYWIDE_IDS = {
    "office-us-tx-brazos-county-judge",
    "office-us-tx-brazos-county-sheriff",
    "office-us-tx-brazos-county-clerk",
    "office-us-tx-brazos-county-district-clerk",
    "office-us-tx-brazos-county-tax-assessor-collector",
    "office-us-tx-brazos-county-treasurer",
}
'''
base_actions = '''BASE_ACTION_IDS = {
    "ACT-BRAZOS-COMMISSIONERS-AGENDAS",
    "ACT-BRAZOS-COMMISSIONERS-CALENDAR",
    "ACT-BRAZOS-COMMISSIONERS-CONTACT",
    "ACT-BRAZOS-COMMISSIONERS-PUBLIC-COMMENT",
    "ACT-BRAZOS-COMMISSIONERS-WATCH",
    "ACT-BRAZOS-CONTACT-COUNTY-CLERK",
    "ACT-BRAZOS-CONTACT-COUNTY-JUDGE",
    "ACT-BRAZOS-CONTACT-DISTRICT-CLERK",
    "ACT-BRAZOS-CONTACT-SHERIFF",
    "ACT-BRAZOS-CONTACT-TAX-ASSESSOR",
    "ACT-BRAZOS-CONTACT-TREASURER",
}
'''
text = must_replace(text, countywide, countywide + base_actions, "base action ids")
old_assert = '''def assert_no_actions(label: str, payload: dict) -> None:
    actions = [
        row
        for row in payload.get("action_links") or []
        if row.get("jurisdiction_id") == J
    ]
    if actions:
        raise AssertionError(f"[{label}] Brazos actions must remain unreleased: {actions}")
'''
new_assert = '''def assert_brazos_actions(label: str, payload: dict, district_key: str | None) -> None:
    action_ids = {
        row.get("action_id")
        for row in payload.get("action_links") or []
        if row.get("jurisdiction_id") == J
    }
    expected = set(BASE_ACTION_IDS)
    if district_key is not None:
        expected.update({
            f"ACT-BRAZOS-CONTACT-COMMISSIONER-P{district_key}",
            f"ACT-BRAZOS-CONTACT-JP-P{district_key}",
            f"ACT-BRAZOS-CONTACT-CONSTABLE-P{district_key}",
        })
    if action_ids != expected:
        raise AssertionError(
            f"[{label}] expected {len(expected)} Brazos actions {sorted(expected)}, "
            f"got {len(action_ids)} {sorted(action_ids)}"
        )
    coverage = [row for row in payload.get("coverage") or [] if row.get("layer") == "brazos_action_endpoints"]
    if len(coverage) != 1 or coverage[0].get("status") != "RELEASE_BACKED":
        raise AssertionError(f"[{label}] Brazos action coverage is not release-backed: {coverage}")
'''
text = must_replace(text, old_assert, new_assert, "action assertion")
text = must_replace(
    text,
    '    release = json.loads(runtime_archive.read(f"civic_gps/{RELEASE_PATH.name}"))\n',
    '    release = json.loads(runtime_archive.read(f"civic_gps/{RELEASE_PATH.name}"))\n    action_registry = json.loads(runtime_archive.read(f"civic_gps/{ACTION_FILE}"))\n',
    "read action registry",
)
text = must_replace(
    text,
    'if bundle.get("action_registry_files"):\n    raise AssertionError("Brazos action routing must remain unreleased in CG-09")',
    'if bundle.get("action_registry_files") != [ACTION_FILE]:\n    raise AssertionError(f"Unexpected Brazos action registry files: {bundle.get(\'action_registry_files\')}")\nif action_registry.get("meta", {}).get("route_count") != 23:\n    raise AssertionError("Packaged Brazos action registry must contain exactly 23 routes")',
    "bundle action pointer",
)
old_gap = '''gap = next(
    (row for row in bundle.get("known_gaps", []) if row.get("gap_id") == "GAP-BRAZOS-GPS-003"),
    None,
)
if not gap or gap.get("status") != "PROTECTED_PROMOTION_PENDING":
    raise AssertionError(f"Brazos package gap state changed: {gap}")
'''
new_gap = '''gap_statuses = {row.get("gap_id"): row.get("status") for row in bundle.get("known_gaps", [])}
if gap_statuses != {
    "GAP-BRAZOS-GPS-001": "CLOSED",
    "GAP-BRAZOS-GPS-002": "BOUNDED_V0_1_SCOPE",
    "GAP-BRAZOS-GPS-003": "CLOSED",
}:
    raise AssertionError(f"Brazos package gap state changed: {gap_statuses}")
'''
text = must_replace(text, old_gap, new_gap, "gap statuses")
text = must_replace(text, "assert_no_actions(case_id, payload)", "assert_brazos_actions(case_id, payload, key)", "interior actions")
text = must_replace(text, "assert_no_actions(\"boundary-exact\", exact)", "assert_brazos_actions(\"boundary-exact\", exact, None)", "boundary actions")
text = must_replace(text, 'assert_no_actions(f"boundary-{label}", payload)', 'assert_brazos_actions(f"boundary-{label}", payload, expected_key)', "boundary side actions")
text = text.replace('"applicable_offices": 9,\n            "resolution_attempts": attempts,', '"applicable_offices": 9,\n            "action_links": 14,\n            "resolution_attempts": attempts,')
text = text.replace('"applicable_offices": 9,\n            "status": "PASS",', '"applicable_offices": 9,\n            "action_links": 14,\n            "status": "PASS",')
text = must_replace(text, '"exact_applicable_offices": 6,\n        "exact_conflict_layers":', '"exact_applicable_offices": 6,\n        "exact_action_links": 11,\n        "exact_conflict_layers":', "boundary summary")
text = must_replace(
    text,
    '"actions": "NOT_YET_RELEASED",',
    '"actions": {"status": "RELEASE_BACKED", "registry": ACTION_FILE, "verified_routes": 23, "normal_interior_links": 14, "shared_boundary_links": 11},',
    "actions summary",
)
probe_path.write_text(text, encoding="utf-8")

# Update current protected release gate.
workflow_path = ROOT / ".github/workflows/civic-gps-live-smoke.yml"
workflow = workflow_path.read_text(encoding="utf-8")
workflow = must_replace(workflow, "CIVIC_GPS_EXPECTED_REGISTRY_VERSION: '0.6.2'", "CIVIC_GPS_EXPECTED_REGISTRY_VERSION: '0.6.3'", "workflow registry")
workflow = must_replace(workflow, "CIVIC_GPS_EXPECTED_RUNTIME_SHA256: '1969e0e6760bdf4e479bd01fa6976f2ea25dd5fdc14e53d0f4b861cde97549ba'", f"CIVIC_GPS_EXPECTED_RUNTIME_SHA256: '{candidate_sha}'", "workflow runtime env")
workflow = must_replace(workflow, "echo '1969e0e6760bdf4e479bd01fa6976f2ea25dd5fdc14e53d0f4b861cde97549ba  civic_gps_runtime.zip'", f"echo '{candidate_sha}  civic_gps_runtime.zip'", "workflow runtime checksum")
workflow = must_replace(workflow, "      - 'tests/civic_gps_brazos_live_probe.py'\n", "      - 'tests/civic_gps_brazos_live_probe.py'\n      - 'tests/civic_gps_brazos_action_probe.py'\n", "workflow action path")
workflow = must_replace(workflow, "tests/civic_gps_brazos_live_probe.py tests/civic_gps_smith_live_probe.py", "tests/civic_gps_brazos_live_probe.py tests/civic_gps_brazos_action_probe.py tests/civic_gps_smith_live_probe.py", "workflow compile action probe")
workflow = must_replace(
    workflow,
    "      - name: Run packaged Smith County archetype controls\n",
    "      - name: Run Brazos action selection contract\n        if: github.event_name != 'pull_request' || steps.scope.outputs.run == 'true'\n        run: python tests/civic_gps_brazos_action_probe.py\n\n      - name: Run packaged Smith County archetype controls\n",
    "workflow action step",
)
workflow_path.write_text(workflow, encoding="utf-8")

# Narrow documentation updates only.
doc_path = ROOT / "docs/workflows/civic-gps-live-smoke.md"
doc = doc_path.read_text(encoding="utf-8")
doc = must_replace(doc, CURRENT_RUNTIME_SHA, candidate_sha, "live smoke SHA")
doc = must_replace(doc, "- Adapter registry artifact: `v0.6.2`", "- Adapter registry artifact: `v0.6.3`", "live smoke registry version")
doc = must_replace(
    doc,
    "Brazos release scope is 18 offices / 18 holders = 6 deliberately bounded countywide + 4 Commissioner + 4 JP + 4 Constable. Brazos action routing remains `NOT_YET_RELEASED`; additional countywide and judicial offices remain `BOUNDED_V0_1_SCOPE`. Boundary conflicts remain `MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK`.",
    "Brazos release scope is 18 offices / 18 holders = 6 deliberately bounded countywide + 4 Commissioner + 4 JP + 4 Constable. Brazos action routing v0.1 adds 23 verified routes: normal interiors return 14 Brazos action links (11 body/countywide + 3 matching precinct contacts), while an exact shared precinct boundary returns 11 and suppresses all three ambiguous precinct contacts. Additional countywide and judicial offices remain `BOUNDED_V0_1_SCOPE`. Boundary conflicts remain `MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK`.",
    "Brazos live-smoke docs",
)
doc_path.write_text(doc, encoding="utf-8")

archetype_path = ROOT / "docs/workflows/civic-gps-county-archetype.md"
archetype = archetype_path.read_text(encoding="utf-8")
archetype = must_replace(
    archetype,
    "Brazos action routing remains `NOT_YET_RELEASED`; additional countywide and judicial offices remain `BOUNDED_V0_1_SCOPE`.",
    "Brazos action routing v0.1 is release-backed with 23 verified routes: normal interiors return 14 action links and an exact shared precinct boundary returns 11 after all three ambiguous precinct contacts are suppressed. Additional countywide and judicial offices remain `BOUNDED_V0_1_SCOPE`.",
    "Brazos archetype docs",
)
archetype_path.write_text(archetype, encoding="utf-8")

# Temporary build/recovery controls must not survive into the candidate commit.
for temporary in (
    ROOT / ".github/workflows/brazos-action-recovery.yml",
    ROOT / ".github/workflows/brazos-action-build-once.yml",
    ROOT / "tools/build_brazos_candidate_once.py",
):
    if temporary.exists():
        temporary.unlink()

print(json.dumps({
    "status": "BUILT",
    "registry_version": CANDIDATE_VERSION,
    "bundle_count": 14,
    "runtime_sha256": candidate_sha,
    "brazos_action_sha256": ACTION_SHA,
    "route_count": 23,
}, sort_keys=True))
