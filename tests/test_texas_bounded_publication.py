"""Fail-closed tests for bounded Texas publication execution."""
from __future__ import annotations

import hashlib
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

EXECUTION_HEAD = "f" * 40
AUTHORIZATION_MAIN = "defefa6d31987187839fa90434b201a287518e34"
TAG = "tx-legislative-two-office-v0.1"
EXECUTION_PATH = ROOT / "data/packages/tx/legislative/publication-execution-authorization-v0.1.json"


class TexasBoundedPublicationTests(unittest.TestCase):
    def test_missing_execution_authorization_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-execution-authorization.json"
            with self.assertRaisesRegex(PublicationError, "PUBLICATION_EXECUTION_AUTHORIZATION_MISSING"):
                prepare_manifest(repo_root=ROOT, execution_authorization_path=missing,
                                 execution_head_sha=EXECUTION_HEAD)

    def test_governed_execution_receipt_prepares_manifest_without_widening_scope(self):
        manifest = prepare_manifest(
            repo_root=ROOT,
            execution_authorization_path=EXECUTION_PATH,
            execution_head_sha=EXECUTION_HEAD,
        )
        self.assertEqual(manifest["status"], "PUBLICATION_MANIFEST_READY")
        self.assertEqual(manifest["execution_head_sha"], EXECUTION_HEAD)
        self.assertEqual(manifest["target_sha"], AUTHORIZATION_MAIN)
        self.assertNotEqual(manifest["execution_head_sha"], manifest["target_sha"])
        self.assertEqual(manifest["tag"], TAG)
        self.assertEqual(manifest["scope"]["coverage"], "HOUSE_49_INTERSECTION_SENATE_14")
        self.assertFalse(manifest["scope"]["complete_jurisdiction"])
        self.assertFalse(manifest["scope"]["full_essentials"])
        self.assertFalse(manifest["scope"]["elections"])
        self.assertFalse(manifest["publication_boundaries"]["raw_package_bytes_published"])
        self.assertFalse(manifest["publication_boundaries"]["railway_redeploy"])
        self.assertEqual(manifest["publication_boundaries"]["canonical_writes"], 0)

    def test_target_must_equal_authorized_main(self):
        execution = {
            "schema_version": "texas-bounded-publication-execution/0.2",
            "status": "PUBLICATION_EXECUTION_AUTHORIZED",
            "profile_id": "tx_legislative_two_office_v0.1",
            "release_authorization_sha256": AUTH_SHA,
            "authorization_main_sha": AUTHORIZATION_MAIN,
            "publication_target_sha": "e" * 40,
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
            with self.assertRaisesRegex(PublicationError, "PUBLICATION_TARGET_MUST_EQUAL_AUTHORIZED_MAIN"):
                prepare_manifest(repo_root=ROOT, execution_authorization_path=path,
                                 execution_head_sha=EXECUTION_HEAD)


if __name__ == "__main__":
    unittest.main(verbosity=2)
