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
SRC = ROOT / "consumers" / "empowered_vote" / "live_civic_gps.py"
spec = importlib.util.spec_from_file_location("ev_live_civic_gps", SRC)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

PACKAGE_DIR = ROOT / "data" / "packages" / "wa" / "tacoma"
PARTS = [
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part01a",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part01b",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part02",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part03",
    PACKAGE_DIR / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part04",
]
EXPECTED_ZIP_SHA256 = "2c6219303eff3f49b4202f72048910ba970cd65353032b6bfda2975791701d53"


def load_package():
    encoded = "".join(p.read_text(encoding="utf-8") for p in PARTS)
    raw = base64.b64decode(encoded)
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_ZIP_SHA256
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.extractall(tmp)
        package_dir = next(Path(tmp).glob("Tacoma_Jurisdiction_Package_v0.2_2026-08-23/package"))
        pkg_spec = importlib.util.spec_from_file_location(
            "ev_package_source_test_loader",
            ROOT / "consumers" / "empowered_vote" / "package_source.py",
        )
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        assert pkg_spec.loader is not None
        pkg_spec.loader.exec_module(pkg_mod)
        return pkg_mod.load_jurisdiction_package(package_dir)


def gps_result(jurisdictions, assignments, matched="747 MARKET ST, TACOMA, WA, 98402"):
    return {
        "payload": {
            "input": {"matched_address": matched},
            "jurisdictions": [{"jurisdiction_id": x} for x in jurisdictions],
            "district_assignments": [
                {"adapter_id": adapter, "district_key": key}
                for adapter, key in assignments.items()
            ],
            # Deliberately include non-authoritative fields. EV-IMP-003 must ignore them.
            "applicable_offices": [{"office_id": "evil-office"}],
            "action_links": [{"label": "not trusted"}],
        }
    }


def run():
    package = load_package()

    market = mod.build_essentials_from_civic_gps_result(
        package,
        "747 Market Street, Tacoma, WA 98402",
        gps_result(
            ["jur-us-wa-pierce", "jur-us-wa-tacoma"],
            {"DIST-WA-PIERCE-COUNCIL": "4", "DIST-WA-TACOMA-COUNCIL": "2"},
        ),
    )
    assert market["status"] == "PASS"
    assert market["consumer_gate"] == "EV-IMP-003"
    assert market["address_resolution_source"] == "CIVIC_GPS_LIVE"
    assert len(market["applicable_offices"]) == 6
    assert len(market["recent_certified_contests"]) == 5
    assert sum(len(x["candidates"]) for x in market["recent_certified_contests"]) == 15
    assert all(x["office_id"] != "evil-office" for x in market["applicable_offices"])
    assert market["canonical_writes"] == 0

    wapato = mod.build_essentials_from_civic_gps_result(
        package,
        "6500 South Sheridan Avenue, Tacoma, WA 98408",
        gps_result(
            ["jur-us-wa-pierce", "jur-us-wa-tacoma"],
            {"DIST-WA-PIERCE-COUNCIL": "4", "DIST-WA-TACOMA-COUNCIL": "5"},
            matched="6500 S SHERIDAN AVE, TACOMA, WA, 98408",
        ),
    )
    assert wapato["status"] == "PASS"
    assert wapato["district_assignments"]["DIST-WA-TACOMA-COUNCIL"] == "5"
    assert any(x["division_id"].endswith("council_district_5") for x in wapato["applicable_offices"])

    lakewood = mod.build_essentials_from_civic_gps_result(
        package,
        "6000 Main St SW, Lakewood, WA 98499",
        gps_result(["jur-us-wa-pierce"], {"DIST-WA-PIERCE-COUNCIL": "6"}),
    )
    assert lakewood["status"] == "PASS"
    assert lakewood["jurisdiction"] is None
    assert lakewood["applicable_offices"] == []
    assert lakewood["recent_certified_contests"] == []

    missing_district = mod.build_essentials_from_civic_gps_result(
        package,
        "747 Market Street, Tacoma, WA 98402",
        gps_result(["jur-us-wa-tacoma"], {}),
    )
    assert missing_district["status"] == "FAIL-CLOSED"
    assert missing_district["error"] == "CIVIC_GPS_REQUIRED_DISTRICT_MISSING"

    unknown_district = mod.build_essentials_from_civic_gps_result(
        package,
        "747 Market Street, Tacoma, WA 98402",
        gps_result(["jur-us-wa-tacoma"], {"DIST-WA-TACOMA-COUNCIL": "99"}),
    )
    assert unknown_district["status"] == "FAIL-CLOSED"
    assert unknown_district["error"] == "CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE"

    upstream_error = mod.build_essentials_from_civic_gps_result(
        package,
        "bad",
        {"error": {"code": "ADDRESS_NOT_MATCHED", "message": "no Census match"}},
    )
    assert upstream_error["status"] == "FAIL-CLOSED"
    assert upstream_error["error"] == "ADDRESS_NOT_MATCHED"

    market2 = mod.build_essentials_from_civic_gps_result(
        package,
        "747 Market Street, Tacoma, WA 98402",
        gps_result(
            ["jur-us-wa-pierce", "jur-us-wa-tacoma"],
            {"DIST-WA-PIERCE-COUNCIL": "4", "DIST-WA-TACOMA-COUNCIL": "2"},
        ),
    )
    assert market["deterministic_sha256"] == market2["deterministic_sha256"]

    print(json.dumps({
        "status": "PASS",
        "gate": "EV-IMP-003",
        "live_geography_bridge": "PASS",
        "package_fact_authority": "PASS",
        "district_2": "PASS",
        "district_5": "PASS",
        "outside_tacoma": "PASS",
        "fail_closed": "PASS",
        "determinism": "PASS",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
