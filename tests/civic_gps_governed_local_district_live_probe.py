#!/usr/bin/env python3
"""Live governed local-district Civic GPS → Contract v1 proof for #104."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.factory.export_representation import export_factory_package
from civic_gps_extensions.loader import load_resolver_with_extensions
from consumers.empowered_vote.contract_v1 import (
    build_representation_from_civic_gps_result,
)

CASES = (
    {
        "package": ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
        "jurisdiction_id": "jur-us-co-alamosa",
        "adapter_id": "DIST-CO-ALAMOSA-WARD",
        "key_from_native": lambda native: native.rsplit("-", 1)[-1],
    },
    {
        "package": ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
        "jurisdiction_id": "jur-us-co-arvada",
        "adapter_id": "DIST-CO-ARVADA-COUNCIL",
        "key_from_native": lambda native: native.rsplit("-", 1)[-1],
    },
)
GENERATED_AT = "2026-10-11T19:30:00Z"

# The governed source keeps the City's official facility spelling. The
# reconstructed Civic GPS core geocoder uses the Census address matcher, which
# does not match the spelled-out ordinal for this one control. This alias is
# routing-only; district truth still comes exclusively from governed PIP.
CIVIC_GPS_GEOCODER_ALIASES = {
    "addrtest-co-alamosa-ward-4-lee-fields":
        "1000 20th St, Alamosa, CO 81101",
}


def main() -> int:
    resolver = load_resolver_with_extensions(ROOT, timeout_seconds=30.0)
    rows = []

    for case in CASES:
        package = json.loads(case["package"].read_text(encoding="utf-8"))
        contract = export_factory_package(
            package,
            generated_at=GENERATED_AT,
            governed_package=True,
        )
        native_to_ocdid = {
            row["division_id"]: row["ocd_division_id"]
            for row in package["records"]["divisions"]
            if row.get("division_id") and row.get("ocd_division_id")
        }

        for control in package["qa"]["address_tests"]:
            if control.get("coordinate_role") != "DERIVED_TEST_POINT_ONLY":
                continue

            routing_address = control["address_input"]
            gps = resolver.resolve(routing_address, observed_on=None)
            if "error" in gps:
                raise AssertionError(
                    f"{control['test_id']}: Civic GPS error: {gps['error']}"
                )
            payload = gps["payload"]
            jurisdictions = {
                row["jurisdiction_id"]
                for row in payload["jurisdictions"]
                if row.get("jurisdiction_id")
            }
            if case["jurisdiction_id"] not in jurisdictions:
                raise AssertionError(
                    f"{control['test_id']}: missing {case['jurisdiction_id']} "
                    f"from {sorted(jurisdictions)}"
                )

            assignments = {
                row["adapter_id"]: str(row["district_key"])
                for row in payload["district_assignments"]
            }
            expected_key = case["key_from_native"](
                control["expected_division_id"]
            )
            actual_key = assignments.get(case["adapter_id"])
            if actual_key != expected_key:
                raise AssertionError(
                    f"{control['test_id']}: expected district {expected_key}, "
                    f"got {actual_key!r}"
                )

            expected_ocdid = native_to_ocdid[control["expected_division_id"]]
            model = build_representation_from_civic_gps_result(
                contract,
                control["address_input"],
                gps,
                binding={
                    "contract_jurisdiction_ocdid": package["jurisdiction"][
                        "ocd_jurisdiction_id"
                    ],
                    "civic_gps_jurisdiction_id": case["jurisdiction_id"],
                    "district_adapter_id": case["adapter_id"],
                    "district_division_map": {
                        expected_key: expected_ocdid,
                    },
                },
            )
            if model.get("status") != "PASS":
                raise AssertionError(
                    f"{control['test_id']}: Contract v1 failed: {model}"
                )

            actual_offices = sorted(
                row["office_id"]
                for row in model["applicable_offices"]
            )
            expected_offices = sorted(
                part.strip()
                for part in control["expected_office_ids"].split(";")
                if part.strip()
            )
            if actual_offices != expected_offices:
                raise AssertionError(
                    f"{control['test_id']}: expected offices "
                    f"{expected_offices}, got {actual_offices}"
                )

            # The local Civic GPS additions are routing-only. No municipal civic
            # facts are sourced from the release/bundle itself.
            release_name = (
                "alamosa_release_v0.1.json"
                if case["jurisdiction_id"] == "jur-us-co-alamosa"
                else "arvada_release_v0.1.json"
            )
            release = json.loads(
                (ROOT / "civic_gps_extensions" / release_name).read_text(
                    encoding="utf-8"
                )
            )["payload"]
            if release.get("offices") or release.get("officeholders"):
                raise AssertionError(
                    f"{control['test_id']}: routing release contains civic facts"
                )

            if model["canonical_writes"] != 0:
                raise AssertionError(
                    f"{control['test_id']}: canonical writes must be zero"
                )

            rows.append(
                {
                    "test_id": control["test_id"],
                    "address": control["address_input"],
                    "routing_address": routing_address,
                    "used_geocoder_alias": (
                        routing_address != control["address_input"]
                    ),
                    "jurisdiction": case["jurisdiction_id"],
                    "adapter_id": case["adapter_id"],
                    "district_key": actual_key,
                    "division_ocdid": model["resolved_division_ocdid"],
                    "office_count": len(actual_offices),
                    "status": "PASS",
                }
            )

    if len(rows) != 8:
        raise AssertionError(f"expected 8 live district controls, got {len(rows)}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CIVIC-GPS-GOVERNED-LOCAL-DISTRICT-001",
                "controls": rows,
                "routing_release_civic_fact_rows": 0,
                "canonical_writes": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
