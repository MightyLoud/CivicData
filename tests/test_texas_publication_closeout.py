"""Offline certification controls for the bounded Texas publication closeout."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.texas_publication_closeout import (
    ASSET_BYTES,
    ASSET_SHA,
    CLOSEOUT_SHA,
    EXECUTION_HEAD_SHA,
    MANIFEST_SHA,
    SNAPSHOT_SHA,
    TARGET_SHA,
    verify,
)


class TexasPublicationCloseoutTests(unittest.TestCase):
    def test_exact_closeout_chain_passes(self):
        result = verify(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["deterministic_sha256"], CLOSEOUT_SHA)
        self.assertEqual(result["release_snapshot_sha256"], SNAPSHOT_SHA)
        self.assertEqual(result["asset_sha256"], ASSET_SHA)
        self.assertEqual(result["asset_bytes"], ASSET_BYTES)
        self.assertEqual(result["manifest_deterministic_sha256"], MANIFEST_SHA)
        self.assertFalse(result["release_mutated"])
        self.assertFalse(result["railway_redeploy"])
        self.assertEqual(result["canonical_writes"], 0)

    def test_closeout_preserves_exact_publication_identity_and_scope(self):
        closeout = json.loads((ROOT / "data/packages/tx/legislative/publication-closeout-v0.1.json").read_text())
        publication = closeout["publication"]
        self.assertEqual(publication["target_sha"], TARGET_SHA)
        self.assertEqual(publication["execution_head_sha"], EXECUTION_HEAD_SHA)
        self.assertEqual(publication["tag"], "tx-legislative-two-office-v0.1")
        self.assertFalse(publication["draft"])
        self.assertFalse(publication["prerelease"])
        self.assertEqual(closeout["scope"]["coverage"], "HOUSE_49_INTERSECTION_SENATE_14")
        self.assertFalse(closeout["scope"]["complete_jurisdiction"])
        self.assertFalse(closeout["scope"]["full_essentials"])
        self.assertFalse(closeout["scope"]["elections"])

    def test_release_snapshot_records_exactly_one_uploaded_manifest_asset(self):
        snapshot = json.loads((ROOT / "data/packages/tx/legislative/publication-release-snapshot-v0.1.json").read_text())
        self.assertEqual(len(snapshot["assets"]), 1)
        asset = snapshot["assets"][0]
        self.assertEqual(asset["name"], "texas-bounded-runtime-release-manifest-v0.1.json")
        self.assertEqual(asset["bytes"], ASSET_BYTES)
        self.assertEqual(asset["sha256"], ASSET_SHA)
        self.assertEqual(asset["state"], "uploaded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
