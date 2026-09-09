#!/usr/bin/env python3
"""Bounded preview regressions using the unchanged governed Kauaʻi artifact."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import countywide_preview as preview, package_catalog
from tools import ev_kauai_countywide_preview as runner


def geography(county=preview.CIVIC_ID, address="synthetic fixture"):
    return {"payload": {"input": {"matched_address": address},
                        "jurisdictions": [{"jurisdiction_id": county}],
                        "district_assignments": []}}


class FixtureResolver:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []

    def resolve(self, address, observed_on=None):
        self.calls.append(address)
        county = (self.binding["negative_address"]["expected_civic_jurisdiction_id"]
                  if address == self.binding["negative_address"]["address"] else preview.CIVIC_ID)
        return geography(county, address)


class CountywidePreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binding = json.loads((ROOT / runner.CONFIG).read_text())
        cls.package = package_catalog.reconstruct_package(cls.binding, ROOT)

    def build(self, package=None, binding=None, geographic=None):
        return preview.preview_countywide_representation(
            self.package if package is None else package, "synthetic fixture",
            geography() if geographic is None else geographic,
            binding=self.binding if binding is None else binding)

    def assertClosed(self, result, code=None):
        self.assertEqual(result["status"], "FAIL-CLOSED")
        self.assertNotIn("applicable_offices", result)
        self.assertTrue(result["preview_only"])
        self.assertFalse(result["publication_eligible"])
        self.assertFalse(result["complete_jurisdiction"])
        self.assertEqual(result["canonical_writes"], 0)
        if code:
            self.assertEqual(result["error"], code)

    def test_complete_countywide_roster_preserves_governed_records(self):
        result = self.build()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual((result["office_count"], result["current_holder_count"]), (2, 8))
        offices = {row["office_id"]: row for row in result["applicable_offices"]}
        for office in self.package["records"]["offices"]:
            row = offices[office["office_id"]]
            self.assertEqual(row["office"], office)
            self.assertEqual(len(row["holders"]), office["seats"])
            self.assertNotIn("division_id", row)
        holders = [h for row in offices.values() for h in row["holders"]]
        self.assertEqual(len({h["person_id"] for h in holders}), 8)
        people = {p["person_id"]: p for p in self.package["records"]["people"]}
        terms = {t["person_id"]: t for t in self.package["records"]["role_terms"]}
        for holder in holders:
            self.assertEqual(holder["person"], people[holder["person_id"]])
            self.assertEqual(holder["role_term"], terms[holder["person_id"]])
            self.assertEqual(holder["name"], people[holder["person_id"]]["canonical_name"])
            self.assertNotIn("seat_number", holder)
            self.assertNotIn("start_date", holder["role_term"])
        leadership = [lead for h in holders for lead in h["leadership_roles"]]
        self.assertCountEqual(leadership, self.package["records"]["leadership_roles"])
        self.assertEqual(result["source_evidence"], self.package["provenance"]["source_evidence"])
        self.assertEqual(result["source_assertions"], self.package["provenance"]["source_assertions"])
        self.assertEqual(result["warnings"], self.package["warnings"])
        self.assertTrue(result["preview_only"])
        self.assertFalse(result["publication_eligible"])
        self.assertFalse(result["complete_jurisdiction"])

    def test_deterministic_and_does_not_mutate_or_alias_inputs(self):
        original = copy.deepcopy((self.package, self.binding))
        first = self.build()
        self.assertEqual(first, self.build())
        first["warnings"].clear()
        first["applicable_offices"][0]["holders"][0]["person"]["canonical_name"] = "changed output"
        self.assertEqual((self.package, self.binding), original)

    def test_explicit_preview_binding_is_required(self):
        result = preview.preview_countywide_representation(self.package, "fixture", geography())
        self.assertClosed(result, "COUNTYWIDE_PREVIEW_BINDING_REQUIRED")
        for key, value in (("mode", "COUNTYWIDE"), ("preview_only", False),
                           ("publication_eligible", True), ("complete_jurisdiction", True)):
            with self.subTest(key=key):
                binding = copy.deepcopy(self.binding)
                binding[key] = value
                self.assertClosed(self.build(binding=binding))

    def test_other_binding_identities_and_district_adapters_rejected(self):
        for key, value in (("geoid", "15009"), ("package_jurisdiction_id", "jurisdiction-hi-maui-county"),
                           ("civic_gps_jurisdiction_id", "jur-us-hi-maui-county"),
                           ("district_adapter_id", "DISTRICT-TEST")):
            with self.subTest(key=key):
                binding = copy.deepcopy(self.binding)
                binding[key] = value
                self.assertClosed(self.build(binding=binding))

    def test_wrong_missing_and_ambiguous_counties_rejected(self):
        wrong = geography("jur-us-hi-hawaii-county")
        self.assertClosed(self.build(geographic=wrong), "CIVIC_GPS_JURISDICTION_NOT_ACTIVE")
        missing = geography()
        missing["payload"]["jurisdictions"] = []
        self.assertClosed(self.build(geographic=missing))
        ambiguous = geography()
        ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-maui-county"})
        self.assertClosed(self.build(geographic=ambiguous), "COUNTYWIDE_PREVIEW_AMBIGUOUS_COUNTY")

    def test_geocoder_errors_and_malformed_responses_rejected(self):
        for response in ([], {}, {"error": {"code": "NO_MATCH"}}, {"payload": {"jurisdictions": []}}):
            with self.subTest(response=response):
                self.assertClosed(self.build(geographic=response))

    def test_real_other_hawaii_packages_cannot_use_this_preview(self):
        for county in ("hawaii", "honolulu", "maui"):
            with self.subTest(county=county):
                package, _ = runner.proposal.discover_package(ROOT, f"jurisdiction-hi-{county}-county")
                self.assertClosed(self.build(package=package), "COUNTYWIDE_PREVIEW_PACKAGE_MISMATCH")

    def test_package_identity_and_division_semantics_cannot_drift(self):
        for key, value in (("state_abbr", "TX"), ("geoid", "15009"),
                           ("jurisdiction_type", "municipality"), ("division_id", "invented")):
            with self.subTest(key=key):
                package = copy.deepcopy(self.package)
                package["jurisdiction"][key] = value
                self.assertClosed(self.build(package=package))
        package = copy.deepcopy(self.package)
        package["records"]["divisions"] = [{"division_id": "invented", "jurisdiction_id": preview.PACKAGE_ID}]
        self.assertClosed(self.build(package=package))

    def test_office_constituency_and_capacity_cannot_drift(self):
        for key, value in (("constituency", "DISTRICT"), ("seats", 6), ("seats", True),
                           ("division_id", "invented"), ("status", "INACTIVE")):
            with self.subTest(key=key, value=value):
                package = copy.deepcopy(self.package)
                package["records"]["offices"][1][key] = value
                self.assertClosed(self.build(package=package))

    def test_roster_loss_duplicate_and_extra_holders_rejected(self):
        package = copy.deepcopy(self.package)
        package["records"]["role_terms"].pop()
        self.assertClosed(self.build(package=package))
        package = copy.deepcopy(self.package)
        package["records"]["role_terms"][2]["person_id"] = package["records"]["role_terms"][1]["person_id"]
        self.assertClosed(self.build(package=package))
        package = copy.deepcopy(self.package)
        extra = copy.deepcopy(package["records"]["role_terms"][1])
        extra["role_term_id"] = "extra-term"
        package["records"]["role_terms"].append(extra)
        self.assertClosed(self.build(package=package))

    def test_expected_person_set_cannot_drift(self):
        binding = copy.deepcopy(self.binding)
        binding["offices"][1]["expected_person_ids"][0] = "unapproved-person"
        self.assertClosed(self.build(binding=binding), "COUNTYWIDE_PREVIEW_PERSON_SET_DRIFT")

    def test_provisional_identity_is_not_promoted(self):
        package = copy.deepcopy(self.package)
        package["records"]["people"][0]["person_status"] = "PROVISIONAL"
        self.assertClosed(self.build(package=package), "PACKAGE_PUBLIC_IDENTITY_UNRESOLVED")

    def test_broken_person_join_rejected(self):
        package = copy.deepcopy(self.package)
        package["records"]["role_terms"][0]["person_id"] = "missing-person"
        self.assertClosed(self.build(package=package), "PACKAGE_IDENTITY_GRAPH_INVALID")

    def test_missing_sources_cannot_be_silently_dropped(self):
        for table in ("people", "offices", "role_terms", "leadership_roles"):
            for source in ("", "missing-source"):
                with self.subTest(table=table, source=source):
                    package = copy.deepcopy(self.package)
                    package["records"][table][0]["source_ids"] = source
                    self.assertClosed(self.build(package=package))

    def test_role_term_alias_conflicts_and_bad_dates_rejected(self):
        for key, value in (("role_term_status", "FORMER"), ("term_start_date", "2026-99-99")):
            with self.subTest(key=key):
                package = copy.deepcopy(self.package)
                package["records"]["role_terms"][0][key] = value
                self.assertClosed(self.build(package=package))

    def test_leadership_loss_and_invalid_current_joins_rejected(self):
        package = copy.deepcopy(self.package)
        package["records"]["leadership_roles"].pop()
        self.assertClosed(self.build(package=package), "COUNTYWIDE_PREVIEW_LEADERSHIP_SET_DRIFT")
        for key, value in (("person_id", "person-hi-kauai-derek-kawakami"),
                           ("status", "FORMER"), ("body_id", "different-body")):
            with self.subTest(key=key):
                package = copy.deepcopy(self.package)
                package["records"]["leadership_roles"][0][key] = value
                self.assertClosed(self.build(package=package))

    def test_production_representation_still_requires_division_binding(self):
        result = preview.representation.build_representation_from_civic_gps_result(
            self.package, "fixture", geography(), binding=self.binding)
        self.assertEqual(result["status"], "FAIL-CLOSED")
        self.assertEqual(result["error"], "PACKAGE_REPRESENTATION_DIVISION_MISSING")
        self.assertNotIn("applicable_offices", result)

    def test_pinned_archive_checksum_is_enforced(self):
        binding = copy.deepcopy(self.binding)
        binding["artifact"]["archive_sha256"] = "0" * 64
        with self.assertRaises(package_catalog.PackageCatalogError) as caught:
            package_catalog.reconstruct_package(binding, ROOT)
        self.assertEqual(caught.exception.code, "PACKAGE_ARTIFACT_SHA256_MISMATCH")

    def test_runner_preserves_four_routing_holds_and_labels_fixture_evidence(self):
        resolver = FixtureResolver(self.binding)
        before = runner.snapshot(ROOT)
        result = runner.run_preview(ROOT, resolver, live=False)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["validation_mode"], "SYNTHETIC_FIXTURE")
        self.assertEqual(len(resolver.calls), 3)
        self.assertEqual(len(result["positive_controls"]), 2)
        self.assertEqual(len(result["routing_holds"]), 4)
        self.assertEqual(sorted(row["status"] for row in result["routing_holds"]), ["READY"] + ["REVIEW_REQUIRED"] * 3)
        self.assertEqual(result["auto_promoted"], 0)
        self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(before, runner.snapshot(ROOT))

    def test_unresolved_negative_address_is_not_passing_negative_evidence(self):
        class UnresolvedNegative(FixtureResolver):
            def resolve(self, address, observed_on=None):
                if address == self.binding["negative_address"]["address"]:
                    return {"error": {"code": "NO_MATCH"}}
                return super().resolve(address, observed_on)
        with self.assertRaisesRegex(ValueError, "Negative control did not successfully resolve"):
            runner.run_preview(ROOT, UnresolvedNegative(self.binding), live=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
