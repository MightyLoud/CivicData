from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.civicpatch.export_representation import (
    ExportError as CivicPatchExportError,
    export_civicpatch_snapshot,
)
from adapters.factory.export_representation import (
    ExportError as FactoryExportError,
    export_factory_package,
)
from adapters.shared_identity import (
    SharedIdentityResolutionError,
    SharedIdentityResolver,
)
from consumers.empowered_vote import contract_v1_catalog
from tests.test_civicpatch_representation_export import (
    EVIDENCE,
    J,
    MEMBERSHIP,
    ORG,
    PERSON,
    POST,
    STAMP,
    fixture as civicpatch_fixture,
)
from tools.reconcile_representation import reconcile

SHARED_ORG = "org-11111111-1111-4111-8111-111111111111"
SHARED_PERSON = "per-22222222-2222-4222-8222-222222222222"
OTHER_PERSON = "per-33333333-3333-4333-8333-333333333333"
FACTORY_PATH = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"


def registry() -> dict:
    return {
        "registry_version": "0.1",
        "registry_owner": "MightyLoud/CivicData",
        "id_strategy": {
            "organization": "org-<uuidv4>",
            "person": "per-<uuidv4>",
        },
        "entities": [
            {
                "canonical_id": SHARED_ORG,
                "entity_type": "organization",
                "display_name": "Shared Governing Body",
                "status": "ACTIVE",
                "created_at": "2026-09-25",
                "superseded_by": None,
            },
            {
                "canonical_id": SHARED_PERSON,
                "entity_type": "person",
                "display_name": "Shared Person",
                "status": "ACTIVE",
                "created_at": "2026-09-25",
                "superseded_by": None,
            },
            {
                "canonical_id": OTHER_PERSON,
                "entity_type": "person",
                "display_name": "Other Person",
                "status": "ACTIVE",
                "created_at": "2026-09-25",
                "superseded_by": None,
            },
        ],
        "crosswalks": [
            {
                "crosswalk_id": "xw-org-factory-akron",
                "entity_type": "organization",
                "canonical_id": SHARED_ORG,
                "system": "jurisdiction_factory",
                "external_id": "body-co-akron-board-of-trustees",
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-25",
                "source": "reviewed test crosswalk",
            },
            {
                "crosswalk_id": "xw-person-factory-jared",
                "entity_type": "person",
                "canonical_id": SHARED_PERSON,
                "system": "jurisdiction_factory",
                "external_id": "person-co-akron-jared-jefferson",
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-25",
                "source": "reviewed test crosswalk",
            },
            {
                "crosswalk_id": "xw-org-civicpatch",
                "entity_type": "organization",
                "canonical_id": SHARED_ORG,
                "system": "civicpatch",
                "external_id": ORG,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-25",
                "source": "reviewed test crosswalk",
            },
            {
                "crosswalk_id": "xw-person-civicpatch",
                "entity_type": "person",
                "canonical_id": SHARED_PERSON,
                "system": "civicpatch",
                "external_id": PERSON,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-25",
                "source": "reviewed test crosswalk",
            },
        ],
        "events": [],
    }


class SharedIdentityAdapterIntegrationTests(unittest.TestCase):
    def test_factory_export_resolves_reviewed_org_and_person_crosswalks(self):
        package = json.loads(FACTORY_PATH.read_text(encoding="utf-8"))
        out = export_factory_package(
            package,
            generated_at="2026-08-19T00:00:00Z",
            identity_registry=registry(),
        )
        self.assertEqual(out["organizations"][0]["shared_identity_id"], SHARED_ORG)
        people = {row["name"]: row for row in out["people"]}
        self.assertEqual(
            people["Jared Jefferson"]["shared_identity_id"],
            SHARED_PERSON,
        )
        # No reviewed crosswalk means no inferred shared identity, even when a name exists.
        self.assertIsNone(people["Braden Brent"]["shared_identity_id"])

    def test_civicpatch_export_resolves_reviewed_org_and_person_crosswalks(self):
        out = export_civicpatch_snapshot(
            civicpatch_fixture(),
            generated_at=STAMP,
            identity_registry=registry(),
        )
        self.assertEqual(out["organizations"][0]["shared_identity_id"], SHARED_ORG)
        self.assertEqual(out["people"][0]["shared_identity_id"], SHARED_PERSON)

    def test_resolver_never_name_matches_missing_external_id(self):
        resolver = SharedIdentityResolver(registry())
        self.assertIsNone(
            resolver.resolve(
                entity_type="person",
                system="civicpatch",
                external_id="same-name-but-unreviewed",
            )
        )

    def test_invalid_registry_fails_both_exporters_closed(self):
        bad = registry()
        bad["crosswalks"].append(
            {
                "crosswalk_id": "xw-conflict",
                "entity_type": "person",
                "canonical_id": OTHER_PERSON,
                "system": "civicpatch",
                "external_id": PERSON,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-25",
                "source": "conflicting reviewed mapping",
            }
        )
        with self.assertRaisesRegex(CivicPatchExportError, "IDENTITY_REGISTRY_INVALID"):
            export_civicpatch_snapshot(
                civicpatch_fixture(),
                generated_at=STAMP,
                identity_registry=bad,
            )
        package = json.loads(FACTORY_PATH.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(FactoryExportError, "IDENTITY_REGISTRY_INVALID"):
            export_factory_package(
                package,
                generated_at="2026-08-19T00:00:00Z",
                identity_registry=bad,
            )

    def test_active_crosswalk_to_merged_identity_fails_closed(self):
        bad = registry()
        person = next(
            row for row in bad["entities"] if row["canonical_id"] == SHARED_PERSON
        )
        person["status"] = "MERGED"
        person["superseded_by"] = OTHER_PERSON

        resolver = SharedIdentityResolver(bad)
        with self.assertRaisesRegex(
            SharedIdentityResolutionError,
            "IDENTITY_CROSSWALK_CANONICAL_ID_NOT_ACTIVE",
        ):
            resolver.resolve(
                entity_type="person",
                system="civicpatch",
                external_id=PERSON,
            )

    def test_reviewed_factory_identity_flows_through_empowered_vote_shadow(self):
        gps = {
            "payload": {
                "input": {"matched_address": "250 MAIN AVENUE, AKRON, CO 80720"},
                "jurisdictions": [{"jurisdiction_id": "jur-us-co-akron"}],
                "district_assignments": [],
            }
        }
        model = contract_v1_catalog.build_representation_from_catalog(
            "250 Main Avenue, Akron, CO 80720",
            gps,
            repo_root=ROOT,
            identity_registry=registry(),
        )
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["canonical_writes"], 0)
        self.assertTrue(
            all(
                row["shared_organization_id"] == SHARED_ORG
                for row in model["applicable_offices"]
            )
        )
        trustees = next(
            row
            for row in model["applicable_offices"]
            if row["office_id"] == "office-co-akron-trustee"
        )
        jared = next(
            row for row in trustees["holders"] if row["name"] == "Jared Jefferson"
        )
        self.assertEqual(jared["shared_person_id"], SHARED_PERSON)
        braden = next(
            row for row in trustees["holders"] if row["name"] == "Braden Brent"
        )
        self.assertIsNone(braden["shared_person_id"])

    def test_post_reconciliation_uses_shared_organization_identity_across_rename(self):
        factory = {
            "generated_at": STAMP,
            "jurisdiction": {"jurisdiction_ocdid": J, "name": "Synthetic City"},
            "organizations": [
                {
                    "id": "factory-org",
                    "shared_identity_id": SHARED_ORG,
                    "name": "Old Council Name",
                    "is_default": False,
                }
            ],
            "roles": [],
            "posts": [
                {
                    "id": "factory-post",
                    "organization_id": "factory-org",
                    "role_id": "council-member",
                    "division_ocdid": "ocd-division/country:us/state:co/place:synthetic",
                    "meta_headcount": 1,
                    "selection_method": "elected",
                }
            ],
            "memberships": [],
            "people": [],
            "certification": {},
        }
        civicpatch = copy.deepcopy(factory)
        civicpatch["organizations"][0]["id"] = "civicpatch-org"
        civicpatch["organizations"][0]["name"] = "Renamed City Council"
        civicpatch["posts"][0]["id"] = "civicpatch-post"
        civicpatch["posts"][0]["organization_id"] = "civicpatch-org"

        report = reconcile(factory, civicpatch)
        post = next(
            row for row in report["differences"] if row["entity_type"] == "post"
        )
        self.assertEqual(post["status"], "SAME")
        self.assertEqual(post["reason"], "SEMANTIC_POST_MATCH")

    def test_contract_consumer_rejects_malformed_shared_identity_id(self):
        from consumers.empowered_vote import contract_v1

        package = json.loads(FACTORY_PATH.read_text(encoding="utf-8"))
        contract = export_factory_package(
            package,
            generated_at="2026-08-19T00:00:00Z",
        )
        contract["people"][0]["shared_identity_id"] = "person-not-a-shared-id"
        errors = contract_v1.validate_contract(
            contract,
            require_certified=False,
        )
        self.assertIn("CONTRACT_PERSON_SHARED_IDENTITY_INVALID", errors)

    def test_reconciler_accepts_same_reviewed_shared_person_identity(self):
        factory = {
            "generated_at": STAMP,
            "jurisdiction": {
                "jurisdiction_ocdid": J,
                "name": "Synthetic City",
            },
            "organizations": [],
            "posts": [],
            "memberships": [],
            "people": [
                {
                    "id": "factory-person",
                    "shared_identity_id": SHARED_PERSON,
                    "name": "Alex Example",
                    "identifiers": [],
                }
            ],
            "certification": {},
        }
        civicpatch = {
            "generated_at": STAMP,
            "jurisdiction": {
                "jurisdiction_ocdid": J,
                "name": "Synthetic City",
            },
            "organizations": [],
            "posts": [],
            "memberships": [],
            "people": [
                {
                    "id": "civicpatch-person",
                    "shared_identity_id": SHARED_PERSON,
                    "name": "Alex Example",
                    "identifiers": [],
                }
            ],
            "certification": {},
        }
        report = reconcile(factory, civicpatch)
        person_rows = [
            row for row in report["differences"] if row["entity_type"] == "person"
        ]
        self.assertEqual(len(person_rows), 1)
        self.assertEqual(person_rows[0]["status"], "SAME")
        self.assertEqual(person_rows[0]["reason"], "SHARED_IDENTITY")
        self.assertEqual(report["crosswalk_candidates"], [])
        self.assertEqual(report["canonical_writes"], 0)

    def test_reconciler_flags_reviewed_shared_identity_mismatch(self):
        factory = {
            "generated_at": STAMP,
            "jurisdiction": {"jurisdiction_ocdid": J, "name": "Synthetic City"},
            "organizations": [],
            "posts": [],
            "memberships": [],
            "people": [
                {
                    "id": "factory-person",
                    "shared_identity_id": SHARED_PERSON,
                    "name": "Alex Example",
                    "identifiers": [],
                }
            ],
            "certification": {},
        }
        civicpatch = copy.deepcopy(factory)
        civicpatch["people"][0]["id"] = "civicpatch-person"
        civicpatch["people"][0]["shared_identity_id"] = OTHER_PERSON

        report = reconcile(factory, civicpatch)
        row = next(
            row for row in report["differences"] if row["entity_type"] == "person"
        )
        self.assertEqual(row["status"], "IDENTITY_CONFLICT")
        self.assertEqual(row["reason"], "REVIEWED_SHARED_IDENTITY_MISMATCH")
        # A reviewed disagreement is not downgraded to another name-based proposal.
        self.assertEqual(report["crosswalk_candidates"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
