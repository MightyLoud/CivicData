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
    def test_all_ten_current_governed_address_controls_pass_runtime_join(self):
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

        self.assertEqual(total, 10)
        self.assertEqual(by_jurisdiction["Akron"]["controls_total"], 2)
        self.assertEqual(by_jurisdiction["Alamosa"]["controls_total"], 2)
        self.assertEqual(by_jurisdiction["Alma"]["controls_total"], 2)
        self.assertEqual(by_jurisdiction["Arvada"]["controls_total"], 2)
        self.assertEqual(by_jurisdiction["Aspen"]["controls_total"], 2)

    def test_districted_cities_report_missing_district_address_coverage(self):
        results = {}
        for path in discover_packages(ROOT):
            package = load(path)
            results[package["jurisdiction"]["name"]] = (
                evaluate_governed_address_runtime(package, contract(package))
            )

        self.assertEqual(len(results["Alamosa"]["geography_gaps"]), 4)
        self.assertTrue(
            all(
                "division-co-alamosa-ward-" in gap
                for gap in results["Alamosa"]["geography_gaps"]
            )
        )
        self.assertEqual(len(results["Arvada"]["geography_gaps"]), 4)
        self.assertTrue(
            all(
                "division-co-arvada-district-" in gap
                for gap in results["Arvada"]["geography_gaps"]
            )
        )
        for name in ("Akron", "Alma", "Aspen"):
            self.assertEqual(results[name]["geography_gaps"], [])

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
