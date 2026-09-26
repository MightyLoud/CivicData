from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ocdid_registry_validation import (
    OCDIDRegistryError,
    RegistrySnapshot,
    validate_civicpatch_identity,
)

FIXTURE = ROOT / "acceptance" / "representation" / "ocdid_registry_v0.1.json"


def load_fixture():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload, RegistrySnapshot.from_dict(payload["registry"])


class OCDIDRegistryAcceptanceTests(unittest.TestCase):
    def test_committed_acceptance_cases(self):
        payload, registry = load_fixture()
        self.assertEqual(payload["contract_version"], "0.1")
        for case in payload["cases"]:
            with self.subTest(case=case["id"]):
                result = validate_civicpatch_identity(
                    **case["input"],
                    registry=registry,
                    reviewed_mappings=payload["reviewed_mappings"],
                )
                for key, value in case["expected"].items():
                    self.assertEqual(result[key], value)

    def test_valid_ids_pass_unchanged(self):
        _, registry = load_fixture()
        jurisdiction = "ocd-jurisdiction/country:us/state:tx/place:arlington/government"
        division = "ocd-division/country:us/state:tx/place:arlington/council_district:5"
        result = validate_civicpatch_identity(
            jurisdiction_ocdid=jurisdiction,
            division_ocdid=division,
            registry=registry,
        )
        self.assertEqual(result["jurisdiction_ocdid"], jurisdiction)
        self.assertEqual(result["division_ocdid"], division)
        self.assertEqual(result["registry_status"], "PUBLISHED_LOOKUP")

    def test_legacy_millbury_fails_without_reviewed_mapping(self):
        _, registry = load_fixture()
        with self.assertRaisesRegex(OCDIDRegistryError, "DIVISION_NOT_IN_REGISTRY"):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:ma/place:millbury/government"
                ),
                division_ocdid=(
                    "ocd-division/country:us/state:ma/county:worcester/place:millbury"
                ),
                registry=registry,
            )

    def test_missing_division_never_mints(self):
        _, registry = load_fixture()
        with self.assertRaisesRegex(OCDIDRegistryError, "DIVISION_NOT_IN_REGISTRY"):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:tx/place:arlington/government"
                ),
                division_ocdid=(
                    "ocd-division/country:us/state:tx/place:arlington/council_district:999"
                ),
                registry=registry,
            )

    def test_missing_jurisdiction_base_never_mints(self):
        _, registry = load_fixture()
        with self.assertRaisesRegex(
            OCDIDRegistryError,
            "JURISDICTION_BASE_DIVISION_NOT_IN_REGISTRY",
        ):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:tx/place:not_real/government"
                ),
                division_ocdid=(
                    "ocd-division/country:us/state:tx/place:arlington/council_district:5"
                ),
                registry=registry,
            )

    def test_ambiguous_reviewed_mapping_fails_closed(self):
        payload, registry = load_fixture()
        mappings = list(payload["reviewed_mappings"])
        mappings.append(
            {
                "entity_type": "division",
                "source_id": (
                    "ocd-division/country:us/state:ma/county:worcester/place:millbury"
                ),
                "canonical_id": (
                    "ocd-division/country:us/state:tx/place:arlington"
                ),
                "review_status": "accepted",
                "reviewed_at": "2026-09-25",
                "reviewer": "conflicting test review",
                "evidence": "synthetic-regression",
            }
        )
        with self.assertRaisesRegex(
            OCDIDRegistryError,
            "REVIEWED_MAPPING_AMBIGUOUS",
        ):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:ma/place:millbury/government"
                ),
                division_ocdid=(
                    "ocd-division/country:us/state:ma/county:worcester/place:millbury"
                ),
                registry=registry,
                reviewed_mappings=mappings,
            )

    def test_mapping_target_must_exist_in_registry(self):
        _, registry = load_fixture()
        mappings = [
            {
                "entity_type": "division",
                "source_id": "ocd-division/country:us/state:ma/legacy:millbury",
                "canonical_id": "ocd-division/country:us/state:ma/place:not_real",
                "review_status": "accepted",
                "reviewed_at": "2026-09-25",
                "reviewer": "test",
                "evidence": "synthetic-regression",
            }
        ]
        with self.assertRaisesRegex(
            OCDIDRegistryError,
            "REVIEWED_MAPPING_TARGET_INVALID",
        ):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:ma/place:millbury/government"
                ),
                division_ocdid="ocd-division/country:us/state:ma/legacy:millbury",
                registry=registry,
                reviewed_mappings=mappings,
            )

    def test_cross_state_post_division_fails(self):
        payload, registry = load_fixture()
        master = set(registry.master_divisions)
        master.add("ocd-division/country:us/state:ma/place:millbury/ward:1")
        altered = RegistrySnapshot(
            source_repository=registry.source_repository,
            source_commit=registry.source_commit,
            manifest_generated_at=registry.manifest_generated_at,
            master_divisions=frozenset(master),
            published_divisions=registry.published_divisions,
            published_states=registry.published_states,
        )
        with self.assertRaisesRegex(OCDIDRegistryError, "STATE_MISMATCH"):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:tx/place:arlington/government"
                ),
                division_ocdid="ocd-division/country:us/state:ma/place:millbury/ward:1",
                registry=altered,
            )

    def test_unrelated_same_state_division_fails(self):
        _, registry = load_fixture()
        with self.assertRaisesRegex(
            OCDIDRegistryError,
            "DIVISION_OUTSIDE_JURISDICTION",
        ):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:tx/place:arlington/government"
                ),
                division_ocdid="ocd-division/country:us/state:tx/place:austin",
                registry=RegistrySnapshot(
                    source_repository=registry.source_repository,
                    source_commit=registry.source_commit,
                    manifest_generated_at=registry.manifest_generated_at,
                    master_divisions=frozenset(
                        set(registry.master_divisions)
                        | {"ocd-division/country:us/state:tx/place:austin"}
                    ),
                    published_divisions=registry.published_divisions,
                    published_states=registry.published_states,
                ),
            )

    def test_malformed_mapping_requires_review_metadata(self):
        _, registry = load_fixture()
        mapping = [
            {
                "entity_type": "division",
                "source_id": "ocd-division/country:us/state:ma/legacy:millbury",
                "canonical_id": "ocd-division/country:us/state:ma/place:millbury",
                "review_status": "accepted",
            }
        ]
        with self.assertRaisesRegex(OCDIDRegistryError, "REVIEWED_MAPPING_INVALID"):
            validate_civicpatch_identity(
                jurisdiction_ocdid=(
                    "ocd-jurisdiction/country:us/state:ma/place:millbury/government"
                ),
                division_ocdid="ocd-division/country:us/state:ma/legacy:millbury",
                registry=registry,
                reviewed_mappings=mapping,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
