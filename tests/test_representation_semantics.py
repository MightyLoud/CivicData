from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.representation_semantics import (
    RepresentationSemanticsError,
    normalize_observation,
    validate_no_fake_vacancy_person,
    vacancy_count,
)

FIXTURE = ROOT / "acceptance" / "representation" / "office_semantics_v0.1.json"


class RepresentationSemanticsAcceptanceTests(unittest.TestCase):
    def test_committed_acceptance_cases(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(payload["contract_version"], "0.1")
        for case in payload["cases"]:
            with self.subTest(case=case["id"]):
                result = normalize_observation(**case["input"])
                expected = case["expect"]
                self.assertEqual(result["role"]["role_id"], expected["role_id"])
                self.assertEqual(result["role"]["label"], expected["role_label"])
                self.assertEqual(result["post"]["division_ocdid"], expected["division_ocdid"])
                self.assertEqual(result["membership"]["label"], expected["membership_label"])
                self.assertEqual(result["membership"]["designations"], expected["designations"])
                self.assertEqual(result["vacancy_count"], expected["vacancy_count"])

    def test_internal_title_never_rekeys_formal_role(self):
        result = normalize_observation(
            formal_role_id="select-board-member",
            formal_role_label="Select Board Member",
            base_division_ocdid="ocd-division/country:us/state:ma/place:millbury",
            source_title="Chair",
            classification="INTERNAL_TITLE",
            seats=5,
            active_memberships=5,
        )
        self.assertEqual(result["role"], {
            "role_id": "select-board-member",
            "label": "Select Board Member",
        })
        self.assertEqual(result["membership"]["label"], "Chair")
        self.assertFalse(result["observation"]["canonical_write"])

    def test_conflicting_formal_title_requires_review(self):
        with self.assertRaisesRegex(
            RepresentationSemanticsError,
            "FORMAL_ROLE_OVERRIDE_REVIEW_REQUIRED",
        ):
            normalize_observation(
                formal_role_id="select-board-member",
                formal_role_label="Select Board Member",
                base_division_ocdid="ocd-division/country:us/state:ma/place:millbury",
                source_title="Council Member",
                classification="FORMAL_ROLE",
            )

    def test_reviewed_label_correction_preserves_role_id(self):
        result = normalize_observation(
            formal_role_id="select-board-member",
            formal_role_label="Selectboard Member",
            base_division_ocdid="ocd-division/country:us/state:ma/place:millbury",
            source_title="Select Board Member",
            classification="FORMAL_ROLE",
            formal_role_override_reviewed=True,
        )
        self.assertEqual(result["role"]["role_id"], "select-board-member")
        self.assertEqual(result["role"]["label"], "Select Board Member")

    def test_geographic_seat_requires_authoritative_division(self):
        with self.assertRaisesRegex(
            RepresentationSemanticsError,
            "GEOGRAPHIC_SEAT_DIVISION_REQUIRED",
        ):
            normalize_observation(
                formal_role_id="council-member",
                formal_role_label="Council Member",
                base_division_ocdid="ocd-division/country:us/state:wa/place:tacoma",
                source_title="Council Member",
                classification="FORMAL_ROLE",
                seat_designation="District 1",
                seat_is_geographic=True,
            )

    def test_nongeographic_seat_stays_membership_designation(self):
        result = normalize_observation(
            formal_role_id="council-member",
            formal_role_label="Council Member",
            base_division_ocdid="ocd-division/country:us/state:tx/place:example",
            source_title="Council Member",
            classification="FORMAL_ROLE",
            seat_designation="Position A",
            seat_is_geographic=False,
        )
        self.assertEqual(
            result["post"]["division_ocdid"],
            "ocd-division/country:us/state:tx/place:example",
        )
        self.assertEqual(result["membership"]["designations"], ["Position A"])

    def test_multi_seat_vacancy_is_capacity_not_person(self):
        self.assertEqual(vacancy_count(5, 4), 1)
        self.assertEqual(vacancy_count(1, 0), 1)
        with self.assertRaisesRegex(
            RepresentationSemanticsError,
            "FAKE_VACANCY_PERSON_FORBIDDEN",
        ):
            validate_no_fake_vacancy_person({
                "person_id": "vacant",
                "canonical_name": "Vacant",
            })

    def test_active_memberships_cannot_exceed_capacity(self):
        with self.assertRaisesRegex(
            RepresentationSemanticsError,
            "ACTIVE_MEMBERSHIP_COUNT_INVALID",
        ):
            vacancy_count(5, 6)

    def test_raw_only_preserves_bad_source_without_canonical_write(self):
        result = normalize_observation(
            formal_role_id="select-board-member",
            formal_role_label="Select Board Member",
            base_division_ocdid="ocd-division/country:us/state:ma/place:millbury",
            source_title="Council Member",
            classification="RAW_ONLY",
            seats=5,
            active_memberships=4,
        )
        self.assertEqual(result["role"]["label"], "Select Board Member")
        self.assertEqual(result["observation"]["source_title"], "Council Member")
        self.assertFalse(result["observation"]["canonical_write"])
        self.assertIsNone(result["membership"]["label"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
