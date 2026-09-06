"""Fail-closed tests for future bounded Texas publication execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.jurisdiction_package import canonical_json
from tools.texas_bounded_publication import PublicationError, prepare_manifest
from tools.texas_release_authorization import AUTH_SHA

HEAD = "d" * 40
TAG = "tx-legislative-two-office-v0.1"


class TexasBoundedPublicationTests(unittest.TestCase):
    def test_missing_execution_authorization_fails_closed(self):
        with self.assertRaisesRegex(PublicationError, "PUBLICATION_EXECUTION_AUTHORIZATION_MISSING"):
            prepare_manifest(
                repo_root=ROOT,
                execution_authorization_path=ROOT / "data/packages/tx/legislative/publication-execution-authorization-v0.1.json",
                head_sha=HEAD,
            )

    def test_future_exact_execution_receipt_can_prepare_manifest_without_widening_scope(self):
        execution = {
            "schema_version": "texas-bounded-publication-execution/0.1",
            "status": "PUBLICATION_EXECUTION_AUTHORIZED",
            "profile_id": "tx_legislative_two_office_v0.1",
            "release_authorization_sha256": AUTH_SHA,
            "publication_main_sha": HEAD,
            "proposed_tag": TAG,
            "execution_authorized": True,
            "github_release_creation_authorized": True,
            "railway_redeploy_authorized": False,
            "canonical_writes": 0,
        }
        execution["deterministic_sha256"] = hashlib.sha256(canonical_json(execution).encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "execution.json"
            path.write_text(canonical_json(execution), encoding="utf-8")
            manifest = prepare_manifest(repo_root=ROOT, execution_authorization_path=path, head_sha=HEAD)

        self.assertEqual(manifest["status"], "PUBLICATION_MANIFEST_READY")
        self.assertEqual(manifest["target_sha"], HEAD)
        self.assertEqual(manifest["tag"], TAG)
        self.assertEqual(manifest["scope"]["coverage"], "HOUSE_49_INTERSECTION_SENATE_14")
        self.assertFalse(manifest["scope"]["complete_jurisdiction"])
        self.assertFalse(manifest["scope"]["full_essentials"])
        self.assertFalse(manifest["scope"]["elections"])
        self.assertFalse(manifest["publication_boundaries"]["raw_package_bytes_published"])
        self.assertFalse(manifest["publication_boundaries"]["railway_redeploy"])
        self.assertEqual(manifest["publication_boundaries"]["canonical_writes"], 0)

    def test_wrong_main_sha_fails_closed(self):
        execution = {
            "schema_version": "texas-bounded-publication-execution/0.1",
            "status": "PUBLICATION_EXECUTION_AUTHORIZED",
            "profile_id": "tx_legislative_two_office_v0.1",
            "release_authorization_sha256": AUTH_SHA,
            "publication_main_sha": "e" * 40,
            "proposed_tag": TAG,
            "execution_authorized": True,
            "github_release_creation_authorized": True,
            "railway_redeploy_authorized": False,
            "canonical_writes": 0,
        }
        execution["deterministic_sha256"] = hashlib.sha256(canonical_json(execution).encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "execution.json"
            path.write_text(canonical_json(execution), encoding="utf-8")
            with self.assertRaisesRegex(PublicationError, "PUBLICATION_MAIN_SHA_DRIFT"):
                prepare_manifest(repo_root=ROOT, execution_authorization_path=path, head_sha=HEAD)


if __name__ == "__main__":
    unittest.main(verbosity=2)
