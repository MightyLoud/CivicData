#!/usr/bin/env python3
"""Source-delta, residency semantics, and production-isolation regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_preview as preview, package_catalog
from tools import ev_maui_source_correction as correction, ev_maui_countywide_preview as runner


def geography(county=preview.CIVIC_ID, address="synthetic fixture", district=None):
    return {"payload": {"input": {"matched_address": address},
        "jurisdictions": [{"jurisdiction_id": county}],
        "district_assignments": [] if district is None else [
            {"adapter_id": "fixture-residency-area", "district_key": district}]}}


class FixtureResolver:
    def __init__(self, binding):
        self.binding, self.calls = binding, []

    def resolve(self, address, observed_on=None):
        self.calls.append(address)
        county = (self.binding["negative_address"]["expected_civic_jurisdiction_id"]
                  if address == self.binding["negative_address"]["address"] else preview.CIVIC_ID)
        return geography(county, address)


class MauiPreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binding = json.loads((ROOT / runner.CONFIG).read_text())
        cls.correction = json.loads((ROOT / correction.CORRECTION).read_text())
        cls.base = package_catalog.reconstruct_package(correction.entry(correction.BASE_ARTIFACT), ROOT)
        cls.package, cls.source_report = correction.verify_candidate(ROOT, cls.binding)

    def build(self, package=None, binding=None, geographic=None):
        return preview.preview_maui_representation(
            self.package if package is None else package, "synthetic fixture",
            geography() if geographic is None else geographic,
            binding=self.binding if binding is None else binding)

    def assertClosed(self, result, code=None):
        self.assertEqual(result["status"], "FAIL-CLOSED", result)
        self.assertNotIn("applicable_offices", result)
        self.assertTrue(result["preview_only"])
        self.assertFalse(result["publication_eligible"])
        self.assertFalse(result["complete_jurisdiction"])
        self.assertEqual(result["canonical_writes"], 0)
        if code:
            self.assertEqual(result["error"], code)

    def test_exact_source_delta_and_full_csv_parity(self):
        old, new = copy.deepcopy(self.base), copy.deepcopy(self.package)
        original_terms = {r["role_term_id"]: r for r in old["records"]["role_terms"]}
        changed = []
        for term in new["records"]["role_terms"]:
            before = original_terms[term["role_term_id"]]
            if term != before:
                changed.append(term["role_term_id"])
                self.assertEqual({k for k in term if term[k] != before[k]},
                                 {"selection_type", "source_ids", "assertion_ids", "notes"})
                self.assertEqual(term["selection_type"], "APPOINTED")
                self.assertNotIn("start_date", term)
        self.assertEqual(changed, [correction.ROLE_ID])
        for table in old["records"]:
            if table != "role_terms":
                self.assertEqual(new["records"][table], old["records"][table])
        for table in ("source_evidence", "source_assertions"):
            self.assertEqual(new["provenance"][table][:-3], old["provenance"][table])
        for key in ("jurisdiction", "qa", "warnings", "schema_version"):
            self.assertEqual(new[key], old[key])
        self.assertEqual(self.source_report["csv_tables_checked"], 7)
        self.assertTrue(self.source_report["parity_ok"])
        self.assertEqual(self.source_report["changed_archive_members"],
                         ["SHA256SUMS.txt", "jurisdiction.json", "manifest.json", "role_terms.csv"])

    def test_raw_to_normalized_appointment_provenance_joins(self):
        raw = self.correction["raw_observations"]
        sources = self.package["provenance"]["source_evidence"][-3:]
        assertions = self.package["provenance"]["source_assertions"][-3:]
        term = next(r for r in self.package["records"]["role_terms"] if r["role_term_id"] == correction.ROLE_ID)
        for observation, source, assertion in zip(raw, sources, assertions):
            self.assertEqual(source["url"], observation["url"])
            self.assertEqual(source["authority_level"], "PRIMARY_OFFICIAL")
            self.assertIn(source["source_id"], term["source_ids"].split(";"))
            self.assertIn(assertion["assertion_id"], term["assertion_ids"].split(";"))
            self.assertEqual(assertion["source_id"], source["source_id"])
            self.assertEqual(assertion["subject_id"], term["role_term_id"])
            self.assertEqual(assertion["observed_text"], observation["observed_text"])
            self.assertEqual((assertion["normalized_status"], assertion["confidence"], assertion["object_value"]),
                             ("NORMALIZED", "HIGH", "APPOINTED"))

    def test_correction_replay_is_deterministic_and_does_not_mutate_base(self):
        before = copy.deepcopy((self.base, self.correction))
        once = correction.corrected_package(self.base, self.correction)
        self.assertEqual(once, self.package)
        self.assertEqual(correction.package_bytes(once), correction.package_bytes(once))
        self.assertEqual((self.base, self.correction), before)
        with self.assertRaisesRegex(ValueError, "PRECONDITION_FAILED"):
            correction.corrected_package(once, self.correction)

    def test_receipt_rejects_missing_duplicate_unofficial_or_wrong_target_evidence(self):
        mutations = [lambda c: c["raw_observations"].pop(),
                     lambda c: c["raw_observations"].__setitem__(1, c["raw_observations"][0]),
                     lambda c: c["raw_observations"][0].__setitem__("url", "https://example.org/claim"),
                     lambda c: c["raw_observations"][0].__setitem__("normalized_selection_type", "ELECTED"),
                     lambda c: c["target"].__setitem__("person_id", "different-person"),
                     lambda c: c.__setitem__("publication_eligible", True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                receipt = copy.deepcopy(self.correction)
                mutate(receipt)
                with self.assertRaises(ValueError):
                    correction.corrected_package(self.base, receipt)

    def test_pinned_receipt_and_archive_enforced(self):
        for section in ("source_correction", "artifact"):
            with self.subTest(section=section):
                binding = copy.deepcopy(self.binding)
                binding[section]["sha256" if section == "source_correction" else "archive_sha256"] = "0" * 64
                with self.assertRaises(ValueError):
                    correction.verify_candidate(ROOT, binding)

    def test_full_countywide_scope_preserves_offices_people_and_residency(self):
        result = self.build()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual((result["office_count"], result["current_holder_count"], result["residency_area_count"]), (10, 10, 9))
        self.assertEqual(result["residency_areas"], self.package["records"]["divisions"])
        offices = {r["office_id"]: r for r in self.package["records"]["offices"]}
        people = {r["person_id"]: r for r in self.package["records"]["people"]}
        for item in result["applicable_offices"]:
            self.assertEqual(item["office"], offices[item["office_id"]])
            self.assertEqual(item["representation_scope"], "COUNTYWIDE")
            holder = item["holders"][0]
            self.assertEqual(holder["person"], people[holder["person_id"]])
        for key in ("source_evidence", "source_assertions"):
            self.assertEqual(result[key], self.package["provenance"][key])
        self.assertEqual(result["warnings"], self.package["warnings"])

    def test_unrepaired_governed_package_is_rejected(self):
        self.assertClosed(self.build(package=self.base), "MAUI_HOLDER_SELECTION_INVALID")

    def test_district_assignment_never_filters_countywide_seats(self):
        expected = self.build()["applicable_offices"]
        for area in preview.COUNCIL:
            with self.subTest(area=area):
                result = self.build(geographic=geography(district=area))
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["applicable_offices"], expected)

    def test_output_is_deterministic_and_cannot_alias_inputs(self):
        before = copy.deepcopy((self.package, self.binding))
        first = self.build()
        self.assertEqual(first, self.build())
        first["residency_areas"].clear()
        first["applicable_offices"][0]["holders"][0]["person"]["canonical_name"] = "changed"
        self.assertEqual((self.package, self.binding), before)

    def test_binding_required_and_activation_or_district_flags_rejected(self):
        self.assertClosed(preview.preview_maui_representation(self.package, "fixture", geography()), "MAUI_PREVIEW_BINDING_REQUIRED")
        for key, value in (("mode", "PRODUCTION"), ("preview_only", False), ("publication_eligible", True),
                           ("complete_jurisdiction", True), ("geoid", "15001"),
                           ("district_adapter_id", "district"), ("package_jurisdiction_id", "other")):
            with self.subTest(key=key):
                binding = copy.deepcopy(self.binding); binding[key] = value
                self.assertClosed(self.build(binding=binding))

    def test_wrong_missing_ambiguous_counties_and_geocoder_errors_rejected(self):
        self.assertClosed(self.build(geographic=geography("jur-us-hi-hawaii-county")), "CIVIC_GPS_JURISDICTION_NOT_ACTIVE")
        ambiguous = geography(); ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-kauai-county"})
        self.assertClosed(self.build(geographic=ambiguous), "MAUI_PREVIEW_AMBIGUOUS_COUNTY")
        for result in ({}, [], {"error": {"code": "NO_MATCH"}}, {"payload": {"jurisdictions": [], "district_assignments": []}}):
            with self.subTest(result=result): self.assertClosed(self.build(geographic=result))

    def test_residency_sets_and_semantics_cannot_be_rewritten_as_electorates(self):
        for key, value in (("division_type", "COUNCIL_DISTRICT"), ("address_routing_level", "COUNCIL_DISTRICT"),
                           ("jurisdiction_id", "other")):
            package = copy.deepcopy(self.package); package["records"]["divisions"][0][key] = value
            self.assertClosed(self.build(package=package), "MAUI_RESIDENCY_SEMANTICS_INVALID")
        package = copy.deepcopy(self.package); package["records"]["divisions"].pop()
        self.assertClosed(self.build(package=package), "MAUI_RESIDENCY_SET_DRIFT")

    def test_holder_loss_duplicates_and_office_changes_rejected(self):
        for table in ("people", "offices", "role_terms"):
            package = copy.deepcopy(self.package); package["records"][table].pop()
            self.assertClosed(self.build(package=package))
        package = copy.deepcopy(self.package)
        package["records"]["role_terms"][1]["person_id"] = package["records"]["role_terms"][0]["person_id"]
        self.assertClosed(self.build(package=package))
        for key, value in (("constituency", "DISTRICT"), ("seats", 2), ("seats", True),
                           ("represented_division_id", "wrong-area"), ("selection_method", "APPOINTED")):
            package = copy.deepcopy(self.package); package["records"]["offices"][1][key] = value
            self.assertClosed(self.build(package=package), "MAUI_OFFICE_SEMANTICS_INVALID")

    def test_leadership_titles_and_joins_cannot_drift(self):
        for key, value in (("role_title", "Different Chair"), ("person_id", "person-hi-maui-richard-bissen"),
                           ("office_id", "office-hi-maui-mayor"), ("status", "FORMER")):
            package = copy.deepcopy(self.package); package["records"]["leadership_roles"][0][key] = value
            self.assertClosed(self.build(package=package), "MAUI_LEADERSHIP_JOIN_INVALID")

    def test_missing_sources_provisional_people_and_conflicting_dates_rejected(self):
        for table in ("offices", "people", "role_terms", "leadership_roles", "divisions"):
            package = copy.deepcopy(self.package); package["records"][table][0]["source_ids"] = "missing-source"
            self.assertClosed(self.build(package=package))
        package = copy.deepcopy(self.package); package["records"]["people"][0]["person_status"] = "PROVISIONAL"
        self.assertClosed(self.build(package=package), "PACKAGE_PUBLIC_IDENTITY_UNRESOLVED")
        package = copy.deepcopy(self.package); package["records"]["role_terms"][0]["term_start_date"] = "2026-99-99"
        self.assertClosed(self.build(package=package), "ROLE_TERM_DATE_INVALID")

    def test_unrelated_source_or_record_drift_is_rejected_by_digest(self):
        package = copy.deepcopy(self.package); package["warnings"][0]["message"] = "different"
        self.assertClosed(self.build(package=package), "MAUI_CORRECTED_PACKAGE_DIGEST_MISMATCH")

    def test_default_production_consumer_does_not_select_preview(self):
        result = package_catalog.build_essentials_from_catalog("fixture", geography(), repo_root=ROOT,
            catalog_path=ROOT / "consumers/empowered_vote/package_catalog.v0.1.json", profile="municipal_representation")
        self.assertEqual(result["status"], "FAIL-CLOSED")
        self.assertNotIn("applicable_offices", result)
        production = preview.representation.build_representation_from_civic_gps_result(
            self.package, "fixture", geography(), binding=self.binding)
        self.assertEqual(production["error"], "PACKAGE_REPRESENTATION_DIVISION_MISSING")

    def test_runner_preserves_holds_and_distinguishes_fixture_evidence(self):
        resolver = FixtureResolver(self.binding)
        before = runner.snapshot(ROOT)
        result = runner.run_preview(ROOT, resolver)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["validation_mode"], "SYNTHETIC_FIXTURE")
        self.assertEqual(len(resolver.calls), 3)
        self.assertEqual(result["production_hold"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["source_correction"]["corrected_role_terms"], 1)
        self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(runner.snapshot(ROOT), before)

    def test_unresolved_negative_does_not_count_as_success(self):
        class UnresolvedNegative(FixtureResolver):
            def resolve(self, address, observed_on=None):
                if address == self.binding["negative_address"]["address"]:
                    return {"error": {"code": "NO_MATCH"}}
                return super().resolve(address, observed_on)
        with self.assertRaisesRegex(ValueError, "MAUI_NEGATIVE_GEOGRAPHY_UNRESOLVED"):
            runner.run_preview(ROOT, UnresolvedNegative(self.binding))

    def test_cli_rejects_output_over_protected_files_before_network_access(self):
        protected = ROOT / "previews/ev/maui_countywide.v0.1.json"
        before = protected.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "tools/ev_maui_countywide_preview.py"),
                                 "--output", str(protected)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Output must be under", result.stderr)
        self.assertEqual(protected.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
