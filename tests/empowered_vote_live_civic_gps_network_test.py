#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


live = load_module("ev_live_civic_gps_network", ROOT / "consumers" / "empowered_vote" / "live_civic_gps.py")
pkg_mod = load_module("ev_package_source_network", ROOT / "consumers" / "empowered_vote" / "package_source.py")
PACKAGE_DIR = ROOT / "data" / "packages" / "wa" / "tacoma"
PARTS = [
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part01a",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part01b",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part02",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part03",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part04",
]
EXPECTED_ZIP_SHA256 = "2c6219303eff3f49b4202f72048910ba970cd65353032b6bfda2975791701d53"


def package_from_mainline():
    encoded = "".join(p.read_text(encoding="utf-8") for p in PARTS)
    raw = base64.b64decode(encoded)
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_ZIP_SHA256
    tmp = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(tmp.name)
    package_dir = next(Path(tmp.name).glob("Tacoma_Jurisdiction_Package_v0.2_2026-08-23/package"))
    return tmp, pkg_mod.load_jurisdiction_package(package_dir)


def main() -> int:
    tmp, package = package_from_mainline()
    try:
        resolver = live.load_default_civic_gps_resolver(ROOT, timeout_seconds=30.0)
        controls = [
            ("market", "747 Market Street, Tacoma, WA 98402", "2", 6, 5, 15),
            ("wapato", "6500 South Sheridan Avenue, Tacoma, WA 98408", "5", 6, 5, 15),
            ("lakewood", "6000 Main St SW, Lakewood, WA 98499", None, 0, 0, 0),
        ]
        summaries = []
        for control_id, address, expected_district, offices, contests, candidates in controls:
            model = live.build_essentials_from_live_civic_gps(package, address, resolver)
            if model.get("status") != "PASS":
                raise AssertionError(f"{control_id}: {model}")
            got_offices = len(model["applicable_offices"])
            got_contests = len(model["recent_certified_contests"])
            got_candidates = sum(len(x["candidates"]) for x in model["recent_certified_contests"])
            if (got_offices, got_contests, got_candidates) != (offices, contests, candidates):
                raise AssertionError(
                    f"{control_id}: expected {(offices, contests, candidates)}, got {(got_offices, got_contests, got_candidates)}"
                )
            if expected_district is None:
                if model["jurisdiction"] is not None:
                    raise AssertionError(f"{control_id}: Tacoma unexpectedly active")
            else:
                got_district = model["district_assignments"].get("DIST-WA-TACOMA-COUNCIL")
                if got_district != expected_district:
                    raise AssertionError(f"{control_id}: expected Tacoma district {expected_district}, got {got_district}")
            if model["canonical_writes"] != 0:
                raise AssertionError(f"{control_id}: canonical writes must remain zero")
            summaries.append({
                "control": control_id,
                "status": "PASS",
                "district": expected_district,
                "offices": got_offices,
                "contests": got_contests,
                "candidates": got_candidates,
                "matched_address": model.get("matched_address"),
            })
        print(json.dumps({"status": "PASS", "gate": "EV-IMP-003-LIVE", "controls": summaries, "canonical_writes": 0}, sort_keys=True))
        return 0
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
