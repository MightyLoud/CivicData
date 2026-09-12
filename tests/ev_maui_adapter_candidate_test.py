#!/usr/bin/env python3
"""Full catalog acceptance and rejection controls for the held Maui adapter."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_candidate as adapter, package_catalog, representation_catalog
from tools import ev_maui_adapter_candidate as runner, ev_jurisdiction_onboarding as onboarding
from tools import ev_onboarding_materialize as materialize
from ev_maui_countywide_preview_test import geography, FixtureResolver


class MauiCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / runner.SPEC).read_text())
        cls.catalog = json.loads((ROOT / runner.CATALOG).read_text())
        cls.package = package_catalog.reconstruct_package(cls.catalog["entries"][0], ROOT)

    def build(self, *, catalog=None, geographic=None, allow=True, root=ROOT):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "catalog.json"
            path.write_text(json.dumps(self.catalog if catalog is None else catalog))
            return representation_catalog.build_representation_from_catalog(
                "synthetic fixture", geography() if geographic is None else geographic,
                repo_root=root, catalog_path=path, allow_candidate=allow)

    def closed(self, result, code=None):
        self.assertEqual(result["status"], "FAIL-CLOSED", result)
        self.assertNotIn("applicable_offices", result)
        self.assertNotIn("projections", result)
        self.assertIsNot(result.get("production_eligible"), True)
        self.assertIsNot(result.get("publication_eligible"), True)
        self.assertEqual(result["canonical_writes"], 0)
        if code:
            self.assertEqual(result["error"], code)

    def test_full_catalog_path_preserves_all_governed_records(self):
        model = self.build()
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["package_catalog_entry_id"], adapter.ENTRY_ID)
        self.assertEqual((model["office_count"], model["current_holder_count"], model["residency_area_count"]),
                         (10, 10, 9))
        self.assertTrue(model["preview_only"])
        self.assertTrue(model["representation_only"])
        self.assertFalse(model["full_essentials_supported"])
        for key, value in adapter.FLAGS.items():
            self.assertIs(model[key], value)
        records = self.package["records"]
        self.assertCountEqual([r["office"] for r in model["applicable_offices"]], records["offices"])
        holders = [h for r in model["applicable_offices"] for h in r["holders"]]
        self.assertCountEqual([h["person"] for h in holders], records["people"])
        self.assertCountEqual([h["role_term"] for h in holders], records["role_terms"])
        self.assertCountEqual([r for h in holders for r in h["leadership_roles"]], records["leadership_roles"])
        self.assertEqual(model["residency_areas"], records["divisions"])
        for field in ("source_evidence", "source_assertions"):
            self.assertEqual(model[field], self.package["provenance"][field])
        self.assertEqual(model["warnings"], self.package["warnings"])

    def test_default_catalog_and_nonboolean_opt_in_stay_closed(self):
        for allow in (False, None, 1, "true"):
            self.closed(self.build(allow=allow), "COUNTYWIDE_CANDIDATE_NOT_ENABLED")
        for allow in (False, True):
            self.closed(representation_catalog.build_representation_from_catalog(
                "fixture", geography(), repo_root=ROOT, allow_candidate=allow),
                "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")

    def test_full_essentials_has_no_candidate_opt_in(self):
        self.closed(package_catalog.build_essentials_from_catalog(
            "fixture", geography(), repo_root=ROOT, catalog_path=ROOT / runner.CATALOG),
            "COUNTYWIDE_CANDIDATE_NOT_ENABLED")

    def test_hold_flags_cannot_be_flipped_omitted_or_integer(self):
        for key, value in adapter.FLAGS.items():
            for replacement in (not value, None, int(value)):
                with self.subTest(key=key, replacement=replacement):
                    catalog = copy.deepcopy(self.catalog)
                    catalog["entries"][0][key] = replacement
                    self.closed(self.build(catalog=catalog), "MAUI_CANDIDATE_HOLD_REQUIRED")
            catalog = copy.deepcopy(self.catalog)
            del catalog["entries"][0][key]
            self.closed(self.build(catalog=catalog), "MAUI_CANDIDATE_HOLD_REQUIRED")

    def test_mixed_production_and_district_bindings_are_rejected(self):
        for key in ("district_binding", "district_bindings", "production_profile", "countywide_profile"):
            for value in (None, {}, {"mode": "COUNTYWIDE_PRODUCTION"}):
                catalog = copy.deepcopy(self.catalog)
                catalog["entries"][0][key] = value
                with self.subTest(key=key, value=value):
                    self.closed(self.build(catalog=catalog))

    def test_schema_identity_and_cross_county_dispatch_drift_rejected(self):
        for key, value in (("entry_id", "candidate-hi-kauai-countywide-v0.1"),
                           ("profile", "municipal_essentials"), ("package_schema_version", "0.2"),
                           ("package_jurisdiction_id", "jurisdiction-hi-kauai-county"),
                           ("civic_gps_jurisdiction_id", "jur-us-hi-kauai-county")):
            catalog = copy.deepcopy(self.catalog)
            catalog["entries"][0][key] = value
            self.closed(self.build(catalog=catalog))

    def test_binding_and_residency_contract_cannot_be_broadened(self):
        mutations = [("mode", "COUNTYWIDE_PRODUCTION"), ("scope", "COMPLETE_COUNTY"), ("geoid", "15007"),
            ("expected_package_sha256", "0" * 64), ("source_correction", {}), ("offices", None),
            ("offices", [{}]), ("expected_leadership_ids", []), ("district_division_map", {})]
        for key, value in mutations:
            catalog = copy.deepcopy(self.catalog)
            catalog["entries"][0]["countywide_binding"][key] = value
            with self.subTest(key=key):
                self.closed(self.build(catalog=catalog))
        for key, value in (("constituency", "DISTRICT"), ("seats", True), ("seats", 9),
                           ("residency_area_id", None), ("expected_person_id", "wrong")):
            catalog = copy.deepcopy(self.catalog)
            catalog["entries"][0]["countywide_binding"]["offices"][1][key] = value
            self.closed(self.build(catalog=catalog), "MAUI_CANDIDATE_ROSTER_INVALID")

    def test_archive_location_hash_and_unsafe_paths_are_pinned(self):
        for key, value in (("archive_sha256", "0" * 64), ("parts_glob", "../../*.b64"),
                           ("package_subdir", "/tmp"), ("encoding", "raw")):
            catalog = copy.deepcopy(self.catalog)
            catalog["entries"][0]["artifact"][key] = value
            with patch.object(package_catalog, "reconstruct_package") as loader:
                self.closed(self.build(catalog=catalog))
                loader.assert_not_called()

    def test_corrupt_archive_bytes_fail_before_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rel = Path(adapter.ARTIFACT["parts_glob"])
            dest = root / rel
            dest.parent.mkdir(parents=True)
            content = (ROOT / rel).read_text()
            dest.write_text(("A" if content[0] != "A" else "B") + content[1:])
            self.closed(self.build(root=root), "PACKAGE_ARTIFACT_SHA256_MISMATCH")

    def test_residency_assignments_never_filter_countywide_offices(self):
        expected = self.build()["applicable_offices"]
        for area in adapter.preview.COUNCIL:
            actual = self.build(geographic=geography(district=area))
            self.assertEqual(actual["applicable_offices"], expected)
        for row in expected:
            self.assertEqual(row["representation_scope"], "COUNTYWIDE")
            self.assertEqual(row["seat_capacity"], 1)

    def test_wrong_ambiguous_failed_and_missing_geography_fail_closed(self):
        ambiguous = geography()
        ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-hawaii-county"})
        for geo in ({}, [], {"error": {"code": "TIMEOUT"}}, geography("jur-us-hi-hawaii-county"), ambiguous):
            self.closed(self.build(geographic=geo))

    def test_civic_gps_office_facts_are_ignored(self):
        geo = geography()
        for field in ("offices", "officeholders", "applicable_offices", "action_links"):
            geo["payload"][field] = [{"office_id": "poison", "person_id": "poison"}]
        self.assertEqual(self.build(), self.build(geographic=geo))

    def test_uncorrected_appointment_and_other_package_drift_fail_closed(self):
        for mutation in ("appointment", "lost_holder", "duplicate_holder", "provisional", "source",
                         "leadership", "residency", "unreviewed_note"):
            package = copy.deepcopy(self.package)
            records = package["records"]
            if mutation == "appointment":
                next(t for t in records["role_terms"] if t["person_id"] ==
                     "person-hi-maui-kauanoe-batangan")["selection_type"] = "ELECTED"
            elif mutation == "lost_holder": records["role_terms"].pop()
            elif mutation == "duplicate_holder": records["role_terms"][1]["person_id"] = records["role_terms"][0]["person_id"]
            elif mutation == "provisional": records["people"][0]["person_status"] = "PROVISIONAL"
            elif mutation == "source": records["offices"][0]["source_ids"] = "missing-source"
            elif mutation == "leadership": records["leadership_roles"].pop()
            elif mutation == "residency": records["divisions"][0]["address_routing_level"] = "ELECTORATE"
            else: records["people"][0]["notes"] = "unreviewed"
            with self.subTest(mutation=mutation), patch.object(package_catalog, "reconstruct_package", return_value=package):
                self.closed(self.build())

    def test_duplicate_catalog_entries_fail_before_loading(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["entries"].append(copy.deepcopy(catalog["entries"][0]))
        with patch.object(package_catalog, "reconstruct_package") as loader:
            self.closed(self.build(catalog=catalog), "PACKAGE_CATALOG_ENTRY_ID_DUPLICATE")
            loader.assert_not_called()

    def test_deterministic_output_and_input_independence(self):
        before = copy.deepcopy((self.package, self.catalog))
        with patch.object(package_catalog, "reconstruct_package", return_value=self.package):
            first, second = self.build(), self.build()
        self.assertEqual(first, second)
        digest = first.pop("deterministic_sha256")
        self.assertEqual(digest, adapter.preview.package_source.sha256_bytes(
            adapter.preview.package_source.canonical_json_bytes(first)))
        first["applicable_offices"][1]["residency_qualification"]["notes"] = "changed"
        first["source_assertions"].clear()
        self.assertEqual((self.package, self.catalog), before)

    def test_onboarding_builders_preserve_binding_and_flags(self):
        catalog, route = runner.build_candidate_catalog(ROOT, self.spec)
        self.assertEqual(catalog, self.catalog)
        self.assertEqual(route["action"], "VERIFY_EXISTING_ONLY")
        self.assertEqual(route["routing_writes"], 0)
        self.assertEqual(onboarding.build_catalog_entry(self.spec), materialize.catalog_entry(self.spec))
        bound = package_catalog.binding_from_entry(catalog["entries"][0])
        self.assertEqual(bound["countywide_binding"], self.spec["countywide_binding"])

    def test_production_staging_and_route_materialization_are_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "staged"
            with self.assertRaisesRegex(onboarding.OnboardingError, "isolated candidate runner"):
                onboarding.run(ROOT / runner.SPEC, ROOT, out, False)
            with self.assertRaisesRegex(materialize.MaterializeError, "existing route"):
                materialize.routing_record(self.spec)
            self.assertFalse(out.exists())

    def test_route_spec_and_governed_route_drift_rejected(self):
        spec = copy.deepcopy(self.spec)
        spec["routing"]["route_sha256"] = "0" * 64
        with self.assertRaises(ValueError): runner.verify_existing_route(ROOT, spec)
        registry = json.loads((ROOT / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
        next(r for r in registry["bundles"] if r["adapter_id"] == "BASE-HI-MAUI-COUNTY")["action_registry_files"] = ["invented"]
        with patch.object(runner.preview_runner, "assert_holds", return_value={}), patch.object(
                Path, "read_text", return_value=json.dumps(registry)):
            with self.assertRaisesRegex(ValueError, "ROUTE_HASH_DRIFT"):
                runner.verify_existing_route(ROOT, self.spec)

    def test_live_address_entry_point_preserves_opt_in(self):
        kwargs = {"repo_root": ROOT, "catalog_path": ROOT / runner.CATALOG, "resolver": FixtureResolver(self.spec)}
        result = representation_catalog.build_representation_from_live_address("fixture", allow_candidate=True, **kwargs)
        self.assertEqual(result["status"], "PASS", result)
        self.closed(representation_catalog.build_representation_from_live_address("fixture", **kwargs),
                    "COUNTYWIDE_CANDIDATE_NOT_ENABLED")

    def test_runner_retains_source_parity_production_holds_and_protected_content(self):
        before = runner.snapshot(ROOT)
        report = runner.run_candidate(ROOT, FixtureResolver(self.spec))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validation_mode"], "SYNTHETIC_FIXTURE")
        self.assertIsNone(report["source_commit"])
        self.assertEqual(len(report["positive_controls"]), 2)
        self.assertEqual(report["source_correction"]["status"], "PASS")
        self.assertEqual(report["route_verification"]["production_hold"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["auto_promoted"], 0)
        self.assertEqual(report["canonical_writes"], 0)
        self.assertEqual(before, runner.snapshot(ROOT))

    def test_unresolved_negative_never_counts_as_success(self):
        class UnresolvedNegative(FixtureResolver):
            def resolve(self, address, observed_on=None):
                if address == self.binding["negative_address"]["address"]:
                    return {"error": {"code": "TIMEOUT"}}
                return super().resolve(address, observed_on)
        with self.assertRaisesRegex(ValueError, "NEGATIVE_GEOGRAPHY_UNRESOLVED"):
            runner.run_candidate(ROOT, UnresolvedNegative(self.spec))

    def test_cli_rejects_output_into_protected_configuration(self):
        path = ROOT / runner.CATALOG
        before = path.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "tools/ev_maui_adapter_candidate.py"),
            "--repo-root", str(ROOT), "--output", str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Output must be under", result.stderr)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
