"""Bound evidence, policy, UTC boundaries and read-only reporting regressions."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from consumers.empowered_vote import countywide_production as kauai
from consumers.empowered_vote import maui_countywide_production as maui
from tools import source_review_freshness as freshness

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date.fromisoformat(json.loads((ROOT / maui.REVIEW_REFERENCE["path"]).read_text())["reviewed_on"])


class FreshnessTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        paths = (freshness.CATALOG_PATH, kauai.RECEIPT_PATH, maui.RECEIPT_PATH,
            maui.REVIEW_REFERENCE["path"], maui.candidate.SOURCE_CORRECTION["path"])
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def read(self, relative):
        return json.loads((self.root / relative).read_text())

    def write(self, relative, value):
        path = self.root / relative
        path.write_text(json.dumps(value, indent=2) + "\n")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def rebind_receipt(self, entry_id, relative, update):
        receipt = self.read(relative)
        update(receipt)
        sha = self.write(relative, receipt)
        catalog = self.read(freshness.CATALOG_PATH)
        entry = next(r for r in catalog["entries"] if r["entry_id"] == entry_id)
        entry["countywide_profile"]["acceptance_receipt"]["sha256"] = sha
        self.write(freshness.CATALOG_PATH, catalog)

    def report(self, today=AS_OF):
        return freshness.build_report(self.root, today=today)

    def row(self, entry_id, today=AS_OF):
        return next(r for r in self.report(today)["reviews"] if r["entry_id"] == entry_id)

    def dates(self, entry_id):
        if entry_id == maui.ENTRY_ID:
            review = self.read(maui.REVIEW_REFERENCE["path"])
        else:
            review = self.read(kauai.RECEIPT_PATH)["source_review"]
        return date.fromisoformat(review["reviewed_on"]), date.fromisoformat(review["expires_on"])

    def isolate_maui(self):
        catalog = self.read(freshness.CATALOG_PATH)
        catalog["entries"] = [r for r in catalog["entries"] if r["entry_id"] != kauai.ENTRY_ID]
        self.write(freshness.CATALOG_PATH, catalog)

    def test_current_receipts_verify_and_uncovered_entries_are_explicit(self):
        report = self.report()
        self.assertEqual(report["scope"], freshness.SCOPE)
        self.assertEqual(report["review_count"], 2)
        self.assertEqual(len(report["not_covered_entry_ids"]), 4)
        self.assertEqual(report["canonical_writes"], 0)
        rows = {}
        for entry_id in (maui.ENTRY_ID, kauai.ENTRY_ID):
            reviewed, expires = self.dates(entry_id)
            row = self.row(entry_id, reviewed)
            rows[entry_id] = row
            self.assertEqual(row["days_remaining"], (expires - reviewed).days)
            self.assertNotIn(row["status"], freshness.FAIL_STATES)
            self.assertTrue(row["contract_verified"])
            for reference in row["bound_references"].values():
                self.assertEqual(hashlib.sha256((self.root / reference["path"]).read_bytes()).hexdigest(),
                    reference["sha256"])
        self.assertEqual(rows[maui.ENTRY_ID]["review_storage"], "SEPARATE_BOUND_RECEIPT")
        self.assertEqual(rows[kauai.ENTRY_ID]["review_storage"], "EMBEDDED_IN_BOUND_ACCEPTANCE")

    def test_thresholds_and_exclusive_expiry_for_both_profiles(self):
        for entry_id in (maui.ENTRY_ID, kauai.ENTRY_ID):
            expires = date.fromisoformat(self.row(entry_id)["expires_on"])
            for days, status in ((15, "CURRENT"), (14, "EXPIRING_14_DAYS"),
                    (8, "EXPIRING_14_DAYS"), (7, "EXPIRING_7_DAYS"),
                    (1, "EXPIRING_7_DAYS"), (0, "EXPIRED"), (-1, "EXPIRED")):
                with self.subTest(entry=entry_id, days=days):
                    row = self.row(entry_id, expires - timedelta(days=days))
                    self.assertEqual(row["status"], status, row)
                    self.assertEqual(row["days_remaining"], days)
                    self.assertTrue(row["contract_verified"])

    def test_future_review_is_not_current(self):
        row = self.row(maui.ENTRY_ID, AS_OF - timedelta(days=1))
        self.assertEqual(row["status"], "NOT_YET_VALID")
        self.assertEqual(self.report(AS_OF - timedelta(days=1))["status"], "FAIL")

    def test_report_aggregates_warnings_without_failing_cli(self):
        self.isolate_maui()
        expires = self.dates(maui.ENTRY_ID)[1]
        for current in (expires - timedelta(days=14), expires - timedelta(days=7)):
            with self.subTest(current=current):
                self.assertEqual(self.report(current)["status"], "WARN")
                out = io.StringIO()
                with redirect_stdout(out):
                    code = freshness.main(["--repo-root", str(self.root), "--as-of", current.isoformat()])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out.getvalue())["status"], "WARN")

    def test_expired_cli_returns_failure_and_emits_parseable_json(self):
        expires = self.dates(maui.ENTRY_ID)[1]
        out = io.StringIO()
        with redirect_stdout(out):
            code = freshness.main(["--repo-root", str(self.root), "--as-of", expires.isoformat()])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "FAIL")

    def test_acceptance_hash_drift_does_not_hide_other_review(self):
        path = self.root / kauai.RECEIPT_PATH
        path.write_bytes(path.read_bytes() + b" ")
        report = self.report()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(self.row(kauai.ENTRY_ID)["error"], "SOURCE_FRESHNESS_HASH_DRIFT")
        self.assertEqual(self.row(maui.ENTRY_ID)["status"], "CURRENT")

    def test_separate_review_hash_drift_is_rejected(self):
        path = self.root / maui.REVIEW_REFERENCE["path"]
        path.write_bytes(path.read_bytes() + b" ")
        row = self.row(maui.ENTRY_ID)
        self.assertEqual(row["error"], "SOURCE_FRESHNESS_HASH_DRIFT")
        self.assertFalse(row["contract_verified"])

    def test_missing_or_malformed_evidence_is_invalid(self):
        relative = kauai.RECEIPT_PATH
        path = self.root / relative
        original = path.read_bytes()
        for raw in (None, b"{broken", b"[]", b"\xff"):
            with self.subTest(raw=raw):
                path.write_bytes(original)
                if raw is None:
                    path.unlink()
                else:
                    path.write_bytes(raw)
                    catalog = self.read(freshness.CATALOG_PATH)
                    entry = next(r for r in catalog["entries"] if r["entry_id"] == kauai.ENTRY_ID)
                    entry["countywide_profile"]["acceptance_receipt"]["sha256"] = hashlib.sha256(raw).hexdigest()
                    self.write(freshness.CATALOG_PATH, catalog)
                self.assertEqual(self.row(kauai.ENTRY_ID)["status"], "INVALID")

    def test_rehashed_invalid_evidence_is_not_misreported_as_expired(self):
        expires = self.dates(kauai.ENTRY_ID)[1]
        self.rebind_receipt(kauai.ENTRY_ID, kauai.RECEIPT_PATH,
            lambda r: r["source_review"]["sources"][0].update(authority="UNVERIFIED"))
        row = self.row(kauai.ENTRY_ID, expires + timedelta(days=1))
        self.assertEqual(row["status"], "INVALID")
        self.assertEqual(row["error"], "COUNTYWIDE_PRODUCTION_SOURCE_REVIEW_INVALID")

    def test_maui_thirty_day_policy_cannot_be_extended(self):
        review = self.read(maui.REVIEW_REFERENCE["path"])
        review["expires_on"] = (date.fromisoformat(review["reviewed_on"]) + timedelta(days=31)).isoformat()
        sha = self.write(maui.REVIEW_REFERENCE["path"], review)
        reference = {"path": maui.REVIEW_REFERENCE["path"], "sha256": sha}
        self.rebind_receipt(maui.ENTRY_ID, maui.RECEIPT_PATH,
            lambda r: r.update(source_review=reference))
        with patch.object(maui, "REVIEW_REFERENCE", reference):
            row = self.row(maui.ENTRY_ID)
        self.assertEqual(row["status"], "INVALID")
        self.assertEqual(row["error"], "MAUI_PRODUCTION_SOURCE_REVIEW_INVALID")

    def test_kauai_transition_cutoff_cannot_be_extended(self):
        self.rebind_receipt(kauai.ENTRY_ID, kauai.RECEIPT_PATH,
            lambda r: r["source_review"].update(expires_on="2026-12-02"))
        row = self.row(kauai.ENTRY_ID)
        self.assertEqual(row["status"], "INVALID")
        self.assertEqual(row["error"], "COUNTYWIDE_PRODUCTION_SOURCE_REVIEW_EXPIRED_OR_FUTURE")

    def test_rehashed_acceptance_cannot_grant_publication_authority(self):
        self.rebind_receipt(kauai.ENTRY_ID, kauai.RECEIPT_PATH,
            lambda r: r.update(publication_authorized=True))
        self.assertEqual(self.row(kauai.ENTRY_ID)["error"], "COUNTYWIDE_PRODUCTION_RECEIPT_CONTRACT_INVALID")

    def test_noncanonical_or_reversed_dates_are_invalid(self):
        for reviewed, expires in (("20260909", "2026-12-01"), ("2026-09-09", "2026-09-08"),
                (None, "2026-12-01"), ("2026-09-09", "not a date")):
            with self.subTest(reviewed=reviewed, expires=expires):
                self.rebind_receipt(kauai.ENTRY_ID, kauai.RECEIPT_PATH,
                    lambda r: r["source_review"].update(reviewed_on=reviewed, expires_on=expires))
                self.assertEqual(self.row(kauai.ENTRY_ID)["status"], "INVALID")

    def test_bound_paths_cannot_escape_root_through_symlinks(self):
        with tempfile.TemporaryDirectory() as outside:
            path = self.root / kauai.RECEIPT_PATH
            external = Path(outside) / "receipt.json"
            external.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(external)
            row = self.row(kauai.ENTRY_ID)
            self.assertEqual(row["error"], "SOURCE_FRESHNESS_PATH_INVALID")

    def test_missing_malformed_and_duplicate_catalogs_fail(self):
        path = self.root / freshness.CATALOG_PATH
        original = path.read_bytes()
        for raw in (None, b"{", b"[]"):
            with self.subTest(raw=raw):
                if raw is None:
                    path.unlink()
                else:
                    path.write_bytes(raw)
                self.assertEqual(self.report()["status"], "FAIL")
                path.write_bytes(original)
        catalog = self.read(freshness.CATALOG_PATH)
        catalog["entries"].append(catalog["entries"][0])
        self.write(freshness.CATALOG_PATH, catalog)
        self.assertEqual(self.report()["error"], "PACKAGE_CATALOG_ENTRY_ID_DUPLICATE")

    def test_empty_covered_inventory_is_not_an_empty_pass(self):
        catalog = self.read(freshness.CATALOG_PATH)
        catalog["entries"] = [r for r in catalog["entries"] if "countywide_profile" not in r]
        self.write(freshness.CATALOG_PATH, catalog)
        self.assertEqual(self.report()["error"], "SOURCE_FRESHNESS_INVENTORY_EMPTY")

    def test_default_clock_is_utc_and_datetime_override_is_rejected(self):
        with patch.object(freshness, "datetime") as clock:
            clock.now.return_value.date.return_value = AS_OF
            report = freshness.build_report(self.root)
            clock.now.assert_called_once_with(timezone.utc)
            self.assertEqual(report["as_of_utc"], AS_OF.isoformat())
        with self.assertRaisesRegex(ValueError, "AS_OF_DATE_INVALID"):
            freshness.build_report(self.root, today=datetime(2026, 10, 12))

    def test_report_is_deterministic_and_does_not_write_evidence(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        first = self.report()
        self.assertEqual(first, self.report())
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_root_override_and_cli_work_outside_repo(self):
        self.isolate_maui()
        result = subprocess.run([sys.executable, str(ROOT / "tools/source_review_freshness.py"),
            "--repo-root", str(self.root), "--as-of", AS_OF.isoformat()], cwd=self.root,
            text=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["review_count"], 1)

    def test_github_summary_and_annotations_leave_json_stdout_parseable(self):
        self.isolate_maui()
        expires = self.dates(maui.ENTRY_ID)[1]
        summary = self.root / "summary.md"
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}), redirect_stdout(out), redirect_stderr(err):
            code = freshness.main(["--repo-root", str(self.root), "--as-of", (expires - timedelta(days=7)).isoformat(), "--github-actions"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "WARN")
        self.assertIn("::warning::hi-maui", err.getvalue())
        self.assertIn("EXPIRING_7_DAYS", summary.read_text())
        self.assertIn("Not covered:", summary.read_text())
        with redirect_stderr(err):
            freshness.emit_github_actions(self.report(expires))
        self.assertIn("::error::hi-maui", err.getvalue())

    def test_untrusted_text_cannot_inject_github_commands_or_markdown_cells(self):
        self.isolate_maui()
        report = self.report(self.dates(maui.ENTRY_ID)[1] - timedelta(days=7))
        row = next(r for r in report["reviews"] if r["entry_id"] == maui.ENTRY_ID)
        row["entry_id"] = "x%\n::notice::injected|<script>"
        err = io.StringIO()
        with redirect_stderr(err):
            freshness.emit_github_actions(report)
        self.assertEqual(len(err.getvalue().splitlines()), 1)
        self.assertIn("x%25%0A::notice::", err.getvalue())
        markdown = freshness.render_markdown(report)
        self.assertNotIn("<script>", markdown)
        self.assertIn("\\|&lt;script&gt;", markdown)


if __name__ == "__main__":
    unittest.main()
