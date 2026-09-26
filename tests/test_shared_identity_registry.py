from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.shared_identity_registry import (
    IdentityRegistryError,
    merge_entities,
    mint_identity_id,
    rename_entity,
    resolve_external_id,
    rollback_merge,
    rollback_split,
    split_entity,
    validate_registry,
)

FIXTURE = ROOT / "acceptance" / "representation" / "shared_identity_registry_v0.1.json"

ORG = "org-11111111-1111-4111-8111-111111111111"
PERSON = "per-22222222-2222-4222-8222-222222222222"
DUPLICATE_PERSON = "per-33333333-3333-4333-8333-333333333333"
SPLIT_PERSON = "per-44444444-4444-4444-8444-444444444444"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SharedIdentityRegistryTests(unittest.TestCase):
    def test_fixture_is_valid_and_cross_system_ids_resolve(self):
        registry = fixture()
        self.assertEqual(validate_registry(registry), [])
        self.assertEqual(
            resolve_external_id(
                registry,
                entity_type="organization",
                system="civicpatch",
                external_id="organizations/example-city-council",
            ),
            ORG,
        )
        self.assertEqual(
            resolve_external_id(
                registry,
                entity_type="organization",
                system="seegov",
                external_id="government/example-city",
            ),
            ORG,
        )
        self.assertEqual(
            resolve_external_id(
                registry,
                entity_type="person",
                system="civicpatch",
                external_id="people/alex-example",
            ),
            PERSON,
        )
        self.assertEqual(
            resolve_external_id(
                registry,
                entity_type="person",
                system="civic_mirror",
                external_id="official/alex-001",
            ),
            PERSON,
        )

    def test_uuid4_minting_is_opaque_and_prefixed(self):
        fixed = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        self.assertEqual(
            mint_identity_id("person", uuid_factory=lambda: fixed),
            "per-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
        self.assertEqual(
            mint_identity_id("organization", uuid_factory=lambda: fixed),
            "org-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )

    def test_non_uuid4_minting_is_rejected(self):
        fixed = uuid.UUID("aaaaaaaa-aaaa-5aaa-8aaa-aaaaaaaaaaaa")
        with self.assertRaisesRegex(IdentityRegistryError, "UUID4_REQUIRED"):
            mint_identity_id("person", uuid_factory=lambda: fixed)

    def test_organization_rename_preserves_identity_and_crosswalks(self):
        registry = fixture()
        renamed = rename_entity(
            registry,
            canonical_id=ORG,
            new_display_name="Example Select Board",
            event_id="evt-org-rename-001",
            reviewed_at="2026-09-25",
            reviewer="fixture-reviewer",
            reason="official body renamed",
            evidence="synthetic acceptance fixture",
        )
        entity = next(x for x in renamed["entities"] if x["canonical_id"] == ORG)
        self.assertEqual(entity["display_name"], "Example Select Board")
        self.assertEqual(
            resolve_external_id(
                renamed,
                entity_type="organization",
                system="civicpatch",
                external_id="organizations/example-city-council",
            ),
            ORG,
        )
        self.assertEqual(renamed["events"][-1]["event_type"], "RENAME")

    def test_person_display_name_change_preserves_identity(self):
        renamed = rename_entity(
            fixture(),
            canonical_id=PERSON,
            new_display_name="Alexandra Example",
            event_id="evt-person-rename-001",
            reviewed_at="2026-09-25",
            reviewer="fixture-reviewer",
            reason="source-supported name change",
            evidence="synthetic acceptance fixture",
        )
        entity = next(x for x in renamed["entities"] if x["canonical_id"] == PERSON)
        self.assertEqual(entity["display_name"], "Alexandra Example")
        self.assertEqual(entity["canonical_id"], PERSON)

    def test_reviewed_person_merge_moves_crosswalk_and_preserves_source_record(self):
        merged = merge_entities(
            fixture(),
            target_id=PERSON,
            source_ids=[DUPLICATE_PERSON],
            event_id="evt-person-merge-001",
            reviewed_at="2026-09-25",
            reviewer="fixture-reviewer",
            reason="independent evidence confirms same human",
            evidence="synthetic acceptance fixture",
        )
        source = next(
            x for x in merged["entities"] if x["canonical_id"] == DUPLICATE_PERSON
        )
        self.assertEqual(source["status"], "MERGED")
        self.assertEqual(source["superseded_by"], PERSON)
        self.assertEqual(
            resolve_external_id(
                merged,
                entity_type="person",
                system="seegov",
                external_id="speaker/alexander-example",
            ),
            PERSON,
        )
        self.assertEqual(merged["events"][-1]["event_type"], "MERGE")

    def test_mistaken_merge_rollback_restores_only_moved_crosswalks(self):
        merged = merge_entities(
            fixture(),
            target_id=PERSON,
            source_ids=[DUPLICATE_PERSON],
            event_id="evt-person-merge-001",
            reviewed_at="2026-09-25",
            reviewer="fixture-reviewer",
            reason="initial identity resolution",
            evidence="synthetic acceptance fixture",
        )
        rolled = rollback_merge(
            merged,
            merge_event_id="evt-person-merge-001",
            event_id="evt-person-merge-rollback-001",
            reviewed_at="2026-09-26",
            reviewer="fixture-reviewer",
            reason="new evidence disproves merge",
            evidence="synthetic rollback evidence",
        )
        source = next(
            x for x in rolled["entities"] if x["canonical_id"] == DUPLICATE_PERSON
        )
        self.assertEqual(source["status"], "ACTIVE")
        self.assertIsNone(source["superseded_by"])
        self.assertEqual(
            resolve_external_id(
                rolled,
                entity_type="person",
                system="seegov",
                external_id="speaker/alexander-example",
            ),
            DUPLICATE_PERSON,
        )
        self.assertEqual(rolled["events"][-1]["event_type"], "ROLLBACK_MERGE")

    def test_merge_requires_review_metadata(self):
        with self.assertRaisesRegex(
            IdentityRegistryError,
            "REVIEW_METADATA_REQUIRED",
        ):
            merge_entities(
                fixture(),
                target_id=PERSON,
                source_ids=[DUPLICATE_PERSON],
                event_id="evt-person-merge-001",
                reviewed_at="",
                reviewer="fixture-reviewer",
                reason="same person",
                evidence="synthetic acceptance fixture",
            )

    def test_cross_entity_type_merge_is_forbidden(self):
        with self.assertRaisesRegex(
            IdentityRegistryError,
            "MERGE_ENTITY_TYPE_MISMATCH",
        ):
            merge_entities(
                fixture(),
                target_id=PERSON,
                source_ids=[ORG],
                event_id="evt-invalid-merge",
                reviewed_at="2026-09-25",
                reviewer="fixture-reviewer",
                reason="synthetic invalid merge",
                evidence="synthetic acceptance fixture",
            )

    def test_split_moves_only_explicit_crosswalks(self):
        split = split_entity(
            fixture(),
            source_id=PERSON,
            new_canonical_id=SPLIT_PERSON,
            new_display_name="Different Alex Example",
            crosswalk_ids=["xw-person-civic-mirror-alex"],
            event_id="evt-person-split-001",
            reviewed_at="2026-09-26",
            reviewer="fixture-reviewer",
            reason="evidence shows records refer to different people",
            evidence="synthetic split evidence",
            created_at="2026-09-26",
        )
        self.assertEqual(
            resolve_external_id(
                split,
                entity_type="person",
                system="civic_mirror",
                external_id="official/alex-001",
            ),
            SPLIT_PERSON,
        )
        self.assertEqual(
            resolve_external_id(
                split,
                entity_type="person",
                system="civicpatch",
                external_id="people/alex-example",
            ),
            PERSON,
        )

    def test_split_rollback_restores_crosswalk_and_retires_split_identity(self):
        split = split_entity(
            fixture(),
            source_id=PERSON,
            new_canonical_id=SPLIT_PERSON,
            new_display_name="Different Alex Example",
            crosswalk_ids=["xw-person-civic-mirror-alex"],
            event_id="evt-person-split-001",
            reviewed_at="2026-09-26",
            reviewer="fixture-reviewer",
            reason="initial split",
            evidence="synthetic split evidence",
            created_at="2026-09-26",
        )
        rolled = rollback_split(
            split,
            split_event_id="evt-person-split-001",
            event_id="evt-person-split-rollback-001",
            reviewed_at="2026-09-27",
            reviewer="fixture-reviewer",
            reason="new evidence reunifies identity",
            evidence="synthetic rollback evidence",
        )
        self.assertEqual(
            resolve_external_id(
                rolled,
                entity_type="person",
                system="civic_mirror",
                external_id="official/alex-001",
            ),
            PERSON,
        )
        split_entity_row = next(
            x for x in rolled["entities"] if x["canonical_id"] == SPLIT_PERSON
        )
        self.assertEqual(split_entity_row["status"], "RETIRED")

    def test_duplicate_active_external_mapping_fails_validation(self):
        registry = fixture()
        registry["crosswalks"].append(
            {
                "crosswalk_id": "xw-conflict",
                "entity_type": "person",
                "canonical_id": DUPLICATE_PERSON,
                "system": "civicpatch",
                "external_id": "people/alex-example",
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-25",
                "source": "synthetic invalid fixture",
            }
        )
        self.assertIn("ACTIVE_EXTERNAL_ID_AMBIGUOUS", validate_registry(registry))

    def test_crosswalk_type_mismatch_fails_validation(self):
        registry = fixture()
        registry["crosswalks"][0]["entity_type"] = "person"
        self.assertIn("CROSSWALK_ENTITY_TYPE_MISMATCH", validate_registry(registry))


if __name__ == "__main__":
    unittest.main(verbosity=2)
