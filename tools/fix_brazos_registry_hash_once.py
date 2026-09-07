#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "civic_gps_runtime_parts"
OLD_RUNTIME_SHA = "a1d323db8ed7eaaa47e3541a42bacef4377e9c41161f7a2ad888ddf86e5fe192"
PART_SIZE = 8000


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


parts = sorted(PARTS.glob("part.*"))
if not parts:
    raise RuntimeError("runtime parts missing")
raw = b"".join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest() != OLD_RUNTIME_SHA:
    raise RuntimeError("unexpected candidate runtime SHA before registry-hash correction")

src = Path("/tmp/brazos-candidate-before-registry-hash.zip")
src.write_bytes(raw)
with zipfile.ZipFile(src) as zin:
    infos = zin.infolist()
    payload = {info.filename: zin.read(info.filename) for info in infos}

registry = json.loads(payload["civic_gps/registry.json"])
if registry.get("engine_version") != "0.6.2" or registry.get("registry_artifact_version") != "0.6.3":
    raise RuntimeError("unexpected engine/registry version")
if len(registry.get("bundles", [])) != 14:
    raise RuntimeError("unexpected bundle count")
brazos = next(row for row in registry["bundles"] if row.get("adapter_id") == "ADAPTER-TX-BRAZOS")
if brazos.get("action_registry_files") != ["civic_gps_action_registry_brazos_v0.1.json"]:
    raise RuntimeError("Brazos action pointer missing before registry-hash correction")

without_hash = copy.deepcopy(registry)
old_recorded = without_hash.pop("canonical_content_sha256", None)
correct_hash = canonical_sha(without_hash)
if old_recorded == correct_hash:
    raise RuntimeError("registry hash unexpectedly already correct")
registry["canonical_content_sha256"] = correct_hash
payload["civic_gps/registry.json"] = (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

out = Path("/tmp/brazos-candidate-registry-hash-corrected.zip")
with zipfile.ZipFile(out, "w") as zout:
    for info in infos:
        clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        clone.compress_type = info.compress_type
        clone.comment = info.comment
        clone.extra = info.extra
        clone.internal_attr = info.internal_attr
        clone.external_attr = info.external_attr
        clone.create_system = info.create_system
        clone.flag_bits = info.flag_bits
        zout.writestr(clone, payload[info.filename])
corrected = out.read_bytes()
new_runtime_sha = hashlib.sha256(corrected).hexdigest()

for p in parts:
    p.unlink()
for index, start in enumerate(range(0, len(corrected), PART_SIZE)):
    (PARTS / f"part.{index:02d}").write_bytes(corrected[start:start + PART_SIZE])

# Update only active non-workflow runtime-integrity pins. Historical receipts/contracts remain untouched.
active_files = [
    ROOT / "tests/civic_gps_legislative_overlay_test.py",
    ROOT / "services/texas_bounded_api/Dockerfile",
    ROOT / "docs/workflows/civic-gps-live-smoke.md",
]
for path in active_files:
    text = path.read_text(encoding="utf-8")
    if OLD_RUNTIME_SHA not in text:
        raise RuntimeError(f"active old runtime SHA missing from {path.relative_to(ROOT)}")
    path.write_text(text.replace(OLD_RUNTIME_SHA, new_runtime_sha), encoding="utf-8")

print(json.dumps({
    "status": "CORRECTED",
    "old_recorded_registry_sha256": old_recorded,
    "canonical_registry_sha256": correct_hash,
    "old_runtime_sha256": OLD_RUNTIME_SHA,
    "runtime_sha256": new_runtime_sha,
    "engine_version": "0.6.2",
    "registry_artifact_version": "0.6.3",
    "bundle_count": 14,
    "brazos_routes": 23,
}, sort_keys=True))
