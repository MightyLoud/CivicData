"""Structural controls for the bounded Texas publication workflow."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/texas-bounded-publication.yml"


class TexasPublicationWorkflowTests(unittest.TestCase):
    def test_publish_job_requires_main_and_governed_execution_marker(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'push'", text)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn("[execute-tx-publication]", text)
        self.assertNotIn("github.event_name == 'pull_request' &&", text)
        self.assertIn("publication-execution-authorization-v0.1.json", text)
        self.assertIn("--execution-head-sha \"$GITHUB_SHA\"", text)

    def test_only_manifest_asset_is_published_to_governed_target(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("texas-bounded-runtime-release-manifest-v0.1.json", text)
        self.assertIn("gh release create", text)
        self.assertIn("--target \"$TARGET\"", text)
        self.assertNotIn("Tx_Legislative_Two_Office_v0.1.zip", text)
        self.assertNotIn(".zip.b64.part", text)

    def test_validation_job_has_no_write_permission_and_execution_has_write_permission(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("name: Execute separately authorized bounded publication", text)
        self.assertIn("contents: write", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
