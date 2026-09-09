#!/usr/bin/env python3
"""Production catalog activation, receipt integrity, expiry, and isolation tests."""
from __future__ import annotations

import copy
from datetime import date
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

from consumers.empowered_vote import countywide_production as production, package_catalog, representation_catalog
from tools import ev_kauai_production_activation as runner, ev_onboarding_proposal as proposal
from tools import ev_onboarding_materialize as materialize, ev_jurisdiction_onboarding as onboarding
from ev_kauai_countywide_preview_test import geography, FixtureResolver


class ProductionActivationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = json.loads((ROOT / production.SPEC_PATH).read_text())
        for folder in ("data/packages/hi/kauai-county", "onboarding/ev", "acceptance/ev"):
            shutil.copytree(ROOT / folder, self.root / folder)
        for rel in ("consumers/empowered_vote/package_catalog.v0.1.json",
                    "civic_gps_extensions/registry_bundles.v0.1.json", self.spec["routing"]["release_path"]):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        self.catalog_path = self.root / "consumers/empowered_vote/package_catalog.v0.1.json"
        self.entry = onboarding.build_catalog_entry(self.spec)

    def build(self, geographic=None):
        return representation_catalog.build_representation_from_catalog(
            "synthetic fixture", geography() if geographic is None else geographic,
            repo_root=self.root, catalog_path=self.catalog_path)

    def closed(self, model, code=None):
        self.assertEqual(model["status"], "FAIL-CLOSED", model)
        self.assertNotIn("applicable_offices", model)
        self.assertNotIn("projections", model)
        self.assertIsNot(model.get("publication_eligible"), True)
        self.assertEqual(model["canonical_writes"], 0)
        if code:
            self.assertEqual(model["error"], code)

    def change_entry(self, update):
        catalog = json.loads(self.catalog_path.read_text())
        entry = next(row for row in catalog["entries"] if row["entry_id"] == production.ENTRY_ID)
        update(entry)
        self.catalog_path.write_text(json.dumps(catalog))
        return entry

    def change_receipt(self, update):
        path = self.root / production.RECEIPT_PATH
        receipt = json.loads(path.read_text())
        update(receipt)
        path.write_text(json.dumps(receipt))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.entry = self.change_entry(lambda row: row["countywide_profile"]["acceptance_receipt"].update(sha256=digest))
        spec_path = self.root / production.SPEC_PATH
        spec = json.loads(spec_path.read_text())
        spec["countywide_profile"]["acceptance_receipt"]["sha256"] = digest
        spec_path.write_text(json.dumps(spec))

    def test_default_production_catalog_preserves_exact_preview_records(self):
        result = self.build()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["package_catalog_entry_id"], production.ENTRY_ID)
        self.assertEqual(result["production_profile_id"], production.PROFILE_ID)
        self.assertEqual((result["office_count"], result["current_holder_count"]), (2, 8))
        for key, value in production.FLAGS.items():
            self.assertIs(result[key], value)
        self.assertFalse(result["preview_only"])
        self.assertEqual(result["source_review_expires_on"], "2026-12-01")
        package = package_catalog.reconstruct_package(self.entry, self.root)
        reference = production.candidate.build_representation(
            package, "synthetic fixture", geography(), production.candidate_entry(self.entry))
        for key in ("applicable_offices", "source_evidence", "source_assertions", "warnings"):
            self.assertEqual(result[key], reference[key])
        self.assertTrue(result["representation_only"])
        self.assertFalse(result["full_essentials_supported"])

    def test_candidate_contract_does_not_become_production_by_flipping_flags(self):
        entry = production.candidate_entry(self.entry)
        entry.update(production.FLAGS)
        self.catalog_path.write_text(json.dumps({"catalog_version": "0.1", "entries": [entry]}))
        self.closed(self.build(), "COUNTYWIDE_CANDIDATE_NOT_ENABLED")
        result = representation_catalog.build_representation_from_catalog(
            "synthetic", geography(), repo_root=self.root, catalog_path=self.catalog_path, allow_candidate=True)
        self.closed(result, "COUNTYWIDE_CANDIDATE_HOLD_REQUIRED")

    def test_production_flags_must_preserve_publication_and_coverage_holds(self):
        original = self.catalog_path.read_text()
        for key, value in production.FLAGS.items():
            for wrong in (not value, int(value), None):
                with self.subTest(key=key, wrong=wrong):
                    self.catalog_path.write_text(original)
                    self.change_entry(lambda row: row.update({key: wrong}))
                    self.closed(self.build(), "COUNTYWIDE_PRODUCTION_FLAGS_INVALID")

    def test_missing_or_altered_receipt_fails_closed(self):
        path = self.root / production.RECEIPT_PATH
        path.write_text(path.read_text() + " ")
        self.closed(self.build(), "COUNTYWIDE_PRODUCTION_RECEIPT_HASH_DRIFT")
        path.unlink()
        self.closed(self.build(), "COUNTYWIDE_PRODUCTION_RECEIPT_UNAVAILABLE")

    def test_receipt_path_traversal_and_mixed_profile_rejected(self):
        original = self.catalog_path.read_text()
        for wrong in ("../../receipt.json", "/tmp/receipt.json", "acceptance/ev/other.json"):
            self.catalog_path.write_text(original)
            self.change_entry(lambda row: row["countywide_profile"]["acceptance_receipt"].update(path=wrong))
            self.closed(self.build(), "COUNTYWIDE_PRODUCTION_RECEIPT_REFERENCE_INVALID")
        self.catalog_path.write_text(original)
        self.change_entry(lambda row: row.update(production_profile={"profile_id": "tx_legislative_two_office_v0.1"}))
        self.closed(self.build(), "COUNTYWIDE_PRODUCTION_CONTRACT_INVALID")

    def test_rehashed_receipt_cannot_expand_scope_or_authorize_publication(self):
        original = (self.root / production.RECEIPT_PATH).read_text()
        changes = [("scope", "COMPLETE_COUNTY"), ("publication_authorized", True),
                   ("deployment_authorized", True), ("complete_jurisdiction", True),
                   ("binding_sha256", "0" * 64), ("archive_sha256", "0" * 64),
                   ("package_sha256", "0" * 64), ("routing", None),
                   ("onboarding_expected", {"office_rows": 1})]
        for key, wrong in changes:
            with self.subTest(key=key):
                (self.root / production.RECEIPT_PATH).write_text(original)
                self.change_receipt(lambda row: row.update({key: wrong}))
                self.closed(self.build())

    def test_expired_and_future_reviews_block_public_catalog(self):
        for current, allowed in ((date(2026, 9, 8), False), (date(2026, 9, 9), True),
                                  (date(2026, 11, 30), True), (date(2026, 12, 1), False)):
            with self.subTest(current=current), patch.object(production, "datetime") as clock:
                clock.now.return_value.date.return_value = current
                model = self.build()
                if allowed:
                    self.assertEqual(model["status"], "PASS")
                else:
                    self.closed(model, "COUNTYWIDE_PRODUCTION_SOURCE_REVIEW_EXPIRED_OR_FUTURE")

    def test_rehashed_bad_review_dates_and_missing_official_sources_rejected(self):
        original = (self.root / production.RECEIPT_PATH).read_text()
        for key, value in (("expires_on", "2027-01-01"), ("reviewed_on", "not-a-date"),
                           ("sources", []), ("roster_matches_package", False),
                           ("known_omitted_offices", []), ("identity_policy", "PROMOTE_ALL")):
            with self.subTest(key=key):
                (self.root / production.RECEIPT_PATH).write_text(original)
                self.change_receipt(lambda row: row["source_review"].update({key: value}))
                self.closed(self.build())

    def test_archive_binding_and_office_scope_cannot_drift(self):
        self.change_entry(lambda row: row["artifact"].update(archive_sha256="0" * 64))
        self.closed(self.build(), "COUNTYWIDE_PRODUCTION_CONTRACT_INVALID")

    def test_wrong_county_ambiguous_geography_and_resolver_error_rejected(self):
        for value in (geography("jur-us-hi-hawaii-county"), {}, [], {"error": {"code": "TIMEOUT"}}):
            self.closed(self.build(value))
        ambiguous = geography()
        ambiguous["payload"]["jurisdictions"].append({"jurisdiction_id": "jur-us-hi-maui-county"})
        self.closed(self.build(ambiguous), "COUNTYWIDE_PREVIEW_AMBIGUOUS_COUNTY")

    def test_tampered_package_records_fail_even_if_loader_is_bypassed(self):
        package = package_catalog.reconstruct_package(self.entry, self.root)
        package["records"]["role_terms"].pop()
        with patch.object(package_catalog, "reconstruct_package", return_value=package):
            self.closed(self.build(), "COUNTYWIDE_PRODUCTION_PACKAGE_DRIFT")

    def test_route_drift_does_not_auto_create_or_replace_geography(self):
        path = self.root / "civic_gps_extensions/registry_bundles.v0.1.json"
        registry = json.loads(path.read_text())
        row = next(row for row in registry["bundles"] if row["adapter_id"] == "BASE-HI-KAUAI-COUNTY")
        row["scope_match"] = {"geography": "county", "equals": "15007"}
        path.write_text(json.dumps(registry))
        before = path.read_bytes()
        self.closed(self.build(), "COUNTYWIDE_PRODUCTION_ROUTE_DRIFT")
        self.assertEqual(path.read_bytes(), before)

    def test_catalog_spec_pair_is_required_for_proposal_readiness(self):
        self.assertEqual(proposal.propose(self.root, production.candidate.preview.PACKAGE_ID)["status"], "READY")
        (self.root / production.SPEC_PATH).unlink()
        with self.assertRaises(production.CountywideProductionError):
            proposal.propose(self.root, production.candidate.preview.PACKAGE_ID)

    def test_spec_drift_is_rejected_before_materialization(self):
        path = self.root / production.SPEC_PATH
        spec = json.loads(path.read_text())
        spec["live_addresses"] = ["unapproved", "unapproved2"]
        path.write_text(json.dumps(spec))
        with self.assertRaises(production.CountywideProductionError):
            materialize.materialize(self.root, production.candidate.preview.PACKAGE_ID, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_route_without_catalog_or_spec_remains_review_required(self):
        catalog = json.loads(self.catalog_path.read_text())
        catalog["entries"] = [row for row in catalog["entries"] if row["entry_id"] != production.ENTRY_ID]
        self.catalog_path.write_text(json.dumps(catalog))
        (self.root / production.SPEC_PATH).unlink()
        result = proposal.propose(self.root, production.candidate.preview.PACKAGE_ID)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIsNone(result["production_spec"])
        self.closed(self.build(), "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")

    def test_valid_materialization_is_all_noop_and_preserves_route_and_sources(self):
        before = runner.preview_runner.snapshot(self.root)
        report = materialize.materialize(self.root, production.candidate.preview.PACKAGE_ID, self.root / "staged")
        self.assertEqual(report["changes_required"], 0)
        self.assertTrue(all(row["action"] == "NOOP" for row in report["changes"]))
        self.assertEqual(before, runner.preview_runner.snapshot(self.root))

    def test_existing_tacoma_akron_fircrest_and_texas_entries_preserved(self):
        catalog = package_catalog.load_catalog(ROOT / "consumers/empowered_vote/package_catalog.v0.1.json")
        other = [row for row in catalog["entries"] if row["entry_id"] != production.ENTRY_ID]
        self.assertEqual(len(other), 4)
        self.assertEqual({row["entry_id"] for row in other}, {
            "wa-tacoma-municipal-essentials-v0.2", "co-akron-municipal-representation-v0.1",
            "wa-fircrest-municipal-essentials-v0.2", "tx-legislative-two-office-v0.1-hosted-candidate"})

    def test_full_essentials_stays_unsupported_for_kauai(self):
        from consumers.empowered_vote import full_essentials_catalog
        model = package_catalog.build_essentials_from_catalog(
            "synthetic", geography(), repo_root=self.root, catalog_path=self.catalog_path,
            profile="municipal_representation")
        self.closed(model)
        self.closed(full_essentials_catalog.build_full_essentials_from_catalog(
            "synthetic", geography(), repo_root=self.root, catalog_path=self.catalog_path,
            profile="municipal_representation"))

    def test_acceptance_runner_labels_synthetic_and_keeps_three_other_holds(self):
        fixture = {"negative_address": {"address": "25 Aupuni Street, Hilo, HI 96720",
            "expected_civic_jurisdiction_id": "jur-us-hi-hawaii-county"}}
        report = runner.run_activation(ROOT, FixtureResolver(fixture), live=False)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validation_mode"], "SYNTHETIC_FIXTURE")
        self.assertEqual(report["other_hi_production_holds"], 3)
        self.assertEqual(report["auto_promoted"], 0)
        self.assertFalse(report["publication_authorized"])
        self.assertFalse(report["deployment_authorized"])

    def test_unresolved_negative_is_never_counted_as_success(self):
        class Resolver:
            def resolve(self, address, observed_on=None):
                return {"error": {"code": "NO_MATCH"}} if address.startswith("25 Aupuni") else geography()
        with self.assertRaisesRegex(ValueError, "negative did not successfully resolve"):
            runner.run_activation(ROOT, Resolver(), live=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
