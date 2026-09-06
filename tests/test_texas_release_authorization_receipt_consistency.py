"""Cross-check release-authorization receipt hashes and execution boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.jurisdiction_package import canonical_json


class TexasReleaseAuthorizationReceiptConsistencyTests(unittest.TestCase):
    def test_release_authorization_receipt_is_self_consistent(self):
        path = ROOT / "data/packages/tx/legislative/release-authorization-v0.1.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        recorded = receipt.pop("deterministic_sha256")
        actual = hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest()
        self.assertEqual(recorded, actual)
        self.assertEqual(recorded, "7bf9a8ecf9c101e9faee4389f925f469fd1d37934cc1d3dc9bfd6a890989d6de")
        auth = receipt["authorization"]
        self.assertTrue(auth["release_authorized"])
        self.assertTrue(auth["publication_workflow_authorized"])
        self.assertFalse(auth["publication_execution_authorized"])
        self.assertFalse(auth["github_release_creation_authorized"])
        self.assertFalse(auth["railway_redeploy_authorized"])
        self.assertEqual(auth["canonical_writes"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
