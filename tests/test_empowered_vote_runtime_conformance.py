from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.runtime_conformance import (
    RESOLUTION_SOURCE,
    evaluate_address_control,
    evaluate_governed_address_runtime,
)
from tools.export_representation import build_report, discover_packages

STAMP = "2026-09-26T16:45:00Z"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def contract(package):
    return export_factory_package(
        package,
        generated_at=STAMP,
        governed_package=True,
    )


class EmpoweredVoteGovernedAddressRuntimeTests(unittest.TestCase):
    def test_all_eighteen_current_governed_address_controls_pass_runtime_join(self):
        total = 0
        by_jurisdiction = {}
        for path in discover_packages(ROOT):
            package = load(path)
            result = evaluate_governed_address_runtime(package, contract(package))
            by_jurisdiction[package["jurisdiction"]["name"]] = result
            total += result["controls_total"]
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["controls_blocked"], 0, result)
            self.assertEqual(result["controls_lossy"], 0, result)
            self.assertEqual(
                result["controls_passed"],
                result["controls_total"],
                result,
            )
            for control in result["controls"]:
                self.assertEqual(control["resolution_source"], RESOLUTION_SOURCE)
                self.assertEqual(
                    control["actual_office_ids"],
                    control["expected_office_ids"],
                )
                self.assertEqual(
                    control["resolved_division_ocdid"],
                    control["expected_division_ocdid"],
                )
                self.assertEqual(control["canonical_writes"], 0)

        self.assertEqual(total, 18)
        self.assertEqual(by_jurisdiction["Akron"]["controls_total"], 2)
        self.assertEqual(by_jurisdiction["Alamosa"]["controls_total"], 6)
        self.assertEqual(by_jurisdiction["Alma"]["controls_total"], 2)
        self.assertEqual(by_jurisdiction["Arvada"]["controls_total"], 6)
        self.assertEqual(by_jurisdiction["Aspen"]["controls_total"], 2)

    def test_all_current_local_electoral_divisions_have_governed_address_coverage(self):
        results = {}
        for path in discover_packages(ROOT):
            package = load(path)
            results[package["jurisdiction"]["name"]] = (
                evaluate_governed_address_runtime(package, contract(package))
            )

        for name, result in results.items():
            with self.subTest(jurisdiction=name):
                self.assertEqual(result["geography_gaps"], [])

        alamosa_ids = {
            row["expected_division_id"]
            for row in results["Alamosa"]["controls"]
        }
        self.assertTrue(
            {
                "division-co-alamosa-ward-1",
                "division-co-alamosa-ward-2",
                "division-co-alamosa-ward-3",
                "division-co-alamosa-ward-4",
            }.issubset(alamosa_ids)
        )

        arvada_ids = {
            row["expected_division_id"]
            for row in results["Arvada"]["controls"]
        }
        self.assertTrue(
            {
                "division-co-arvada-district-1",
                "division-co-arvada-district-2",
                "division-co-arvada-district-3",
                "division-co-arvada-district-4",
            }.issubset(arvada_ids)
        )

    def test_every_address_control_references_committed_boundary_evidence(self):
        for path in discover_packages(ROOT):
            package = load(path)
            source_ids = {
                row["source_id"]
                for row in package.get("provenance", {}).get("source_evidence", [])
            }
            for control in package.get("qa", {}).get("address_tests", []):
                with self.subTest(
                    jurisdiction=package["jurisdiction"]["name"],
                    test_id=control.get("test_id"),
                ):
                    self.assertIn(control.get("boundary_source_id"), source_ids)

    def test_alamosa_and_arvada_geometry_warnings_are_resolved_and_retained_for_audit(self):
        expected = {
            "Alamosa": "gap-co-alamosa-machine-readable-ward-geometry",
            "Arvada": "gap-co-arvada-machine-readable-district-geometry",
        }
        for path in discover_packages(ROOT):
            package = load(path)
            name = package["jurisdiction"]["name"]
            if name not in expected:
                continue
            warnings = package.get("warnings", [])
            self.assertEqual(len(warnings), 1)
            warning = warnings[0]
            self.assertEqual(warning["gap_id"], expected[name])
            self.assertEqual(
                warning["gap_type"],
                "MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED",
            )
            self.assertFalse(warning["blocking"])
            self.assertEqual(warning["status"], "RESOLVED")
            self.assertEqual(warning["resolved_at"], "2026-09-26")
            self.assertIn("governed snapshot archived", warning["resolution"])

    def test_new_district_controls_select_citywide_plus_one_local_office(self):
        expectations = {
            "Alamosa": {
                "addrtest-co-alamosa-ward-1-cattails": "office-co-alamosa-council-ward-1",
                "addrtest-co-alamosa-ward-2-carroll-park": "office-co-alamosa-council-ward-2",
                "addrtest-co-alamosa-ward-3-jardin-hermosa": "office-co-alamosa-council-ward-3",
                "addrtest-co-alamosa-ward-4-lee-fields": "office-co-alamosa-council-ward-4",
            },
            "Arvada": {
                "addrtest-co-arvada-district-1-lake-arbor-golf": "office-co-arvada-council-district-1",
                "addrtest-co-arvada-district-2-little-dry-creek": "office-co-arvada-council-district-2",
                "addrtest-co-arvada-district-3-little-raven": "office-co-arvada-council-district-3",
                "addrtest-co-arvada-district-4-west-woods": "office-co-arvada-council-district-4",
            },
        }
        for path in discover_packages(ROOT):
            package = load(path)
            name = package["jurisdiction"]["name"]
            if name not in expectations:
                continue
            result = evaluate_governed_address_runtime(package, contract(package))
            controls = {row["test_id"]: row for row in result["controls"]}
            for test_id, local_office in expectations[name].items():
                with self.subTest(jurisdiction=name, test_id=test_id):
                    row = controls[test_id]
                    self.assertEqual(row["status"], "PASS", row)
                    self.assertIn(local_office, row["actual_office_ids"])
                    self.assertEqual(
                        len(
                            [
                                office_id
                                for office_id in row["actual_office_ids"]
                                if (
                                    "ward-" in office_id
                                    or "district-" in office_id
                                )
                            ]
                        ),
                        1,
                        row,
                    )

    def test_synthetic_district_control_selects_citywide_plus_district_offices(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json"
        package = load(path)
        control = {
            "test_id": "synthetic-alamosa-ward-1-runtime",
            "address_input": "SYNTHETIC GOVERNED WARD 1 CONTROL",
            "normalized_address": "SYNTHETIC GOVERNED WARD 1 CONTROL",
            "expected_division_id": "division-co-alamosa-ward-1",
            "expected_office_ids": (
                "office-co-alamosa-mayor;"
                "office-co-alamosa-council-at-large;"
                "office-co-alamosa-council-ward-1"
            ),
            "result": True,
        }
        result = evaluate_address_control(package, contract(package), control)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(
            result["actual_office_ids"],
            sorted([
                "office-co-alamosa-mayor",
                "office-co-alamosa-council-at-large",
                "office-co-alamosa-council-ward-1",
            ]),
        )
        self.assertEqual(
            result["resolved_division_ocdid"],
            "ocd-division/country:us/state:co/place:alamosa/ward:1",
        )

    def test_missing_expected_division_fails_closed(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
        package = load(path)
        control = deepcopy(package["qa"]["address_tests"][0])
        control["expected_division_id"] = "division-co-akron-not-real"
        result = evaluate_address_control(package, contract(package), control)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error"], "EXPECTED_DIVISION_CROSSWALK_MISSING")

    def test_missing_expected_office_fails_closed(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
        package = load(path)
        control = deepcopy(package["qa"]["address_tests"][0])
        control["expected_office_ids"] += ";office-co-akron-not-real"
        result = evaluate_address_control(package, contract(package), control)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error"], "EXPECTED_OFFICE_NOT_IN_CONTRACT")

    def test_nonpassing_factory_address_control_is_not_promoted_to_runtime_pass(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
        package = load(path)
        control = deepcopy(package["qa"]["address_tests"][0])
        control["result"] = False
        result = evaluate_address_control(package, contract(package), control)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error"], "FACTORY_ADDRESS_CONTROL_NOT_PASSING")

    def test_generic_conformance_engine_now_runs_ev_address_runtime(self):
        report, _ = build_report(
            discover_packages(ROOT),
            root=ROOT,
            generated_at=STAMP,
            certified_only=True,
        )
        self.assertEqual(report["selection"]["selected_count"], 5)
        for row in report["results"]:
            consumer = row["consumers"]["empowered_vote"]
            with self.subTest(jurisdiction=row["jurisdiction_name"]):
                self.assertEqual(consumer["status"], "PASS", consumer)
                self.assertEqual(
                    consumer["mode"],
                    "GOVERNED_ADDRESS_FIXTURE_RUNTIME",
                )
                self.assertNotIn(
                    "address_resolution_without_binding_fixture",
                    consumer["untested_capabilities"],
                )
                self.assertIn(
                    "live_civic_gps_network",
                    consumer["untested_capabilities"],
                )

    def test_runtime_results_are_deterministic(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json"
        package = load(path)
        c = contract(package)
        self.assertEqual(
            evaluate_governed_address_runtime(package, c),
            evaluate_governed_address_runtime(package, c),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
