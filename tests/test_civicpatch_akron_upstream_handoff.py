from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.civicpatch.build_akron_upstream_handoff import (
    BASE,
    CANDIDATE,
    CHECKLIST_NAME,
    METADATA_NAME,
    PATCH_NAME,
    PR_BODY_NAME,
    build_handoff,
)

HANDOFF = ROOT / "candidates" / "civicpatch" / "akron_v0.1" / "upstream_handoff"


class AkronCivicPatchUpstreamHandoffTests(unittest.TestCase):
    def test_committed_handoff_matches_deterministic_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build_handoff(out)
            for name in (PATCH_NAME, PR_BODY_NAME, CHECKLIST_NAME):
                with self.subTest(name=name):
                    self.assertEqual(
                        (out / name).read_bytes(),
                        (HANDOFF / name).read_bytes(),
                    )
            generated_meta = json.loads((out / METADATA_NAME).read_text(encoding="utf-8"))
            committed_meta = json.loads((HANDOFF / METADATA_NAME).read_text(encoding="utf-8"))
            self.assertEqual(generated_meta, committed_meta)

    def test_full_replacement_patch_reconstructs_both_files_exactly(self):
        patch = (HANDOFF / PATCH_NAME).read_text(encoding="utf-8")
        lines = patch.splitlines()
        self.assertEqual(
            lines[:3],
            [
                "diff --git a/data/co/local/place_akron.yml b/data/co/local/place_akron.yml",
                "--- a/data/co/local/place_akron.yml",
                "+++ b/data/co/local/place_akron.yml",
            ],
        )
        self.assertTrue(lines[3].startswith("@@ -1,"))
        body = lines[4:]
        removed = [line[1:] for line in body if line.startswith("-")]
        added = [line[1:] for line in body if line.startswith("+")]
        self.assertEqual("\n".join(removed) + "\n", BASE.read_text(encoding="utf-8"))
        self.assertEqual("\n".join(added) + "\n", CANDIDATE.read_text(encoding="utf-8"))

    def test_handoff_is_pinned_and_not_submitted(self):
        metadata = json.loads((HANDOFF / METADATA_NAME).read_text(encoding="utf-8"))
        self.assertEqual(metadata["upstream"]["repository"], "CivicPatch/open-data")
        self.assertEqual(
            metadata["upstream"]["commit"],
            "69331c2b0d97e13695dab07ec1d6a969c99a3e4d",
        )
        self.assertEqual(
            metadata["upstream"]["target_blob_sha"],
            "3c335cac8e5d07fb18b67db70aa12c7dc1d7a7d7",
        )
        self.assertEqual(
            metadata["upstream"]["target_path"],
            "data/co/local/place_akron.yml",
        )
        self.assertFalse(metadata["upstream"]["connected_account_push_permission"])
        self.assertFalse(metadata["submission"]["upstream_write_authorized"])
        self.assertTrue(metadata["submission"]["requires_fork_or_maintainer_branch"])
        self.assertTrue(metadata["submission"]["pr_not_submitted"])

    def test_pr_body_contains_identity_role_tenure_and_source_review_notes(self):
        body = (HANDOFF / PR_BODY_NAME).read_text(encoding="utf-8")
        for required in (
            "Braden Brent",
            "Crystann Benson",
            "Jared Jefferson",
            "formal role as `trustee`",
            "start_date",
            "end_date",
            "Brandon Hill",
            "Ariella Gonzales-Vondy",
            "David Kembel",
            "Jennifer Hansen",
            "https://www.townofakron.com/172/Board-of-Trustees",
            "0-0-0-127",
            "0-0-0-134",
        ):
            with self.subTest(required=required):
                self.assertIn(required, body)

    def test_checklist_includes_actual_civicpatch_validation_command(self):
        checklist = (HANDOFF / CHECKLIST_NAME).read_text(encoding="utf-8")
        self.assertIn(
            "uv run python scripts/github_actions/validate_jurisdiction.py",
            checklist,
        )
        self.assertIn(
            "ocd-jurisdiction/country:us/state:co/place:akron/government",
            checklist,
        )
        self.assertIn("Review or remint the four proposed IDs", checklist)
        self.assertIn("Only then merge/publish upstream", checklist)


if __name__ == "__main__":
    unittest.main(verbosity=2)
