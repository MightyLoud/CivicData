#!/usr/bin/env python3
"""Offline validation of pinned Colorado local-election geometry artifacts."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from tools.fetch_district_geometry import district_for_point

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_DIR = ROOT / "data" / "geometry" / "co"

FILES = {
    "alamosa": GEOMETRY_DIR / "alamosa_wards.geojson",
    "arvada": GEOMETRY_DIR / "arvada_council_districts.geojson",
}
PACKAGE_FILES = {
    "alamosa": ROOT / "data" / "normalized" / "co" / "jurisdiction-co-alamosa" / "jurisdiction.json",
    "arvada": ROOT / "data" / "normalized" / "co" / "jurisdiction-co-arvada" / "jurisdiction.json",
}
MACHINE_SOURCE_IDS = {
    "alamosa": "src-co-alamosa-ward-feature-service",
    "arvada": "src-co-arvada-council-district-feature-service",
}


class OfflineGeometryError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(root: Path = ROOT) -> dict[str, Any]:
    geometry_dir = root / "data" / "geometry" / "co"
    manifest = load_json(geometry_dir / "district_geometry_manifest.json")
    points = load_json(geometry_dir / "district_control_points.json")
    recorded = load_json(geometry_dir / "district_geometry_verification.json")

    collections: dict[str, dict[str, Any]] = {}
    hash_results: dict[str, Any] = {}
    for city, filename in {
        "alamosa": "alamosa_wards.geojson",
        "arvada": "arvada_council_districts.geojson",
    }.items():
        path = geometry_dir / filename
        collection = load_json(path)
        collections[city] = collection
        actual_hash = sha256(canonical_bytes(collection)).hexdigest()
        expected_hash = manifest["sources"][city]["geojson_sha256"]
        districts = sorted(
            str(row["properties"]["district"])
            for row in collection.get("features", [])
        )
        expected_districts = sorted(manifest["sources"][city]["expected_districts"])
        hash_results[city] = {
            "actual_sha256": actual_hash,
            "expected_sha256": expected_hash,
            "hash_ok": actual_hash == expected_hash,
            "districts": districts,
            "district_set_ok": districts == expected_districts,
            "feature_count": len(collection.get("features", [])),
        }

    point_results = []
    for point in points:
        city = point["city"]
        actual = district_for_point(
            collections[city],
            float(point["longitude"]),
            float(point["latitude"]),
        )
        recorded_row = next(
            row
            for row in recorded["results"]
            if row["test_id"] == point["test_id"]
        )
        point_results.append(
            {
                "city": city,
                "test_id": point["test_id"],
                "actual_district": actual,
                "expected_district": recorded_row["expected_district"],
                "recorded_actual_district": recorded_row["actual_district"],
                "result": (
                    actual == recorded_row["expected_district"]
                    and actual == recorded_row["actual_district"]
                    and recorded_row["result"] is True
                ),
            }
        )

    package_results = {}
    for city, rel in {
        "alamosa": "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
        "arvada": "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
    }.items():
        package = load_json(root / rel)
        source_id = MACHINE_SOURCE_IDS[city]
        source = next(
            (
                row
                for row in package.get("provenance", {}).get("source_evidence", [])
                if row.get("source_id") == source_id
            ),
            None,
        )
        test_ids = {
            row["test_id"]
            for row in package.get("qa", {}).get("address_tests", [])
            if row.get("boundary_source_id") == source_id
        }
        expected_test_ids = {
            row["test_id"]
            for row in recorded["results"]
            if row["city"] == city
        }
        package_results[city] = {
            "machine_source_present": source is not None,
            "machine_source_url": source.get("url") if source else None,
            "machine_source_url_ok": (
                source is not None
                and source.get("url") == manifest["sources"][city]["layer_url"]
            ),
            "controls_bound_to_machine_source": test_ids == expected_test_ids,
            "warnings_closed": not any(
                row.get("gap_type") == "MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED"
                for row in package.get("warnings", [])
            ),
            "warning_count_synced": (
                package.get("qa", {}).get("source_counts", {}).get("warnings")
                == len(package.get("warnings", []))
            ),
        }

    passed = (
        recorded.get("count") == 8
        and recorded.get("passed") is True
        and len(point_results) == 8
        and all(row["result"] for row in point_results)
        and all(
            row["hash_ok"]
            and row["district_set_ok"]
            and row["feature_count"] == 4
            for row in hash_results.values()
        )
        and all(
            row["machine_source_present"]
            and row["machine_source_url_ok"]
            and row["controls_bound_to_machine_source"]
            and row["warnings_closed"]
            and row["warning_count_synced"]
            for row in package_results.values()
        )
    )

    return {
        "version": "0.1",
        "passed": passed,
        "geometry": hash_results,
        "points": point_results,
        "packages": package_results,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit("offline district geometry validation failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
