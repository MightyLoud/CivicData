"""Controls for the bounded Texas release-authorization receipt."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.texas_release_authorization import AUTH_SHA, HOSTED_SHA, READINESS_SHA, verify


class TexasReleaseAuthorizationTests(unittest.TestCase):
    def test_exact_authorization_chain_passes_without_execution_authority(self):
        result = verify(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["deterministic_sha256"], AUTH_SHA)
        self.assertTrue(result["release_authorized"])
        self.assertTrue(result["publication_workflow_authorized"])
        self.assertFalse(result["publication_execution_authorized"])
        self.assertFalse(result["github_release_creation_authorized"])
        self.assertFalse(result["railway_redeploy_authorized"])
        self.assertEqual(result["canonical_writes"], 0)

    def test_evidence_and_readiness_receipts_are_exact(self):
        data = ROOT / "data/packages/tx/legislative"
        hosted = json.loads((data / "post-activation-hosted-evidence-v0.1.json").read_text())
        readiness = json.loads((data / "release-readiness-v0.1.json").read_text())
        self.assertEqual(hosted["deterministic_sha256"], HOSTED_SHA)
        self.assertEqual(readiness["deterministic_sha256"], READINESS_SHA)
        self.assertEqual(readiness["status"], "READY_FOR_RELEASE_AUTHORIZATION")
        self.assertTrue(readiness["runtime_merged"])
        self.assertFalse(readiness["release_authorized"])
        self.assertFalse(readiness["publication_workflow_authorized"])

    def test_release_surface_does_not_publish_source_package(self):
        receipt = json.loads((ROOT / "data/packages/tx/legislative/release-authorization-v0.1.json").read_text())
        publication = receipt["publication_contract"]
        self.assertEqual(publication["surface"], "BOUNDED_RUNTIME_RELEASE")
        self.assertFalse(publication["raw_package_bytes_publishable"])
        self.assertFalse(publication["source_package_publication_eligible"])
        self.assertFalse(publication["registry_publication_eligible"])
        self.assertEqual(publication["release_assets"], ["texas-bounded-runtime-release-manifest-v0.1.json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
