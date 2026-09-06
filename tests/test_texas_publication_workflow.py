"""Structural controls for the manual bounded Texas publication workflow."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/texas-bounded-publication.yml"


class TexasPublicationWorkflowTests(unittest.TestCase):
    def test_publish_job_is_manual_and_separately_locked(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.mode == 'publish'", text)
        self.assertIn("test \"$GITHUB_REF\" = 'refs/heads/main'", text)
        self.assertIn("PUBLISH_TX_HOUSE49_SENATE14", text)
        self.assertIn("publication-execution-authorization-v0.1.json", text)
        self.assertIn("--head-sha \"$GITHUB_SHA\"", text)

    def test_only_manifest_asset_is_published(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("texas-bounded-runtime-release-manifest-v0.1.json", text)
        self.assertIn("gh release create", text)
        self.assertNotIn("Tx_Legislative_Two_Office_v0.1.zip", text)
        self.assertNotIn(".zip.b64.part", text)

    def test_validation_job_has_no_write_permission(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("name: Execute separately authorized bounded publication", text)
        self.assertIn("contents: write", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
