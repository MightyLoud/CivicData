#!/usr/bin/env python3
"""One-shot deterministic packager for Civic GPS v0.6.1 + Williamson County."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "civic_gps"
ZIP_PATH = ROOT / "civic_gps_runtime.zip"
PARTS = ROOT / "civic_gps_runtime_parts"
BUILDER_PATH = ROOT / "tools" / "civic_gps_tx_county_archetype.py"
OUT = ROOT / "artifacts" / "civic-gps-williamson-package"
OUT.mkdir(parents=True, exist_ok=True)
OLD_SHA = "a47205629202d0ee09304b07155262018963f9b815433e1ba9cf7e0e4abe8a4a"
GIS_SERVICE = "https://gis.wilco.org/arcgis/rest/services/public/county_administrative_boundaries/MapServer/0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_builder():
    spec = importlib.util.spec_from_file_location("civic_gps_tx_county_archetype", BUILDER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def williamson_spec():
    countywide = [
        {"office_id": "office-us-tx-williamson-county-judge", "title": "County Judge", "holder": "Steven Snell", "selection_type": "appointment", "official_url": "https://www.wilcotx.gov/334/County-Judge"},
        {"office_id": "office-us-tx-williamson-county-sheriff", "title": "Sheriff", "holder": "Matthew Lindemann", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
        {"office_id": "office-us-tx-williamson-county-clerk", "title": "County Clerk", "holder": "Nancy E. Rister", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
        {"office_id": "office-us-tx-williamson-county-district-clerk", "title": "District Clerk", "holder": "Lisa David", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
        {"office_id": "office-us-tx-williamson-county-tax-assessor-collector", "title": "Tax Assessor-Collector", "holder": "Catherine Totty", "selection_type": "appointment", "official_url": "https://www.wilcotx.gov/tax"},
        {"office_id": "office-us-tx-williamson-county-treasurer", "title": "County Treasurer", "holder": "D. Scott Heselmeyer", "official_url": "https://www.wilcotx.gov/188/Elected-Officials"},
    ]
    families = [
        {
            "adapter_id": "DIST-TX-WILLIAMSON-COMMISSIONER",
            "layer": "williamson_county_commissioner_precinct",
            "service_url": GIS_SERVICE,
            "district_field": "PCT_NUMBER",
            "district_name_template": "Williamson County Commissioner Precinct {district}",
            "division_id_template": "div-us-tx-williamson-county-commissioner-{district}",
            "division_type": "county_commissioner_precinct",
            "office_id_template": "office-us-tx-williamson-county-commissioner-{district}",
            "office_title_template": "Commissioner Precinct {district}",
            "official_url": "https://www.wilcotx.gov/188/Elected-Officials",
            "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
            "endpoint_provenance_url": GIS_SERVICE,
            "endpoint_publisher": "Williamson County GIS",
            "coverage_reason": "Address-specific Commissioner precinct resolved from official Williamson County precinct geometry.",
            "holders": {"1": "Terry Cook", "2": "Cynthia Long", "3": "Valerie Covey", "4": "Russ Boles"},
        },
        {
            "adapter_id": "DIST-TX-WILLIAMSON-JP",
            "layer": "williamson_county_jp_precinct",
            "service_url": GIS_SERVICE,
            "district_field": "PCT_NUMBER",
            "district_name_template": "Williamson County Justice Precinct {district}",
            "division_id_template": "div-us-tx-williamson-county-jp-{district}",
            "division_type": "justice_precinct",
            "office_id_template": "office-us-tx-williamson-county-jp-{district}",
            "office_title_template": "Justice of the Peace Precinct {district}",
            "official_url": "https://www.wilcotx.gov/188/Elected-Officials",
            "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
            "endpoint_provenance_url": GIS_SERVICE,
            "endpoint_publisher": "Williamson County GIS",
            "coverage_reason": "Address-specific Justice precinct resolved from official Williamson County precinct geometry.",
            "holders": {"1": "KT Musselman", "2": "Angela Williams", "3": "Evelyn McLean", "4": "Rhonda Redden"},
        },
        {
            "adapter_id": "DIST-TX-WILLIAMSON-CONSTABLE",
            "layer": "williamson_county_constable_precinct",
            "service_url": GIS_SERVICE,
            "district_field": "PCT_NUMBER",
            "district_name_template": "Williamson County Constable Precinct {district}",
            "division_id_template": "div-us-tx-williamson-county-constable-{district}",
            "division_type": "constable_precinct",
            "office_id_template": "office-us-tx-williamson-county-constable-{district}",
            "office_title_template": "Constable Precinct {district}",
            "official_url": "https://www.wilcotx.gov/188/Elected-Officials",
            "endpoint_authority_class": "OFFICIAL_COUNTY_GIS",
            "endpoint_provenance_url": GIS_SERVICE,
            "endpoint_publisher": "Williamson County GIS",
            "coverage_reason": "Address-specific Constable precinct resolved from the shared official Williamson County precinct geography; identity is canonical-release-only.",
            "holders": {"1": "Mickey Chance", "2": "Jeff Anderson", "3": "Kevin Wilkie", "4": "Paul Leal"},
        },
    ]
    return {
        "county_name": "Williamson County",
        "county_geoid": "48491",
        "jurisdiction_id": "jur-us-tx-williamson-county",
        "division_id": "div-us-tx-williamson-county",
        "adapter_id": "ADAPTER-TX-WILLIAMSON",
        "response_id_prefix": "civic-gps-williamson",
        "release_filename": "civic_gps_williamson_county_v0.1.json",
        "snapshot_ref": "https://www.wilcotx.gov/188/Elected-Officials",
        "source_repository": "https://www.wilcotx.gov/",
        "source_manifest": {
            "elected_officials": "https://www.wilcotx.gov/188/Elected-Officials",
            "county_judge": "https://www.wilcotx.gov/334/County-Judge",
            "tax_assessor_collector": "https://www.wilcotx.gov/tax",
            "geometry": GIS_SERVICE,
            "controls": "official Williamson County facility and precinct-office addresses",
        },
        "observed_on": "2026-08-08",
        "release_status": "RELEASE_BACKED_CURRENT",
        "source_status": "LIVE_INTERIOR_NEGATIVE_BOUNDARY_PASS",
        "release_note": "Williamson County is the third production county generated through the reusable Texas county precinct archetype. It models a deliberately bounded six-office countywide set plus Commissioner, Justice of the Peace, and Constable precinct offices 1-4. Geography comes only from official Williamson County administrative-boundary GIS. Current officeholder identity comes only from canonical official-page evidence; the Tax Assessor-Collector uses newer office-specific appointment evidence over a stale general directory entry. Civic-action routing and additional countywide offices remain explicitly outside this v0.1 release scope.",
        "countywide_offices": countywide,
        "district_families": families,
        "known_gaps": [
            {"gap_id": "GAP-WILLIAMSON-GPS-001", "status": "NOT_YET_RELEASED", "summary": "Williamson County civic-action routing is intentionally not included in this geography/office release."},
            {"gap_id": "GAP-WILLIAMSON-GPS-002", "status": "BOUNDED_V0_1_SCOPE", "summary": "The v0.1 countywide set is intentionally bounded to six core countywide offices; additional countywide offices are not yet modeled."},
            {"gap_id": "GAP-WILLIAMSON-GPS-003", "status": "SOURCE_PRECEDENCE_RESOLVED", "summary": "Newer office-specific evidence establishes Catherine Totty as current Tax Assessor-Collector; a stale general directory entry for Larry Gaddes is not canonical."},
        ],
    }


def patch_registry_and_release():
    builder = load_builder()
    release, bundle = builder.build_texas_county_precinct_artifacts(williamson_spec())
    bundle["coverage_rules"].insert(-1, {
        "layer": "williamson_action_endpoints",
        "reason": "Williamson County civic-action routing is intentionally not yet released in the county-archetype geography/office batch.",
        "status": "NOT_YET_RELEASED",
        "when": {"jurisdiction_active": "jur-us-tx-williamson-county"},
    })
    (GPS / "civic_gps_williamson_county_v0.1.json").write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    path = GPS / "registry.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    if reg.get("engine_version") != "0.6.1" or reg.get("registry_artifact_version") != "0.5.3":
        raise SystemExit(f"unexpected base registry: {reg.get('engine_version')} / {reg.get('registry_artifact_version')}")
    reg["registry_artifact_version"] = "0.5.4"
    reg["bundles"] = [b for b in reg["bundles"] if b.get("adapter_id") != "ADAPTER-TX-WILLIAMSON"]
    reg["bundles"].append(bundle)
    reg["bundles"].sort(key=lambda b: b["adapter_id"])
    path.write_text(json.dumps(reg, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def patch_readme():
    path = GPS / "README.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("registry artifact v0.5.3", "registry artifact v0.5.4")
    text = text.replace("The packaged registry now includes seven jurisdiction bundles:", "The packaged registry now includes eight jurisdiction bundles:")
    text = text.replace(
        "4. Collin County\n5. Denton County\n6. Travis County\n7. Tacoma / Pierce County",
        "4. Collin County\n5. Denton County\n6. Travis County\n7. Williamson County\n8. Tacoma / Pierce County",
    )
    text += "\nWilliamson County is the third production county emitted by the reusable `TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1` build archetype. Four permanent interiors cover precinct keys 1-4; the Austin negative proves county isolation; and a live-derived P1/P4 exact boundary suppresses all three shared district families while preserving the six countywide offices. Williamson action routing and additional countywide offices remain explicitly outside the bounded v0.1 release scope.\n"
    path.write_text(text, encoding="utf-8")


def build_zip():
    with ZipFile(ZIP_PATH, "w") as zf:
        for path in sorted(GPS.iterdir(), key=lambda p: p.name):
            if path.is_file() and not path.name.startswith("."):
                info = ZipInfo(f"civic_gps/{path.name}", date_time=(2026, 8, 8, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                zf.writestr(info, path.read_bytes())


def main():
    current = b"".join(p.read_bytes() for p in sorted(PARTS.glob("part.*")))
    ZIP_PATH.write_bytes(current)
    old_actual = sha256(ZIP_PATH)
    if old_actual != OLD_SHA:
        raise SystemExit(f"old runtime SHA mismatch: {old_actual}")
    if GPS.exists():
        shutil.rmtree(GPS)
    with ZipFile(ZIP_PATH) as zf:
        zf.extractall(ROOT)
    patch_registry_and_release()
    patch_readme()
    build_zip()
    first = sha256(ZIP_PATH)
    build_zip()
    second = sha256(ZIP_PATH)
    if first != second:
        raise SystemExit(f"deterministic build mismatch: {first} != {second}")
    with ZipFile(ZIP_PATH) as zf:
        reg = json.loads(zf.read("civic_gps/registry.json"))
        rel = json.loads(zf.read("civic_gps/civic_gps_williamson_county_v0.1.json"))
    if reg.get("engine_version") != "0.6.1" or reg.get("registry_artifact_version") != "0.5.4":
        raise SystemExit("new registry metadata mismatch")
    bundle = next((b for b in reg.get("bundles", []) if b.get("adapter_id") == "ADAPTER-TX-WILLIAMSON"), None)
    if not bundle or bundle.get("release_files") != ["civic_gps_williamson_county_v0.1.json"]:
        raise SystemExit("Williamson bundle/release linkage mismatch")
    if bundle.get("action_registry_files"):
        raise SystemExit("Williamson actions must remain unreleased")
    if len(rel.get("payload", {}).get("offices", [])) != 18 or len(rel.get("payload", {}).get("officeholders", [])) != 18:
        raise SystemExit("Williamson release must contain exactly 18 offices/officeholders")
    if any(a.get("failure_scope") != "ADAPTER" for a in bundle.get("district_adapters", [])):
        raise SystemExit("Williamson district adapters must fail at ADAPTER scope")
    for p in PARTS.glob("part.*"):
        p.unlink()
    data = ZIP_PATH.read_bytes()
    for i in range(0, len(data), 8000):
        (PARTS / f"part.{i//8000:02d}").write_bytes(data[i:i+8000])
    reconstructed = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(PARTS.glob("part.*")))).hexdigest()
    if reconstructed != first:
        raise SystemExit("chunk reconstruction SHA mismatch")
    summary = {
        "status": "PASS",
        "runtime_sha256": first,
        "engine_version": "0.6.1",
        "registry_artifact_version": "0.5.4",
        "williamson_offices": 18,
        "williamson_actions": "NOT_YET_RELEASED",
        "parts": [{"name": p.name, "size": p.stat().st_size} for p in sorted(PARTS.glob("part.*"))],
    }
    (OUT / "package-summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    print(f"WILLIAMSON_RUNTIME_SHA={first}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
