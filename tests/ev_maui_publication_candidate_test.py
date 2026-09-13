#!/usr/bin/env python3
"""Offline candidate integrity, retained evidence, and publication boundary tests."""
from __future__ import annotations

import base64
import copy
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import ev_maui_publication_candidate as candidate


class PublicationCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = candidate.verify_inputs(ROOT)
        cls.manifest = candidate.load_json((ROOT / candidate.MANIFEST).read_bytes())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", "__pycache__", "artifacts", "*.pyc"))

    def test_retained_original_zip_and_live_projection_are_intact(self):
        live = candidate.read_evidence(self.root)
        self.assertEqual(live["source_commit"], candidate.CERTIFIED_ACTIVATION)
        self.assertEqual(live["validation_mode"], "LIVE_CIVIC_GPS")
        self.assertEqual(len(live["positive_controls"]), 2)
        for row in live["positive_controls"]:
            self.assertTrue(row["representation"]["matched_address"])
            self.assertEqual((row["representation"]["office_count"], row["representation"]["current_holder_count"]), (10, 10))
        self.assertEqual(live["negative_control"]["result"]["error"], "PACKAGE_NOT_GOVERNED_FOR_RESOLVED_ADDRESS")
        self.assertEqual(live["negative_control"]["geography"]["jurisdiction_ids"], ["jur-us-hi-hawaii-county"])
        self.assertFalse(self.manifest["activation_evidence"]["fresh_live_run"])
        self.assertFalse(self.manifest["capabilities"]["hosted_delivery_certified"])

    def test_build_is_deterministic_metadata_only_and_does_not_mutate_inputs(self):
        before = candidate.preview_runner.snapshot(self.root)
        candidate.validate_manifest(self.manifest, self.receipt)
        for folder in ("first", "second"):
            candidate.write_bundle(self.root, self.root / candidate.ARTIFACTS / folder, self.manifest, {"status": "TEST"})
        first = self.root / candidate.ARTIFACTS / "first/release-assets"
        second = self.root / candidate.ARTIFACTS / "second/release-assets"
        self.assertEqual([p.name for p in first.iterdir()], [candidate.ASSET])
        self.assertEqual((first / candidate.ASSET).read_bytes(), (second / candidate.ASSET).read_bytes())
        self.assertEqual((first / candidate.ASSET).read_bytes(), (self.root / candidate.MANIFEST).read_bytes())
        self.assertEqual(before, candidate.preview_runner.snapshot(self.root))
        payload = (first / candidate.ASSET).read_text()
        for forbidden in ("person-hi-maui-", "applicable_offices", "role_terms", "railway.app", "UEsDB"):
            self.assertNotIn(forbidden, payload)

    def test_manifest_rejects_scope_flags_hosted_claims_and_extra_assets(self):
        edits = [
            lambda m: m.update(integration_target_commit="main"),
            lambda m: m.update(integration_target_commit="0" * 40),
            lambda m: m.update(county_geoid="15005"),
            lambda m: m.update(scope="COMPLETE_COUNTY"),
            lambda m: m["counts"].update(office_rows=3),
            lambda m: m["counts"].update(current_holders=9),
            lambda m: m["preserved_production_flags"].update(publication_eligible=True),
            lambda m: m["holds"].update(publication_authorized=True),
            lambda m: m["holds"].update(deployment_authorized=True),
            lambda m: m["holds"].update(merge_authorized=True),
            lambda m: m["holds"].update(canonical_writes=False),
            lambda m: m["holds"].update(other_hi_production_counties=[]),
            lambda m: m["capabilities"].update(hosted_delivery_certified=True),
            lambda m: m.update(hosted_url="https://example.invalid"),
            lambda m: m["proposed_release"]["assets"].append("package.zip"),
            lambda m: m["proposed_release"].update(assets=["officeholders.json"]),
            lambda m: m.update(applicable_offices=[]),
            lambda m: m["activation_evidence"].update(fresh_live_run=True),
            lambda m: m.update(retained_warnings=[]),
            lambda m: m.update(package_sha256="0" * 64),
            lambda m: m["input_hashes"].update({candidate.production.RECEIPT_PATH: "0" * 64}),
        ]
        for index, edit in enumerate(edits):
            with self.subTest(index=index):
                changed = copy.deepcopy(self.manifest)
                edit(changed)
                with self.assertRaisesRegex(ValueError, "MANIFEST_CONTRACT_DRIFT"):
                    candidate.validate_manifest(changed, self.receipt)

    def test_expiry_is_exclusive_utc_and_future_review_is_rejected(self):
        review = self.manifest["source_review"]
        for accepted in (date(2026, 9, 12), date(2026, 10, 11)):
            candidate.validate_review(review, accepted)
        for rejected in (date(2026, 9, 11), date(2026, 10, 12), date(2027, 1, 1)):
            with self.assertRaisesRegex(ValueError, "SOURCE_REVIEW"):
                candidate.validate_review(review, rejected)
        changed = copy.deepcopy(review)
        changed["expires_on"] = "2026-10-13"
        with self.assertRaisesRegex(ValueError, "SOURCE_REVIEW"):
            candidate.validate_review(changed, date(2026, 9, 12))

    def test_receipt_spec_catalog_and_routing_byte_drift_rejected(self):
        for relative in candidate.INPUT_HASHES:
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" ")
                    with self.assertRaisesRegex(ValueError, "INPUT_HASH_DRIFT"):
                        candidate.verify_inputs(self.root)
                finally:
                    path.write_bytes(original)

    def test_runtime_byte_drift_rejected(self):
        path = self.root / "civic_gps_runtime_parts/part.00"
        raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        with self.assertRaisesRegex(ValueError, "RUNTIME_HASH_DRIFT"):
            candidate.verify_inputs(self.root)

    def test_package_archive_byte_drift_rejected(self):
        path = next((self.root / "previews/ev/maui").glob("*.part*"))
        original = path.read_text()
        path.write_text(("A" if original[0] != "A" else "B") + original[1:])
        with self.assertRaisesRegex(ValueError, "PACKAGE_ARTIFACT_SHA256_MISMATCH"):
            candidate.verify_inputs(self.root)

    def test_explicit_provisional_identity_rejected_without_relabeling_legacy(self):
        catalog = candidate.package_catalog.load_catalog(self.root / "consumers/empowered_vote/package_catalog.v0.1.json")
        entry = next(row for row in catalog["entries"] if row["entry_id"] == candidate.production.ENTRY_ID)
        package = candidate.package_catalog.reconstruct_package(entry, self.root)
        candidate.validate_package(package)
        package["records"]["people"][0]["identity_resolution_status"] = "PROVISIONAL"
        with self.assertRaisesRegex(ValueError, "PUBLIC_IDENTITY_REJECTED"):
            candidate.validate_package(package)

    def test_tampered_retention_and_replacement_zip_rejected_before_extraction(self):
        receipt_path = self.root / candidate.RETENTION
        original = receipt_path.read_bytes()
        changed = candidate.load_json(original)
        changed["source_commit"] = candidate.TARGET
        receipt_path.write_bytes(candidate.encoded(changed))
        with self.assertRaisesRegex(ValueError, "EVIDENCE_RETENTION_CONTRACT_DRIFT"):
            candidate.read_evidence(self.root)
        receipt_path.write_bytes(original)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("live.json", "{}")
            archive.writestr("../../escaped.json", "{}")
        (self.root / candidate.EVIDENCE).write_bytes(base64.b64encode(stream.getvalue()) + b"\n")
        with self.assertRaisesRegex(ValueError, "ORIGINAL_LIVE_ZIP_DRIFT"):
            candidate.read_evidence(self.root)
        self.assertFalse((self.root.parent / "escaped.json").exists())

    def test_output_collision_traversal_and_symlink_escape_rejected(self):
        output = self.root / candidate.ARTIFACTS / "build"
        candidate.write_bundle(self.root, output, self.manifest, {})
        asset = output / "release-assets" / candidate.ASSET
        original = asset.read_bytes()
        with self.assertRaisesRegex(ValueError, "OUTPUT_DESTINATION_COLLISION"):
            candidate.write_bundle(self.root, output, self.manifest, {})
        self.assertEqual(asset.read_bytes(), original)
        for forbidden in (self.root / "data/packages/new", self.root / candidate.ARTIFACTS,
                          self.root / candidate.ARTIFACTS / "../../escape", self.root.parent / "external"):
            with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE"):
                candidate.write_bundle(self.root, forbidden, self.manifest, {})
        link = self.root / candidate.ARTIFACTS / "link"
        link.symlink_to(self.root / "data/packages", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE"):
            candidate.write_bundle(self.root, link / "unexpected", self.manifest, {})

    def test_destination_collision_staleness_and_wrong_target_rejected(self):
        now = datetime(2026, 9, 9, 6, tzinfo=timezone.utc)
        snapshot = {"repository": candidate.REPOSITORY, "complete": True, "proposed_tag": candidate.TAG,
                    "checked_at_utc": now.isoformat(), "target_commit": candidate.TARGET,
                    "target_tree": candidate.TARGET_TREE, "tag_refs": [], "release_tags": []}
        candidate.validate_destination(snapshot, now)
        for key, value in (
            ("tag_refs", ["refs/tags/" + candidate.TAG]), ("release_tags", [candidate.TAG]),
            ("complete", False), ("target_commit", "main"), ("target_tree", "0" * 40),
            ("repository", "Other/Repo"), ("proposed_tag", "tx-legislative-two-office-v0.1"),
            ("checked_at_utc", (now - timedelta(hours=2)).isoformat()),
            ("checked_at_utc", (now + timedelta(seconds=1)).isoformat()),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                candidate.validate_destination({**snapshot, key: value}, now)

    def test_duplicate_json_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            candidate.load_json(b'{"publication_authorized":true,"publication_authorized":false}')

    def test_retained_live_evidence_rejects_unresolved_geography_and_lost_semantics(self):
        original = candidate.read_evidence(self.root)
        edits = [
            lambda d: d.update(validation_mode="SYNTHETIC_FIXTURE"),
            lambda d: d.update(source_commit=candidate.TARGET),
            lambda d: d["negative_control"]["geography"].update(status="FAIL"),
            lambda d: d["negative_control"]["geography"].update(matched_address=""),
            lambda d: d["negative_control"]["geography"].update(jurisdiction_ids=["jur-us-hi-maui-county"]),
            lambda d: d["positive_controls"][0]["representation"].update(residency_area_count=0),
            lambda d: d["positive_controls"][0]["representation"].update(warnings=[]),
            lambda d: d["positive_controls"][0]["candidate_without_opt_in"].update(error="GEOCODER_FAILED"),
            lambda d: d["idempotence"].update(changes_required=1),
            lambda d: d["idempotence"].update(changes=[]),
        ]
        candidate.validate_live(original, self.receipt)
        for index, edit in enumerate(edits):
            changed = copy.deepcopy(original)
            edit(changed)
            with self.subTest(index=index), self.assertRaises(ValueError):
                candidate.validate_live(changed, self.receipt)

    def git_answers(self, overrides=None):
        answers = {
            ("rev-parse", "HEAD"): "a" * 40,
            ("rev-parse", candidate.TARGET + "^{tree}"): candidate.TARGET_TREE,
            ("rev-parse", candidate.CERTIFIED_ACTIVATION + "^{tree}"): candidate.TARGET_TREE,
            ("diff", "--name-only", candidate.TARGET, "a" * 40): "\n".join(sorted(candidate.ALLOWED_PATHS)),
            ("diff", "--name-only", candidate.TARGET, "HEAD"): "\n".join(sorted(candidate.ALLOWED_PATHS)),
            ("diff", "--name-status", "--no-renames", candidate.TARGET, "a" * 40): "\n".join(
                ("M" if p == "tools/ev_maui_activation_diff.py" else "A") + "\t" + p
                for p in sorted(candidate.ALLOWED_PATHS)),
            ("status", "--porcelain", "--untracked-files=no"): "",
        }
        answers.update(overrides or {})
        def call(command, **kwargs):
            result = answers[tuple(command[3:])]
            return result if kwargs.get("text") else result.encode()
        return call

    def test_git_contract_rejects_extra_paths_wrong_checkout_and_existing_file_changes(self):
        with mock.patch.object(candidate.subprocess, "check_output", side_effect=self.git_answers()):
            self.assertEqual(candidate.verify_git(self.root, "a" * 40, candidate.TARGET)["status"], "PASS")
            for head, base in (("main", candidate.TARGET), ("a" * 40, "0" * 40)):
                with self.assertRaisesRegex(ValueError, "GIT_BASE_OR_HEAD_INVALID"):
                    candidate.verify_git(self.root, head, base)
        cases = [
            {("rev-parse", "HEAD"): "b" * 40},
            {("rev-parse", candidate.TARGET + "^{tree}"): "b" * 40},
            {("diff", "--name-only", candidate.TARGET, "a" * 40):
                "\n".join(sorted(candidate.ALLOWED_PATHS | {"consumers/empowered_vote/package_catalog.v0.1.json"}))},
            {("diff", "--name-status", "--no-renames", candidate.TARGET, "a" * 40):
                "\n".join("M\t" + p for p in sorted(candidate.ALLOWED_PATHS))},
            {("status", "--porcelain", "--untracked-files=no"): " M consumers/empowered_vote/maui_countywide_production.py"},
        ]
        for index, overrides in enumerate(cases):
            with self.subTest(index=index), mock.patch.object(candidate.subprocess, "check_output",
                    side_effect=self.git_answers(overrides)), self.assertRaises(ValueError):
                candidate.verify_git(self.root, "a" * 40, candidate.TARGET)

    def test_shared_guard_checks_full_manifest_and_preserves_production_hashes(self):
        from tools import ev_maui_activation_diff as guard
        with mock.patch.object(candidate.subprocess, "check_output", side_effect=self.git_answers()):
            result = guard.verify_diff(self.root, candidate.TARGET, "a" * 40)
            self.assertEqual(result["all_production_entries_preserved"], 6)
            path = self.root / candidate.MANIFEST
            original = path.read_bytes()
            changed = candidate.load_json(original)
            changed["holds"]["publication_authorized"] = True
            path.write_bytes(candidate.encoded(changed))
            with self.assertRaisesRegex(ValueError, "MANIFEST_CONTRACT_DRIFT"):
                guard.verify_diff(self.root, candidate.TARGET, "a" * 40)
            path.write_bytes(original)
            catalog = self.root / "consumers/empowered_vote/package_catalog.v0.1.json"
            catalog.write_bytes(catalog.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "INPUT_HASH_DRIFT"):
                guard.verify_diff(self.root, candidate.TARGET, "a" * 40)


if __name__ == "__main__":
    unittest.main()
