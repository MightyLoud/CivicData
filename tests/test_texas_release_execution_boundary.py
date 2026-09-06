"""Execution-phase control: exact bounded publication execution receipt is present and constrained."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data/packages/tx/legislative/publication-execution-authorization-v0.1.json"
EXPECTED_SHA = "be30edcbbeecb01cfc63b32442ff0567e59d7f839c1ee119f877d613b898c7da"
AUTHORIZED_MAIN = "defefa6d31987187839fa90434b201a287518e34"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class TexasReleaseExecutionBoundaryTests(unittest.TestCase):
    def test_execution_authorization_receipt_is_exact_and_bounded(self):
        self.assertTrue(PATH.is_file())
        receipt = json.loads(PATH.read_text(encoding="utf-8"))
        recorded = receipt["deterministic_sha256"]
        core = dict(receipt)
        core.pop("deterministic_sha256")
        self.assertEqual(hashlib.sha256(canonical(core).encode("utf-8")).hexdigest(), recorded)
        self.assertEqual(recorded, EXPECTED_SHA)
        self.assertEqual(receipt["schema_version"], "texas-bounded-publication-execution/0.2")
        self.assertEqual(receipt["status"], "PUBLICATION_EXECUTION_AUTHORIZED")
        self.assertEqual(receipt["authorization_main_sha"], AUTHORIZED_MAIN)
        self.assertEqual(receipt["publication_target_sha"], AUTHORIZED_MAIN)
        self.assertTrue(receipt["execution_authorized"])
        self.assertTrue(receipt["github_release_creation_authorized"])
        self.assertFalse(receipt["railway_redeploy_authorized"])
        self.assertEqual(receipt["canonical_writes"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
