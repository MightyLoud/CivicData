"""Shared current controls; expected values are assertions, never routing inputs."""
from __future__ import annotations

import json
from pathlib import Path

PACKAGE_PATHS = (
    "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
    "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
)


def load_district_controls(root: Path):
    rows = []
    for relative in PACKAGE_PATHS:
        path = root / relative
        package = json.loads(path.read_text(encoding="utf-8"))
        controls = [row for row in package["qa"]["address_tests"]
                    if row.get("coordinate_role") == "DERIVED_TEST_POINT_ONLY"]
        keys = [row["expected_division_id"].rsplit("-", 1)[-1] for row in controls]
        if len(controls) != 4 or set(keys) != {"1", "2", "3", "4"}:
            raise AssertionError(f"{relative}: expected one current control per district 1..4")
        rows.extend((path, package, row) for row in controls)
    if len({row["test_id"] for _, _, row in rows}) != 8:
        raise AssertionError("expected eight unique current district controls")
    return rows
