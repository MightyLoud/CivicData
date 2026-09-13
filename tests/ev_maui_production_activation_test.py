#!/usr/bin/env python3
"""Maui default-catalog acceptance, freshness, tamper, and isolation controls."""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import maui_countywide_production as production, package_catalog, representation_catalog
from tools import ev_maui_production_activation as runner, ev_onboarding_proposal as proposal
from tools import ev_jurisdiction_onboarding as onboarding, ev_onboarding_materialize as materialize
from ev_maui_countywide_preview_test import geography, FixtureResolver


class MauiActivationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for folder in ("data/packages/hi/maui-county", "previews/ev/maui"):
            shutil.copytree(ROOT / folder, self.root / folder)
        for rel in (production.SPEC_PATH, production.RECEIPT_PATH, production.REVIEW_REFERENCE["path"],
            production.candidate.SOURCE_CORRECTION["path"], "previews/ev/maui_countywide.v0.1.json",
            "consumers/empowered_vote/package_catalog.v0.1.json", "civic_gps_extensions/registry_bundles.v0.1.json",
            production.ROUTING["release_path"]):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        self.catalog_path = self.root / "consumers/empowered_vote/package_catalog.v0.1.json"
        self.spec = json.loads((self.root / production.SPEC_PATH).read_text())
        self.entry = onboarding.build_catalog_entry(self.spec)

    def build(self, geographic=None):
        return representation_catalog.build_representation_from_catalog("synthetic fixture",
            geography() if geographic is None else geographic, repo_root=self.root, catalog_path=self.catalog_path)

    def closed(self, model, code=None):
        self.assertEqual(model["status"], "FAIL-CLOSED", model)
        self.assertNotIn("applicable_offices", model)
        self.assertNotIn("projections", model)
        self.assertIsNot(model.get("publication_eligible"), True)
        self.assertEqual(model["canonical_writes"], 0)
        if code: self.assertEqual(model["error"], code)

    def change_entry(self, update):
        catalog = json.loads(self.catalog_path.read_text())
        entry = next(r for r in catalog["entries"] if r["entry_id"] == production.ENTRY_ID)
        update(entry)
        self.catalog_path.write_text(json.dumps(catalog))
        return entry

    def change_receipt(self, update):
        path = self.root / production.RECEIPT_PATH
        receipt = json.loads(path.read_text());update(receipt)
        path.write_text(json.dumps(receipt))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.entry = self.change_entry(lambda r: r["countywide_profile"]["acceptance_receipt"].update(sha256=sha))
        self.spec["countywide_profile"]["acceptance_receipt"]["sha256"] = sha
        (self.root / production.SPEC_PATH).write_text(json.dumps(self.spec))

    def test_default_catalog_returns_exact_certified_roster_and_residency_records(self):
        result = self.build()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual((result["office_count"], result["current_holder_count"], result["residency_area_count"]), (10, 10, 9))
        self.assertEqual(result["package_catalog_entry_id"], production.ENTRY_ID)
        self.assertEqual(result["production_profile_id"], production.PROFILE_ID)
        self.assertFalse(result["preview_only"])
        self.assertTrue(result["representation_only"])
        self.assertFalse(result["full_essentials_supported"])
        for k, v in production.FLAGS.items(): self.assertIs(result[k], v)
        package = package_catalog.reconstruct_package(self.entry, self.root)
        candidate = production.candidate.build_representation(package, "synthetic fixture", geography(),
                                                             production.candidate_entry(self.entry))
        for field in ("applicable_offices", "residency_areas", "source_evidence", "source_assertions", "warnings"):
            self.assertEqual(result[field], candidate[field])
        self.assertEqual(result["source_review_expires_on"], "2026-10-12")

    def test_all_production_flags_are_strict_booleans(self):
        original = self.catalog_path.read_text()
        for key, value in production.FLAGS.items():
            for wrong in (not value, int(value), None):
                with self.subTest(key=key, wrong=wrong):
                    self.catalog_path.write_text(original)
                    self.change_entry(lambda row: row.update({key: wrong}))
                    self.closed(self.build(), "MAUI_PRODUCTION_FLAGS_INVALID")

    def test_candidate_flags_alone_cannot_activate_production(self):
        entry = production.candidate_entry(self.entry)
        entry.update(production.FLAGS)
        self.catalog_path.write_text(json.dumps({"catalog_version": "0.1", "entries": [entry]}))
        self.closed(self.build(), "COUNTYWIDE_CANDIDATE_NOT_ENABLED")
        self.closed(representation_catalog.build_representation_from_catalog("fixture", geography(),
            repo_root=self.root, catalog_path=self.catalog_path, allow_candidate=True), "MAUI_CANDIDATE_HOLD_REQUIRED")

    def test_missing_and_changed_receipt_block_default_service(self):
        path = self.root / production.RECEIPT_PATH
        path.write_text(path.read_text() + " ")
        self.closed(self.build(), "MAUI_PRODUCTION_RECEIPT_HASH_DRIFT")
        path.unlink()
        self.closed(self.build(), "MAUI_PRODUCTION_RECEIPT_UNAVAILABLE")

    def test_source_review_observation_tampering_is_rejected(self):
        path = self.root / production.REVIEW_REFERENCE["path"]
        value = json.loads(path.read_text())
        value["source_observations"][0]["raw_excerpt"] = "invented"
        path.write_text(json.dumps(value))
        self.closed(self.build(), "MAUI_PRODUCTION_SOURCE_REVIEW_HASH_DRIFT")

    def test_missing_correction_receipt_blocks_default_service(self):
        (self.root / production.candidate.SOURCE_CORRECTION["path"]).unlink()
        self.closed(self.build(), "MAUI_PRODUCTION_SOURCE_CORRECTION_UNAVAILABLE")

    def test_expiry_and_future_dates_block_default_service(self):
        for current in (date(2026, 9, 11), date(2026, 10, 12), date(2027, 1, 2)):
            with self.subTest(current=current), patch.object(production, "datetime") as clock:
                clock.now.return_value.date.return_value = current
                self.closed(self.build(), "MAUI_PRODUCTION_SOURCE_REVIEW_EXPIRED_OR_FUTURE")
        for current in (date(2026, 9, 12), date(2026, 10, 11)):
            self.assertEqual(production.load_receipt(self.entry, self.root, today=current)["status"], "PASS")

    def test_rehashed_receipt_cannot_expand_scope_or_authorize_release(self):
        for key, wrong in (("scope", "COMPLETE_COUNTY"), ("publication_authorized", True),
                           ("deployment_authorized", True), ("complete_jurisdiction", True)):
            with self.subTest(key=key):
                self.change_receipt(lambda receipt: receipt.update({key: wrong}))
                self.closed(self.build(), "MAUI_PRODUCTION_RECEIPT_CONTRACT_INVALID")

    def test_rehashed_receipt_cannot_replace_review_or_corrected_package(self):
        self.change_receipt(lambda r: r.update(source_review={"path": production.REVIEW_REFERENCE["path"], "sha256": "0" * 64}))
        self.closed(self.build(), "MAUI_PRODUCTION_RECEIPT_CONTRACT_INVALID")

    def test_mixed_profile_and_path_traversal_are_rejected(self):
        self.change_entry(lambda row: row["countywide_profile"]["acceptance_receipt"].update(path="../../receipt.json"))
        self.closed(self.build(), "MAUI_PRODUCTION_RECEIPT_REFERENCE_INVALID")
        for key in ("district_binding", "district_bindings", "production_profile"):
            self.catalog_path.write_text((ROOT / "consumers/empowered_vote/package_catalog.v0.1.json").read_text())
            self.change_entry(lambda row: row.update({key: {}}))
            self.closed(self.build(), "MAUI_PRODUCTION_CONTRACT_INVALID")

    def test_archive_contract_is_pinned(self):
        self.change_entry(lambda row: row["artifact"].update(archive_sha256="0" * 64))
        self.closed(self.build(), "MAUI_PRODUCTION_CONTRACT_INVALID")

    def test_package_tampering_is_rejected_even_if_loader_is_bypassed(self):
        package = package_catalog.reconstruct_package(self.entry, self.root)
        next(r for r in package["records"]["role_terms"] if r["person_id"] ==
             "person-hi-maui-kauanoe-batangan")["selection_type"] = "ELECTED"
        with patch.object(package_catalog, "reconstruct_package", return_value=package):
            self.closed(self.build(), "MAUI_PRODUCTION_PACKAGE_DRIFT")

    def test_residency_geography_never_filters_offices(self):
        expected = self.build()["applicable_offices"]
        for area in production.candidate.preview.COUNCIL:
            self.assertEqual(self.build(geography(district=area))["applicable_offices"], expected)

    def test_wrong_and_ambiguous_counties_or_resolver_errors_fail_closed(self):
        self.closed(self.build(geography("jur-us-hi-hawaii-county")), "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")
        self.closed(self.build({"error": {"code": "TIMEOUT"}}), "PACKAGE_CATALOG_GEOGRAPHY_INVALID")
        ambiguous = geography();ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-hawaii-county"})
        self.closed(self.build(ambiguous), "MAUI_PREVIEW_AMBIGUOUS_COUNTY")
        ambiguous = geography();ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-kauai-county"})
        self.closed(self.build(ambiguous), "PACKAGE_SELECTION_AMBIGUOUS")

    def test_missing_spec_blocks_serving_and_proposal_readiness(self):
        (self.root / production.SPEC_PATH).unlink()
        self.closed(self.build(), "MAUI_PRODUCTION_SPEC_UNAVAILABLE")
        with self.assertRaises(production.MauiProductionError):
            proposal.propose(self.root, production.candidate.preview.PACKAGE_ID)

    def test_spec_drift_blocks_materialization(self):
        path = self.root / production.SPEC_PATH
        spec = json.loads(path.read_text());spec["live_addresses"] = ["unapproved"]
        path.write_text(json.dumps(spec))
        with self.assertRaises(ValueError):
            materialize.materialize(self.root, production.candidate.preview.PACKAGE_ID, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_route_without_explicit_installation_stays_review_required(self):
        catalog = json.loads(self.catalog_path.read_text())
        catalog["entries"] = [r for r in catalog["entries"] if r["entry_id"] != production.ENTRY_ID]
        self.catalog_path.write_text(json.dumps(catalog));(self.root / production.SPEC_PATH).unlink()
        result = proposal.propose(self.root, production.candidate.preview.PACKAGE_ID)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIsNone(result["production_spec"])
        self.closed(self.build(), "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")

    def test_valid_materialization_is_three_noops(self):
        result = materialize.materialize(self.root, production.candidate.preview.PACKAGE_ID, self.root / "out")
        self.assertEqual(result["changes_required"], 0)
        self.assertEqual([r["action"] for r in result["changes"]], ["NOOP"] * 3)
        self.assertEqual(result["canonical_writes"], 0)

    def test_source_raw_normalized_and_record_parity(self):
        review = json.loads((self.root / production.REVIEW_REFERENCE["path"]).read_text())
        rows = review["normalized_assertions"]
        holders = {(r["office_id"], r["person_id"]) for r in rows if r["type"] == "CURRENT_HOLDER"}
        expected = {(r["office_id"], r["expected_person_id"]) for r in production.candidate.preview.office_contracts()}
        self.assertEqual(holders, expected)
        self.assertEqual(len([r for r in rows if r["type"] == "RESIDENCY_QUALIFICATION"]), 9)
        self.assertEqual(len([r for r in rows if r["type"] == "LEADERSHIP"]), 2)
        self.assertTrue(review["qa"]["parity_ok"])
        self.assertEqual(len(review["source_observations"]), 13)

    def test_determinism_and_no_input_aliasing(self):
        first, second = self.build(), self.build()
        self.assertEqual(first, second)
        sha = first.pop("deterministic_sha256")
        self.assertEqual(sha, production.digest(first))
        first["applicable_offices"][0]["holders"].clear()
        self.assertEqual(self.build(), second)

    def test_full_essentials_remains_unsupported(self):
        from consumers.empowered_vote import full_essentials_catalog
        for function in (package_catalog.build_essentials_from_catalog, full_essentials_catalog.build_full_essentials_from_catalog):
            self.closed(function("fixture", geography(), repo_root=self.root,
                                 catalog_path=self.catalog_path, profile="municipal_representation"))

    def test_live_address_entry_point_needs_no_candidate_opt_in(self):
        result = representation_catalog.build_representation_from_live_address("fixture", repo_root=self.root,
            catalog_path=self.catalog_path, resolver=FixtureResolver({"negative_address": production.NEGATIVE}))
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["package_catalog_entry_id"], production.ENTRY_ID)

    def test_activation_runner_labels_fixture_and_keeps_other_counties_held(self):
        fixture = FixtureResolver({"negative_address": production.NEGATIVE})
        before = runner.adapter_runner.snapshot(ROOT)
        report = runner.run_activation(ROOT, fixture)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validation_mode"], "SYNTHETIC_FIXTURE")
        self.assertIsNone(report["source_commit"])
        self.assertEqual(len(fixture.calls), 3)
        self.assertEqual(report["auto_promoted"], 0)
        self.assertFalse(report["publication_authorized"])
        self.assertFalse(report["deployment_authorized"])
        self.assertEqual(before, runner.adapter_runner.snapshot(ROOT))

    def test_unresolved_negative_never_counts_as_success(self):
        class Resolver(FixtureResolver):
            def resolve(self, address, observed_on=None):
                return {"error": {"code": "NO_MATCH"}} if address.startswith("25 Aupuni") else geography()
        with self.assertRaisesRegex(ValueError, "NEGATIVE_GEOGRAPHY_UNRESOLVED"):
            runner.run_activation(ROOT, Resolver({"negative_address": production.NEGATIVE}))

    def test_output_cannot_overwrite_production_spec(self):
        path = ROOT / production.SPEC_PATH;before = path.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "tools/ev_maui_production_activation.py"),
            "--repo-root", str(ROOT), "--output", str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Output must be under", result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_activation_diff_rejects_other_catalog_and_acceptance_changes(self):
        from tools.ev_maui_activation_diff import verify_catalog_delta
        new = json.loads(self.catalog_path.read_text())
        old = {**new, "entries": [r for r in new["entries"] if r["entry_id"] != production.ENTRY_ID]}
        verify_catalog_delta(old, new, [str(production.SPEC_PATH), production.RECEIPT_PATH,
                                        production.REVIEW_REFERENCE["path"]])
        changed = copy.deepcopy(new);changed["entries"][0]["profile"] = "unreviewed"
        with self.assertRaisesRegex(ValueError, "Other production catalog"):
            verify_catalog_delta(old, changed, [])
        with self.assertRaisesRegex(ValueError, "Unrelated production"):
            verify_catalog_delta(old, new, ["acceptance/ev/kauai_countywide.v0.1.json"])

    def test_activation_diff_rejects_missing_or_duplicate_maui(self):
        from tools.ev_maui_activation_diff import verify_catalog_delta
        new = json.loads(self.catalog_path.read_text())
        old = {**new, "entries": [r for r in new["entries"] if r["entry_id"] != production.ENTRY_ID]}
        with self.assertRaises(ValueError): verify_catalog_delta(old, old, [])
        new["entries"].append(copy.deepcopy(self.entry))
        with self.assertRaises(ValueError): verify_catalog_delta(old, new, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
