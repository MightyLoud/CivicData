#!/usr/bin/env python3
"""Promote a successful district-geometry extraction into governed repository data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_DIR = ROOT / "data" / "reference" / "co" / "electoral_geometry"
FIXTURE = ROOT / "acceptance" / "representation" / "electoral_geometry_v0.1.json"

PACKAGE_PATHS = {
    "alamosa": ROOT / "data" / "normalized" / "co" / "jurisdiction-co-alamosa" / "jurisdiction.json",
    "arvada": ROOT / "data" / "normalized" / "co" / "jurisdiction-co-arvada" / "jurisdiction.json",
}
SOURCE_IDS = {
    "alamosa": "src-co-alamosa-ward-feature-service-2026-09-26",
    "arvada": "src-co-arvada-council-mapserver-2026-09-26",
}
OUTPUT_NAMES = {
    "alamosa": "alamosa_wards.geojson",
    "arvada": "arvada_council_districts.geojson",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_record(city: str, report: dict[str, Any], extracted_at: str) -> dict[str, Any]:
    block = report[city]
    if city == "alamosa":
        return {
            "accessed_at": extracted_at,
            "archive_url": None,
            "authority_level": "PRIMARY_OFFICIAL",
            "batch_id": "CO-GEO-004",
            "jurisdiction_id": "jurisdiction-co-alamosa",
            "locator": "Official ArcGIS Ward Map app resolved to Web Map and Wards FeatureServer layer; governed snapshot archived in data/reference/co/electoral_geometry/alamosa_wards.geojson.",
            "notes": "Machine-readable boundary source used for deterministic Ward 1–4 point-in-polygon validation.",
            "published_at": None,
            "publisher": "City of Alamosa / ArcGIS Online",
            "source_id": SOURCE_IDS[city],
            "source_type": "GIS",
            "supports_entity_id": "jurisdiction-co-alamosa",
            "supports_entity_type": "Jurisdiction",
            "title": "Alamosa Ward Map — machine-readable ArcGIS layer",
            "url": block["layer_url"],
        }
    return {
        "accessed_at": extracted_at,
        "archive_url": None,
        "authority_level": "PRIMARY_OFFICIAL",
        "batch_id": "CO-GEO-004",
        "jurisdiction_id": "jurisdiction-co-arvada",
        "locator": "Official Arvada City Council Districts Instant App resolved to Web Map and City_Council MapServer/1 polygon layer; governed snapshot archived in data/reference/co/electoral_geometry/arvada_council_districts.geojson.",
        "notes": "Machine-readable boundary source used for deterministic Council District 1–4 point-in-polygon validation.",
        "published_at": None,
        "publisher": "City of Arvada GIS",
        "source_id": SOURCE_IDS[city],
        "source_type": "GIS",
        "supports_entity_id": "jurisdiction-co-arvada",
        "supports_entity_type": "Jurisdiction",
        "title": "Arvada City Council Districts — machine-readable ArcGIS layer",
        "url": block["layer_url"],
    }


def update_package(city: str, report: dict[str, Any], extracted_at: str) -> None:
    path = PACKAGE_PATHS[city]
    package = json.loads(path.read_text(encoding="utf-8"))
    evidence = package["provenance"]["source_evidence"]
    record = source_record(city, report, extracted_at)
    matches = [row for row in evidence if row.get("source_id") == SOURCE_IDS[city]]
    if matches:
        matches[0].update(record)
    else:
        evidence.append(record)
        evidence.sort(key=lambda row: str(row.get("source_id") or ""))

    local_prefix = (
        "addrtest-co-alamosa-ward-"
        if city == "alamosa"
        else "addrtest-co-arvada-district-"
    )
    for control in package["qa"]["address_tests"]:
        if str(control.get("test_id") or "").startswith(local_prefix):
            control["boundary_source_id"] = SOURCE_IDS[city]
            control["geometry_artifact"] = (
                "data/reference/co/electoral_geometry/" + OUTPUT_NAMES[city]
            )
            control["geometry_validation_batch"] = "CO-GEO-004"

    expected_gap = (
        "gap-co-alamosa-machine-readable-ward-geometry"
        if city == "alamosa"
        else "gap-co-arvada-machine-readable-district-geometry"
    )
    warning = next(
        (row for row in package.get("warnings", []) if row.get("gap_id") == expected_gap),
        None,
    )
    if warning is None:
        raise RuntimeError(f"Expected open machine-readable geometry warning missing: {city}")

    artifact = "data/reference/co/electoral_geometry/" + OUTPUT_NAMES[city]
    warning.update(
        {
            "batch_id": "CO-GEO-004",
            "blocking": False,
            "description": (
                "RESOLVED — official machine-readable district geometry is archived "
                f"at {artifact}; all four governed local address controls reproduce "
                "their expected division by deterministic point-in-polygon validation."
            ),
            "severity": "INFO",
            "source_id": SOURCE_IDS[city],
            "status": "RESOLVED",
            "resolved_at": extracted_at,
            "resolution_artifact": artifact,
        }
    )

    package["qa"]["source_counts"]["source_evidence"] = len(evidence)
    package["qa"]["source_counts"]["warnings"] = len(package.get("warnings", []))
    path.write_text(canonical_json(package), encoding="utf-8")


def build_fixture(report: dict[str, Any], extracted_at: str) -> dict[str, Any]:
    package_controls: dict[tuple[str, str], dict[str, Any]] = {}
    for city, path in PACKAGE_PATHS.items():
        package = json.loads(path.read_text(encoding="utf-8"))
        for row in package["qa"]["address_tests"]:
            package_controls[(city, row["address_input"])] = row

    sources = {}
    for city in ("alamosa", "arvada"):
        block = report[city]
        output_path = GEOMETRY_DIR / OUTPUT_NAMES[city]
        sources[city] = {
            "source_id": SOURCE_IDS[city],
            "app_id": block["provenance"]["app_id"],
            "webmap_id": block["provenance"]["webmap_id"],
            "webmap_title": block["provenance"]["webmap_title"],
            "layer_title": block["provenance"]["layer_title"],
            "layer_url": block["layer_url"],
            "artifact_path": str(output_path.relative_to(ROOT)),
            "sha256": sha256(output_path),
            "feature_count": report["governed_outputs"][city]["feature_count"],
            "division_ids": report["governed_outputs"][city]["division_ids"],
        }

    controls = []
    for row in report["pip_controls"]:
        package_control = package_controls.get((row["city"], row["address"]))
        if package_control is None:
            raise RuntimeError("No governed package control for extracted PIP row: " + row["address"])
        controls.append(
            {
                "test_id": package_control["test_id"],
                "city": row["city"],
                "address": row["address"],
                "longitude": row["longitude"],
                "latitude": row["latitude"],
                "geocode_match": row["geocoder"]["match_addr"],
                "geocode_score": row["geocoder"]["score"],
                "expected_division_id": row["expected_division_id"],
                "matched_division_ids": row["matched_division_ids"],
                "result": row["result"],
            }
        )

    return {
        "contract_version": "0.1",
        "batch_id": "CO-GEO-004",
        "extracted_at": extracted_at,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_head_sha": os.environ.get("GITHUB_SHA"),
        "crs": "OGC:CRS84 / EPSG:4326 longitude-latitude",
        "simplification": report["simplification"],
        "sources": sources,
        "pip_controls": controls,
        "result": all(row["result"] for row in controls),
    }


def promote(extraction_dir: Path, *, extracted_at: str | None = None) -> None:
    report = json.loads((extraction_dir / "report.json").read_text(encoding="utf-8"))
    if len(report.get("pip_controls", [])) != 8 or not all(
        row.get("result") is True for row in report["pip_controls"]
    ):
        raise RuntimeError("Extraction is not eligible for governed promotion")

    extracted_at = extracted_at or datetime.now(timezone.utc).isoformat()
    GEOMETRY_DIR.mkdir(parents=True, exist_ok=True)
    for city in ("alamosa", "arvada"):
        source = extraction_dir / OUTPUT_NAMES[city]
        if not source.is_file():
            raise RuntimeError("Missing extracted governed output: " + str(source))
        shutil.copyfile(source, GEOMETRY_DIR / OUTPUT_NAMES[city])

    for city in ("alamosa", "arvada"):
        update_package(city, report, extracted_at)

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(build_fixture(report, extracted_at), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--extraction-dir",
        type=Path,
        default=ROOT / "artifacts" / "district_geometry_extract",
    )
    parser.add_argument("--extracted-at")
    args = parser.parse_args()
    promote(args.extraction_dir, extracted_at=args.extracted_at)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
