from __future__ import annotations

import copy
import unittest

from adapters.civicpatch.export_representation import ExportError, export_civicpatch_snapshot

J = "ocd-jurisdiction/country:us/state:co/place:synthetic/government"
D = "ocd-division/country:us/state:co/place:synthetic"
ORG = "11111111-1111-4111-8111-111111111111"
POST = "22222222-2222-4222-8222-222222222222"
PERSON = "33333333-3333-4333-8333-333333333333"
MEMBERSHIP = "44444444-4444-4444-8444-444444444444"
EVIDENCE = "55555555-5555-4555-8555-555555555555"
STAMP = "2026-09-25T00:00:00Z"


def fixture():
    return {
        "jurisdiction": {
            "jurisdiction_ocdid": J,
            "data": {"name": "Synthetic City", "url": "https://example.gov"},
        },
        "organizations": [
            {
                "id": ORG,
                "jurisdiction_ocdid": J,
                "name": "City Council",
                "meta_is_default": True,
            }
        ],
        "roles": [
            {"id": "council-member", "label": "Council Member", "status": "active", "is_unique": False}
        ],
        "posts": [
            {
                "id": POST,
                "jurisdiction_ocdid": J,
                "organization_id": ORG,
                "role_id": "council-member",
                "division_ocdid": D,
                "meta_headcount": 3,
                "meta_is_tracked": True,
            }
        ],
        "people": [{"id": PERSON, "name": "Alex Example"}],
        "memberships": [
            {
                "id": MEMBERSHIP,
                "post_id": POST,
                "organization_id": ORG,
                "person_id": PERSON,
                "designations": ["Seat 1"],
                "sources": [{"url": "https://example.gov/council", "note": "official roster"}],
                "opened_at": STAMP,
                "closed_at": None,
            }
        ],
        "source_records": [
            {
                "id": EVIDENCE,
                "jurisdiction_ocdid": J,
                "person_id": PERSON,
                "organization_id": ORG,
                "label": "Council Member",
                "source_url": "https://example.gov/council",
                "created_at": STAMP,
            }
        ],
    }


class CivicPatchExportTests(unittest.TestCase):
    def test_exports_core_graph_and_evidence_without_mutating_source(self):
        source = fixture()
        before = copy.deepcopy(source)
        out = export_civicpatch_snapshot(source, generated_at=STAMP)
        self.assertEqual(out["schema_version"], "1.0.0-draft")
        self.assertEqual(out["jurisdiction"]["jurisdiction_ocdid"], J)
        self.assertEqual(out["organizations"][0]["id"], ORG)
        self.assertEqual(out["posts"][0]["id"], POST)
        self.assertEqual(out["memberships"][0]["person_id"], PERSON)
        self.assertEqual(out["evidence"][0]["id"], EVIDENCE)
        self.assertEqual(out["evidence"][0]["raw_record"]["label"], "Council Member")
        self.assertEqual(source, before)

    def test_publication_does_not_auto_certify(self):
        source = fixture()
        source["jurisdiction"]["published_at"] = STAMP
        out = export_civicpatch_snapshot(source, generated_at=STAMP)
        self.assertEqual(out["certification"]["status"], "uncertified")
        self.assertFalse(out["certification"]["parity_ok"])

    def test_explicit_certification_requires_all_gates(self):
        with self.assertRaisesRegex(ExportError, "certified requires"):
            export_civicpatch_snapshot(
                fixture(), generated_at=STAMP,
                certification={"status": "certified", "raw_complete": True, "normalized_complete": True,
                               "qa_passed": True, "parity_ok": False},
            )
        out = export_civicpatch_snapshot(
            fixture(), generated_at=STAMP,
            certification={"status": "certified", "raw_complete": True, "normalized_complete": True,
                           "qa_passed": True, "parity_ok": True, "verified_at": STAMP,
                           "factory_extension": {"tracker_synced": True, "factory_complete": True}},
        )
        self.assertEqual(out["certification"]["status"], "certified")
        self.assertTrue(out["certification"]["factory_extension"]["tracker_synced"])

    def test_fake_vacancy_person_is_rejected(self):
        source = fixture()
        source["people"][0]["name"] = "Vacant"
        with self.assertRaisesRegex(ExportError, "fake vacancy person"):
            export_civicpatch_snapshot(source, generated_at=STAMP)

    def test_membership_without_source_fails_closed(self):
        source = fixture()
        source["memberships"][0]["sources"] = []
        with self.assertRaisesRegex(ExportError, "membership.sources"):
            export_civicpatch_snapshot(source, generated_at=STAMP)

    def test_open_roster_cannot_exceed_headcount(self):
        source = fixture()
        source["posts"][0]["meta_headcount"] = 1
        other_person = "66666666-6666-4666-8666-666666666666"
        other_membership = "77777777-7777-4777-8777-777777777777"
        source["people"].append({"id": other_person, "name": "Jordan Example"})
        second = copy.deepcopy(source["memberships"][0])
        second.update(id=other_membership, person_id=other_person)
        source["memberships"].append(second)
        with self.assertRaisesRegex(ExportError, "negative derived vacancy"):
            export_civicpatch_snapshot(source, generated_at=STAMP)

    def test_same_membership_id_can_have_multiple_service_periods(self):
        source = fixture()
        source["memberships"][0]["closed_at"] = "2026-01-01T00:00:00Z"
        second = copy.deepcopy(source["memberships"][0])
        second.update(opened_at="2026-02-01T00:00:00Z", closed_at=None)
        source["memberships"].append(second)
        out = export_civicpatch_snapshot(source, generated_at=STAMP)
        self.assertEqual([m["id"] for m in out["memberships"]], [MEMBERSHIP, MEMBERSHIP])
        self.assertNotEqual(out["memberships"][0]["opened_at"], out["memberships"][1]["opened_at"])

    def test_deterministic_when_generated_at_is_supplied(self):
        self.assertEqual(
            export_civicpatch_snapshot(fixture(), generated_at=STAMP),
            export_civicpatch_snapshot(fixture(), generated_at=STAMP),
        )


if __name__ == "__main__":
    unittest.main()
