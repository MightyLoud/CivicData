#!/usr/bin/env python3
"""Catalog-path acceptance and adversarial controls for the inactive candidate."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import countywide_candidate as adapter, countywide_production, package_catalog, representation_catalog
from tools import ev_kauai_adapter_candidate as runner, ev_jurisdiction_onboarding as onboarding
from tools import ev_onboarding_materialize as materialize
from ev_kauai_countywide_preview_test import geography, FixtureResolver


class CountywideCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / runner.SPEC).read_text())
        cls.catalog = json.loads((ROOT / runner.CATALOG).read_text())
        cls.package = package_catalog.reconstruct_package(cls.catalog["entries"][0], ROOT)

    def build(self, *, catalog=None, geographic=None, allow=True, root=ROOT):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            path.write_text(json.dumps(self.catalog if catalog is None else catalog))
            return representation_catalog.build_representation_from_catalog(
                "synthetic fixture", geography() if geographic is None else geographic,
                repo_root=root, catalog_path=path, allow_candidate=allow)

    def closed(self, result, code=None):
        self.assertEqual(result["status"], "FAIL-CLOSED", result)
        self.assertNotIn("applicable_offices", result)
        self.assertNotIn("projections", result)
        self.assertIsNot(result.get("publication_eligible"), True)
        self.assertEqual(result["canonical_writes"], 0)
        if code:
            self.assertEqual(result["error"], code)

    def test_real_archive_full_catalog_path_and_record_parity(self):
        model = self.build()
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["package_catalog_entry_id"], adapter.ENTRY_ID)
        self.assertEqual((model["office_count"], model["current_holder_count"]), (2, 8))
        for key, value in adapter.FLAGS.items():
            self.assertIs(model[key], value)
        self.assertTrue(model["representation_only"])
        self.assertFalse(model["full_essentials_supported"])
        offices = {row["office_id"]: row for row in self.package["records"]["offices"]}
        people = {row["person_id"]: row for row in self.package["records"]["people"]}
        terms = {row["person_id"]: row for row in self.package["records"]["role_terms"]}
        leaders = []
        for row in model["applicable_offices"]:
            self.assertEqual(row["office"], offices[row["office_id"]])
            self.assertNotIn("division_id", row)
            self.assertEqual(len(row["holders"]), row["seat_capacity"])
            for holder in row["holders"]:
                self.assertEqual(holder["person"], people[holder["person_id"]])
                self.assertEqual(holder["role_term"], terms[holder["person_id"]])
                self.assertNotIn("seat_number", holder)
                self.assertNotIn("start_date", holder["role_term"])
                leaders.extend(holder["leadership_roles"])
        self.assertCountEqual(leaders, self.package["records"]["leadership_roles"])
        for field in ("source_evidence", "source_assertions"):
            self.assertEqual(model[field], self.package["provenance"][field])
        self.assertEqual(model["warnings"], self.package["warnings"])

    def test_default_catalog_and_candidate_without_opt_in_stay_closed(self):
        default = representation_catalog.build_representation_from_catalog(
            "synthetic", geography(), repo_root=ROOT)
        self.assertEqual(default["status"], "PASS")
        self.assertEqual(default["package_catalog_entry_id"], countywide_production.ENTRY_ID)
        self.assertFalse(default["publication_eligible"])
        self.closed(self.build(allow=False), "COUNTYWIDE_CANDIDATE_NOT_ENABLED")
        self.closed(self.build(allow=1), "COUNTYWIDE_CANDIDATE_NOT_ENABLED")

    def test_activation_flags_cannot_be_enabled_or_omitted(self):
        for key, value in adapter.FLAGS.items():
            for replacement in (not value, None, int(value)):
                with self.subTest(key=key, value=replacement):
                    catalog = copy.deepcopy(self.catalog)
                    catalog["entries"][0][key] = replacement
                    self.closed(self.build(catalog=catalog), "COUNTYWIDE_CANDIDATE_HOLD_REQUIRED")
            catalog = copy.deepcopy(self.catalog)
            del catalog["entries"][0][key]
            self.closed(self.build(catalog=catalog), "COUNTYWIDE_CANDIDATE_HOLD_REQUIRED")

    def test_mixed_district_or_texas_profile_bindings_rejected(self):
        for key in ("district_binding", "district_bindings", "production_profile"):
            for value in ({}, None, {"profile_id": "tx_legislative_two_office_v0.1"}):
                with self.subTest(key=key, value=value):
                    catalog = copy.deepcopy(self.catalog)
                    catalog["entries"][0][key] = value
                    self.closed(self.build(catalog=catalog), "PACKAGE_CATALOG_BINDING_FORMS_CONFLICT")

    def test_wrong_package_schema_identity_and_profile_rejected(self):
        for key, value in (("entry_id", "production"), ("profile", "municipal_essentials"),
                           ("package_schema_version", "0.2"),
                           ("package_jurisdiction_id", "jurisdiction-hi-maui-county"),
                           ("civic_gps_jurisdiction_id", "jur-us-hi-maui-county")):
            with self.subTest(key=key):
                catalog = copy.deepcopy(self.catalog)
                catalog["entries"][0][key] = value
                self.closed(self.build(catalog=catalog), "COUNTYWIDE_CANDIDATE_IDENTITY_INVALID")

    def test_binding_scope_and_malformed_contracts_rejected(self):
        changes = [("mode", "COUNTYWIDE_PRODUCTION"), ("scope", "COMPLETE_COUNTY"),
                   ("geoid", "15009"), ("division_id", "invented"),
                   ("offices", None), ("offices", [{}]), ("offices", [[], {}]),
                   ("expected_leadership_ids", []), ("expected_leadership_ids", [[], []])]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                catalog = copy.deepcopy(self.catalog)
                catalog["entries"][0]["countywide_binding"][key] = value
                self.closed(self.build(catalog=catalog))
        for value in (None, [], "COUNTYWIDE"):
            catalog = copy.deepcopy(self.catalog)
            catalog["entries"][0]["countywide_binding"] = value
            self.closed(self.build(catalog=catalog), "COUNTYWIDE_CANDIDATE_BINDING_REQUIRED")

    def test_district_seats_and_duplicate_offices_cannot_be_invented(self):
        for key, value in (("constituency", "DISTRICT"), ("seats", 6), ("seats", True),
                           ("expected_person_ids", ["duplicate"] * 7), ("seat_number", 1)):
            catalog = copy.deepcopy(self.catalog)
            catalog["entries"][0]["countywide_binding"]["offices"][1][key] = value
            self.closed(self.build(catalog=catalog), "COUNTYWIDE_CANDIDATE_OFFICES_INVALID")

    def test_wrong_missing_ambiguous_and_malformed_geography_closed(self):
        values = [[], {}, {"error": {"code": "TIMEOUT"}},
                  {"payload": {"jurisdictions": []}}, geography("jur-us-hi-hawaii-county")]
        ambiguous = geography()
        ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-maui-county"})
        values.append(ambiguous)
        for value in values:
            with self.subTest(value=value):
                self.closed(self.build(geographic=value))
        failed = self.build(geographic={"error": {"code": "TIMEOUT"}})
        self.assertEqual(failed["error"], "PACKAGE_CATALOG_GEOGRAPHY_INVALID")
        self.assertIn("TIMEOUT", failed["detail"])

    def test_poison_civic_facts_do_not_enter_projection(self):
        poisoned = geography()
        for field in ("offices", "officeholders", "applicable_offices", "action_links"):
            poisoned["payload"][field] = [{"office_id": "poison", "person_id": "poison"}]
        self.assertEqual(self.build(), self.build(geographic=poisoned))

    def test_catalog_ambiguity_rejected_before_archive_load(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["entries"].append(copy.deepcopy(catalog["entries"][0]))
        with patch.object(package_catalog, "reconstruct_package") as reconstruct:
            self.closed(self.build(catalog=catalog), "PACKAGE_CATALOG_ENTRY_ID_DUPLICATE")
            reconstruct.assert_not_called()

    def test_archive_pin_and_bytes_are_enforced(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["entries"][0]["artifact"]["archive_sha256"] = "0" * 64
        self.closed(self.build(catalog=catalog), "COUNTYWIDE_CANDIDATE_ARCHIVE_PIN_REQUIRED")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parts = sorted(ROOT.glob(self.spec["artifact"]["parts_glob"]))
            for path in parts:
                dest = root / path.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
            bad = root / parts[0].relative_to(ROOT)
            content = bad.read_text()
            bad.write_text(("A" if content[0] != "A" else "B") + content[1:])
            self.closed(self.build(root=root), "PACKAGE_ARTIFACT_SHA256_MISMATCH")

    def test_roster_loss_extra_duplicate_and_provisional_identity_closed(self):
        for mutation in ("missing", "extra", "duplicate", "provisional", "foreign_person"):
            with self.subTest(mutation=mutation):
                package = copy.deepcopy(self.package)
                terms = package["records"]["role_terms"]
                if mutation == "missing":
                    terms.pop()
                elif mutation == "extra":
                    terms.append({**terms[0], "role_term_id": "extra"})
                elif mutation == "duplicate":
                    terms[1]["person_id"] = terms[2]["person_id"]
                elif mutation == "provisional":
                    package["records"]["people"][0]["person_status"] = "PROVISIONAL"
                else:
                    package["records"]["people"][0]["jurisdiction_id"] = "foreign"
                with patch.object(package_catalog, "reconstruct_package", return_value=package):
                    self.closed(self.build())

    def test_source_and_leadership_loss_closed_through_catalog(self):
        for table in ("people", "offices", "role_terms", "leadership_roles"):
            for source in ("", "missing-source"):
                package = copy.deepcopy(self.package)
                package["records"][table][0]["source_ids"] = source
                with self.subTest(table=table, source=source), patch.object(
                        package_catalog, "reconstruct_package", return_value=package):
                    self.closed(self.build())
        package = copy.deepcopy(self.package)
        package["records"]["leadership_roles"].pop()
        with patch.object(package_catalog, "reconstruct_package", return_value=package):
            self.closed(self.build(), "COUNTYWIDE_PREVIEW_LEADERSHIP_SET_DRIFT")

    def test_output_determinism_and_no_input_aliasing(self):
        original = copy.deepcopy((self.package, self.catalog))
        with patch.object(package_catalog, "reconstruct_package", return_value=self.package):
            first, second = self.build(), self.build()
        self.assertEqual(first, second)
        digest = first.pop("deterministic_sha256")
        self.assertEqual(digest, adapter.preview.package_source.sha256_bytes(
            adapter.preview.package_source.canonical_json_bytes(first)))
        first["warnings"].clear()
        first["applicable_offices"][0]["holders"][0]["person"]["canonical_name"] = "changed"
        self.assertEqual((self.package, self.catalog), original)

    def test_onboarding_roundtrip_preserves_binding_and_flags(self):
        catalog, route = runner.build_candidate_catalog(ROOT, self.spec)
        self.assertEqual(catalog, self.catalog)
        self.assertEqual(route["action"], "VERIFY_EXISTING_ONLY")
        self.assertEqual(route["routing_writes"], 0)
        entry = onboarding.build_catalog_entry(self.spec)
        self.assertEqual(entry, materialize.catalog_entry(self.spec))
        bound = package_catalog.binding_from_entry(entry)
        self.assertEqual(bound["countywide_binding"], self.spec["countywide_binding"])
        bound["countywide_binding"]["offices"].clear()
        self.assertEqual(entry, self.catalog["entries"][0])
        entry["countywide_binding"]["offices"].clear()
        self.assertEqual(len(self.spec["countywide_binding"]["offices"]), 2)

    def test_production_staging_and_route_regeneration_remain_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "staged"
            replay = materialize.materialize(ROOT, adapter.preview.PACKAGE_ID, Path(td) / "production-noop")
            self.assertEqual(replay["changes_required"], 0)
            with self.assertRaises(materialize.MaterializeError):
                materialize.routing_record(self.spec)
            with self.assertRaises(onboarding.OnboardingError):
                onboarding.run(ROOT / runner.SPEC, ROOT, out, False)
            self.assertFalse(out.exists())

    def test_existing_route_changes_duplicates_or_missing_fail_closed(self):
        original = json.loads((ROOT / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
        for mutation in ("missing", "duplicate", "scope", "hold", "office_rule", "release"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "civic_gps_extensions").mkdir()
                registry = copy.deepcopy(original)
                row = next(r for r in registry["bundles"] if r["adapter_id"] == "BASE-HI-KAUAI-COUNTY")
                if mutation == "missing": registry["bundles"].remove(row)
                elif mutation == "duplicate": registry["bundles"].append(copy.deepcopy(row))
                elif mutation == "scope": row["scope_match"] = {"equals": "15007"}
                elif mutation == "hold": row["ev_onboarding_status"] = "READY"
                elif mutation == "office_rule": row["applicable_office_rules"] = [{"office_id": "invented"}]
                else: row["release_files"] = ["changed"]
                (root / "civic_gps_extensions/registry_bundles.v0.1.json").write_text(json.dumps(registry))
                with self.assertRaises(ValueError):
                    runner.verify_existing_route(root, self.spec)

    def test_route_release_civic_facts_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "civic_gps_extensions").mkdir()
            shutil.copyfile(ROOT / "civic_gps_extensions/registry_bundles.v0.1.json",
                            root / "civic_gps_extensions/registry_bundles.v0.1.json")
            spec = copy.deepcopy(self.spec)
            release = json.loads((ROOT / spec["routing"]["release_path"]).read_text())
            release["payload"]["offices"] = [{"office_id": "invented"}]
            raw = json.dumps(release).encode()
            (root / spec["routing"]["release_path"]).write_bytes(raw)
            spec["routing"]["release_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, "acquired civic facts"):
                runner.verify_existing_route(root, spec)

    def test_live_address_api_forwards_explicit_candidate_opt_in(self):
        model = representation_catalog.build_representation_from_live_address(
            self.spec["live_addresses"][0]["address"], repo_root=ROOT,
            resolver=FixtureResolver(self.spec), catalog_path=ROOT / runner.CATALOG, allow_candidate=True)
        self.assertEqual(model["status"], "PASS", model)
        class BrokenResolver:
            def resolve(self, *args, **kwargs): raise TimeoutError("fixture timeout")
        self.closed(representation_catalog.build_representation_from_live_address(
            "synthetic", repo_root=ROOT, resolver=BrokenResolver(),
            catalog_path=ROOT / runner.CATALOG, allow_candidate=True), "CIVIC_GPS_RESOLUTION_EXCEPTION")

    def test_acceptance_runner_labels_fixture_and_retains_all_holds(self):
        before = runner.preview_runner.snapshot(ROOT)
        report = runner.run_candidate(ROOT, FixtureResolver(self.spec), live=False)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validation_mode"], "SYNTHETIC_FIXTURE")
        self.assertIsNone(report["source_commit"])
        self.assertEqual(len(report["positive_controls"]), 2)
        self.assertEqual(len(report["routing_holds"]), 4)
        self.assertEqual(sorted(row["status"] for row in report["routing_holds"]), ["READY"] + ["REVIEW_REQUIRED"] * 3)
        self.assertEqual(report["auto_promoted"], 0)
        self.assertEqual(report["canonical_writes"], 0)
        self.assertEqual(before, runner.preview_runner.snapshot(ROOT))
        self.assertEqual(report["source_review"]["known_omitted_offices"], ["Prosecuting Attorney"])

    def test_unresolved_negative_never_counts_as_passing_evidence(self):
        class UnresolvedNegative(FixtureResolver):
            def resolve(self, address, observed_on=None):
                if address == self.binding["negative_address"]["address"]:
                    return {"error": {"code": "NO_MATCH"}}
                return super().resolve(address, observed_on)
        with self.assertRaisesRegex(ValueError, "negative control did not resolve"):
            runner.run_candidate(ROOT, UnresolvedNegative(self.spec), live=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
