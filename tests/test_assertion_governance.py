from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.assertion_governance import (
    AssertionGovernanceError,
    DEFAULT_AUTHORITY_MATRIX,
    certify_snapshot,
    promote_accepted_assertion,
    review_assertion,
    validate_assertion,
    validate_certification,
)

FIXTURE = ROOT / "acceptance" / "representation" / "partner_assertion_v0.1.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class AssertionGovernanceTests(unittest.TestCase):
    def test_fixture_assertions_are_valid_proposals(self):
        payload = fixture()
        self.assertEqual(payload["authority_matrix"], DEFAULT_AUTHORITY_MATRIX)
        for assertion in payload["assertions"].values():
            with self.subTest(assertion=assertion["assertion_id"]):
                self.assertEqual(validate_assertion(assertion), [])
                self.assertEqual(assertion["review_status"], "proposed")

    def test_partner_end_date_correction_is_reviewed_then_promoted_copy_on_write(self):
        payload = fixture()
        base = payload["base_snapshot"]
        assertion = payload["assertions"]["end_date_correction"]
        accepted = review_assertion(
            assertion,
            outcome="accepted",
            reviewer="representation-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-25T22:30:00-06:00",
            reason="official evidence supports membership end date",
        )
        before = deepcopy(base)
        promoted = promote_accepted_assertion(
            base,
            accepted,
            new_snapshot_id="snapshot-example-002",
            promoted_at="2026-09-25T22:31:00-06:00",
        )

        self.assertEqual(base, before)
        self.assertIsNone(base["memberships"][0]["end_date"])
        self.assertEqual(promoted["memberships"][0]["end_date"], "2026-09-01")
        self.assertEqual(promoted["snapshot_id"], "snapshot-example-002")
        self.assertEqual(
            promoted["assertion_ids_applied"],
            ["assertion-civic-mirror-end-date-001"],
        )
        self.assertEqual(promoted["certification"]["status"], "uncertified")
        self.assertFalse(promoted["certification"]["qa_passed"])
        self.assertFalse(promoted["certification"]["parity_ok"])

    def test_wrong_domain_cannot_accept_assertion(self):
        assertion = fixture()["assertions"]["end_date_correction"]
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "REVIEW_AUTHORITY_MISMATCH",
        ):
            review_assertion(
                assertion,
                outcome="accepted",
                reviewer="wrong-domain-reviewer",
                reviewer_authority="openstates_jurisdictions",
                reviewed_at="2026-09-25T22:30:00-06:00",
                reason="wrong authority",
            )

    def test_jurisdiction_assertion_requires_openstates_authority(self):
        assertion = deepcopy(fixture()["assertions"]["end_date_correction"])
        assertion.update(
            assertion_id="assertion-jurisdiction-name-001",
            subject_type="jurisdiction",
            subject_id="jurisdiction-example",
            field_path="name",
            value="Example Town",
        )
        accepted = review_assertion(
            assertion,
            outcome="accepted",
            reviewer="jurisdiction-reviewer",
            reviewer_authority="openstates_jurisdictions",
            reviewed_at="2026-09-25T22:30:00-06:00",
            reason="governed jurisdiction review",
        )
        self.assertEqual(accepted["review_status"], "accepted")

    def test_rejected_assertion_remains_in_history_and_cannot_promote(self):
        payload = fixture()
        rejected = review_assertion(
            payload["assertions"]["rejected_title_claim"],
            outcome="rejected",
            reviewer="representation-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-25T22:35:00-06:00",
            reason="title conflicts with formal office semantics",
        )
        self.assertEqual(rejected["review_status"], "rejected")
        self.assertEqual(len(rejected["review_history"]), 1)
        self.assertEqual(rejected["review_history"][0]["outcome"], "rejected")
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "ASSERTION_NOT_ACCEPTED",
        ):
            promote_accepted_assertion(
                payload["base_snapshot"],
                rejected,
                new_snapshot_id="snapshot-should-not-exist",
                promoted_at="2026-09-25T22:36:00-06:00",
            )

    def test_identity_conflict_remains_fail_closed(self):
        payload = fixture()
        conflicted = review_assertion(
            payload["assertions"]["identity_conflict"],
            outcome="identity_conflict",
            reviewer="representation-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-25T22:40:00-06:00",
            reason="person identity unresolved",
        )
        self.assertEqual(conflicted["review_status"], "identity_conflict")
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "ASSERTION_NOT_ACCEPTED",
        ):
            promote_accepted_assertion(
                payload["base_snapshot"],
                conflicted,
                new_snapshot_id="snapshot-conflict",
                promoted_at="2026-09-25T22:41:00-06:00",
            )

    def test_needs_evidence_and_scope_conflict_cannot_promote(self):
        payload = fixture()
        for outcome in ("needs_evidence", "scope_conflict"):
            with self.subTest(outcome=outcome):
                reviewed = review_assertion(
                    payload["assertions"]["end_date_correction"],
                    outcome=outcome,
                    reviewer="representation-reviewer",
                    reviewer_authority="civicdata_representation",
                    reviewed_at="2026-09-25T22:45:00-06:00",
                    reason="synthetic review outcome",
                )
                with self.assertRaisesRegex(
                    AssertionGovernanceError,
                    "ASSERTION_NOT_ACCEPTED",
                ):
                    promote_accepted_assertion(
                        payload["base_snapshot"],
                        reviewed,
                        new_snapshot_id="snapshot-not-promoted-" + outcome,
                        promoted_at="2026-09-25T22:46:00-06:00",
                    )

    def test_stale_base_snapshot_fails_closed(self):
        payload = fixture()
        accepted = review_assertion(
            payload["assertions"]["end_date_correction"],
            outcome="accepted",
            reviewer="representation-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-25T22:30:00-06:00",
            reason="supported",
        )
        stale = deepcopy(payload["base_snapshot"])
        stale["snapshot_id"] = "snapshot-newer-than-assertion"
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "BASE_SNAPSHOT_STALE",
        ):
            promote_accepted_assertion(
                stale,
                accepted,
                new_snapshot_id="snapshot-next",
                promoted_at="2026-09-25T22:31:00-06:00",
            )

    def test_identity_fields_cannot_be_overwritten_via_assertion(self):
        payload = fixture()
        assertion = deepcopy(payload["assertions"]["end_date_correction"])
        assertion["field_path"] = "person_id"
        assertion["value"] = "per-33333333-3333-4333-8333-333333333333"
        accepted = review_assertion(
            assertion,
            outcome="accepted",
            reviewer="representation-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-25T22:30:00-06:00",
            reason="synthetic identity overwrite attempt",
        )
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "IDENTITY_FIELD_WRITE_FORBIDDEN",
        ):
            promote_accepted_assertion(
                payload["base_snapshot"],
                accepted,
                new_snapshot_id="snapshot-forbidden",
                promoted_at="2026-09-25T22:31:00-06:00",
            )

    def test_new_snapshot_requires_recertification_and_all_gates(self):
        payload = fixture()
        accepted = review_assertion(
            payload["assertions"]["end_date_correction"],
            outcome="accepted",
            reviewer="representation-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-25T22:30:00-06:00",
            reason="supported",
        )
        promoted = promote_accepted_assertion(
            payload["base_snapshot"],
            accepted,
            new_snapshot_id="snapshot-example-002",
            promoted_at="2026-09-25T22:31:00-06:00",
        )
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "CERTIFICATION_GATES_INCOMPLETE",
        ):
            certify_snapshot(
                promoted,
                raw_complete=True,
                normalized_complete=True,
                qa_passed=True,
                parity_ok=False,
                verified_at="2026-09-25T23:00:00-06:00",
                reviewer="certification-reviewer",
                reviewer_authority="civicdata_certification",
                reason="parity has not passed",
            )

        certified = certify_snapshot(
            promoted,
            raw_complete=True,
            normalized_complete=True,
            qa_passed=True,
            parity_ok=True,
            verified_at="2026-09-25T23:05:00-06:00",
            reviewer="certification-reviewer",
            reviewer_authority="civicdata_certification",
            reason="all shared certification gates passed",
        )
        self.assertEqual(validate_certification(certified["certification"]), [])
        self.assertEqual(certified["certification"]["status"], "certified")

    def test_tracker_sync_is_not_shared_certification_gate(self):
        payload = fixture()
        self.assertFalse(payload["base_snapshot"]["ops"]["tracker_synced"])
        certified = certify_snapshot(
            payload["base_snapshot"],
            raw_complete=True,
            normalized_complete=True,
            qa_passed=True,
            parity_ok=True,
            verified_at="2026-09-25T23:05:00-06:00",
            reviewer="certification-reviewer",
            reviewer_authority="civicdata_certification",
            reason="semantic certification independent of ops tracker",
        )
        self.assertEqual(certified["certification"]["status"], "certified")
        self.assertFalse(certified["ops"]["tracker_synced"])

    def test_certification_requires_certification_authority(self):
        with self.assertRaisesRegex(
            AssertionGovernanceError,
            "CERTIFICATION_AUTHORITY_MISMATCH",
        ):
            certify_snapshot(
                fixture()["base_snapshot"],
                raw_complete=True,
                normalized_complete=True,
                qa_passed=True,
                parity_ok=True,
                verified_at="2026-09-25T23:05:00-06:00",
                reviewer="representation-reviewer",
                reviewer_authority="civicdata_representation",
                reason="wrong authority",
            )

    def test_assertion_requires_evidence(self):
        assertion = deepcopy(fixture()["assertions"]["end_date_correction"])
        assertion["evidence"] = []
        self.assertIn("EVIDENCE_REQUIRED", validate_assertion(assertion))


if __name__ == "__main__":
    unittest.main(verbosity=2)
