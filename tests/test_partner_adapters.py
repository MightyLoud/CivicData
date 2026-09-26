from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.civic_mirror.adapter import adapt_civic_mirror_snapshot
from adapters.factory.export_representation import export_factory_package
from adapters.partner_assertions import PartnerAdapterError
from adapters.seegov.adapter import adapt_seegov_snapshot
from tests.test_shared_identity_adapter_integration import (
    SHARED_ORG,
    SHARED_PERSON,
    registry as base_registry,
)
from tools.assertion_governance import (
    promote_accepted_assertion,
    review_assertion,
    validate_assertion,
)
from tools.canonical_representation_core import (
    from_jurisdiction_package,
    validate_core,
)

try:
    import jsonschema
except ImportError:
    jsonschema = None

FACTORY_PATH = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
J = "ocd-jurisdiction/country:us/state:co/place:akron/government"
STAMP = "2026-09-26T12:00:00Z"
BASE_SNAPSHOT = "snapshot-akron-contract-001"

SEEGOV_ORG = "government/akron-board-of-trustees"
SEEGOV_JARED = "speaker/jared-jefferson"
MIRROR_ORG = "body/akron-board-of-trustees"
MIRROR_JARED = "official/jared-jefferson"


def registry() -> dict:
    out = copy.deepcopy(base_registry())
    out["crosswalks"].extend(
        [
            {
                "crosswalk_id": "xw-org-seegov-akron",
                "entity_type": "organization",
                "canonical_id": SHARED_ORG,
                "system": "seegov",
                "external_id": SEEGOV_ORG,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-26",
                "source": "reviewed test crosswalk",
            },
            {
                "crosswalk_id": "xw-person-seegov-jared",
                "entity_type": "person",
                "canonical_id": SHARED_PERSON,
                "system": "seegov",
                "external_id": SEEGOV_JARED,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-26",
                "source": "reviewed test crosswalk",
            },
            {
                "crosswalk_id": "xw-org-mirror-akron",
                "entity_type": "organization",
                "canonical_id": SHARED_ORG,
                "system": "civic_mirror",
                "external_id": MIRROR_ORG,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-26",
                "source": "reviewed test crosswalk",
            },
            {
                "crosswalk_id": "xw-person-mirror-jared",
                "entity_type": "person",
                "canonical_id": SHARED_PERSON,
                "system": "civic_mirror",
                "external_id": MIRROR_JARED,
                "external_url": None,
                "status": "ACTIVE",
                "verified_at": "2026-09-26",
                "source": "reviewed test crosswalk",
            },
        ]
    )
    return out


def contract() -> dict:
    package = json.loads(FACTORY_PATH.read_text(encoding="utf-8"))
    return export_factory_package(
        package,
        generated_at="2026-08-19T00:00:00Z",
        identity_registry=registry(),
    )


def seegov_snapshot() -> dict:
    return {
        "snapshot_id": "seegov-akron-2026-09-26",
        "captured_at": STAMP,
        "jurisdiction_ocdid": J,
        "meetings": [
            {
                "meeting_id": "meeting-akron-2026-09-15",
                "organization_external_id": SEEGOV_ORG,
                "started_at": "2026-09-15T18:00:00-06:00",
                "source_url": "https://example.invalid/seegov/meeting/akron-2026-09-15",
                "video_url": "https://example.invalid/video/akron-2026-09-15",
                "transcript_url": "https://example.invalid/transcript/akron-2026-09-15",
                "agenda_url": "https://example.invalid/agenda/akron-2026-09-15",
                "moments": [
                    {
                        "moment_id": "moment-1",
                        "summary": "Board discussed a public works item.",
                    }
                ],
                "vote_outcomes": [
                    {
                        "agenda_item": "Public works",
                        "outcome": "passed",
                    }
                ],
                "speakers": [
                    {
                        "person_external_id": SEEGOV_JARED,
                        "display_name": "Jared Jefferson",
                        "representation_observations": [
                            {
                                "observation_id": "obs-seegov-jared-title",
                                "subject_type": "membership",
                                "field_path": "label",
                                "value": "Mayor Pro Tem",
                                "asserted_at": "2026-09-26T11:55:00Z",
                                "evidence_locator": "https://example.invalid/seegov/meeting/akron-2026-09-15#speaker-jared",
                            }
                        ],
                    },
                    {
                        "person_external_id": "speaker/unreviewed-resident",
                        "display_name": "Unreviewed Resident",
                        "representation_observations": [
                            {
                                "observation_id": "obs-seegov-unresolved",
                                "subject_type": "person",
                                "field_path": "name",
                                "value": "Unreviewed Resident",
                                "asserted_at": "2026-09-26T11:56:00Z",
                                "evidence_locator": "https://example.invalid/seegov/meeting/akron-2026-09-15#resident",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def civic_mirror_snapshot() -> dict:
    return {
        "snapshot_id": "civic-mirror-akron-2026-09-26",
        "captured_at": STAMP,
        "jurisdiction_ocdid": J,
        "evidence": [
            {
                "evidence_external_id": "evidence/jared-profile-001",
                "source_url": "https://example.invalid/civic-mirror/evidence/jared-001",
                "captured_at": "2026-09-26T11:50:00Z",
                "title": "Official profile observation",
                "editorial_tag": "questionable",
                "kind": "article",
                "person_external_id": MIRROR_JARED,
                "organization_external_id": MIRROR_ORG,
                "representation_observations": [
                    {
                        "observation_id": "obs-mirror-jared-name",
                        "subject_type": "person",
                        "field_path": "name",
                        "value": "Jared Jefferson",
                        "asserted_at": "2026-09-26T11:52:00Z",
                    }
                ],
            }
        ],
        "bills": [
            {
                "bill_external_id": "bill/example-001",
                "title": "Example Bill",
            }
        ],
        "events": [
            {
                "event_external_id": "event/example-001",
                "title": "Example Event",
            }
        ],
    }


class PartnerAdapterIntegrationTests(unittest.TestCase):
    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_normalized_partner_inputs_validate_against_schemas(self):
        checker = jsonschema.FormatChecker()
        for filename, payload in (
            ("seegov_partner_snapshot_v0.1.schema.json", seegov_snapshot()),
            (
                "civic_mirror_partner_snapshot_v0.1.schema.json",
                civic_mirror_snapshot(),
            ),
        ):
            schema = json.loads(
                (ROOT / "schemas" / filename).read_text(encoding="utf-8")
            )
            validator = jsonschema.Draft202012Validator(
                schema,
                format_checker=checker,
            )
            errors = sorted(
                validator.iter_errors(payload),
                key=lambda error: list(error.path),
            )
            self.assertEqual(errors, [], [error.message for error in errors])

    def test_seegov_resolves_meeting_body_and_speaker_and_emits_proposed_assertion(self):
        result = adapt_seegov_snapshot(
            seegov_snapshot(),
            identity_registry=registry(),
            contract=contract(),
            base_snapshot_id=BASE_SNAPSHOT,
        )
        self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(result["organization_links"][0]["status"], "RESOLVED")
        self.assertEqual(
            result["organization_links"][0]["shared_identity_id"],
            SHARED_ORG,
        )
        resolved_people = {
            row["external_id"]: row for row in result["person_links"]
        }
        self.assertEqual(resolved_people[SEEGOV_JARED]["status"], "RESOLVED")
        self.assertEqual(
            resolved_people[SEEGOV_JARED]["shared_identity_id"],
            SHARED_PERSON,
        )

        self.assertEqual(len(result["assertions"]), 1)
        assertion = result["assertions"][0]
        self.assertEqual(assertion["source_system"], "seegov")
        self.assertEqual(assertion["subject_type"], "membership")
        self.assertEqual(
            assertion["subject_id"],
            "role-co-akron-trustee-jared-jefferson",
        )
        self.assertEqual(assertion["field_path"], "label")
        self.assertEqual(assertion["value"], "Mayor Pro Tem")
        self.assertEqual(assertion["review_status"], "proposed")
        self.assertEqual(validate_assertion(assertion), [])

        # Unreviewed speaker identity is held, never name-matched into a Person.
        self.assertEqual(len(result["held_observations"]), 1)
        self.assertEqual(
            result["held_observations"][0]["status"],
            "identity_conflict",
        )
        self.assertIn(
            "PERSON_IDENTITY_UNRESOLVED",
            result["held_observations"][0]["reason"],
        )

    def test_seegov_meeting_content_stays_partner_owned(self):
        result = adapt_seegov_snapshot(
            seegov_snapshot(),
            identity_registry=registry(),
            contract=contract(),
            base_snapshot_id=BASE_SNAPSHOT,
        )
        meeting = result["product_objects"]["meetings"][0]
        self.assertEqual(
            meeting["transcript_url"],
            "https://example.invalid/transcript/akron-2026-09-15",
        )
        self.assertEqual(len(meeting["moments"]), 1)
        self.assertEqual(len(meeting["vote_outcomes"]), 1)
        # No transcript/moment/vote object is silently inserted into Contract assertions.
        self.assertEqual(
            {row["field_path"] for row in result["assertions"]},
            {"label"},
        )

    def test_civic_mirror_evidence_resolves_official_and_emits_only_explicit_observation(self):
        result = adapt_civic_mirror_snapshot(
            civic_mirror_snapshot(),
            identity_registry=registry(),
            contract=contract(),
            base_snapshot_id=BASE_SNAPSHOT,
        )
        self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(len(result["assertions"]), 1)
        assertion = result["assertions"][0]
        self.assertEqual(assertion["source_system"], "civic_mirror")
        self.assertEqual(assertion["subject_type"], "person")
        self.assertEqual(
            assertion["subject_id"],
            "person-co-akron-jared-jefferson",
        )
        self.assertEqual(assertion["field_path"], "name")
        self.assertEqual(assertion["value"], "Jared Jefferson")
        self.assertEqual(validate_assertion(assertion), [])

        evidence = result["product_objects"]["evidence"][0]
        self.assertEqual(evidence["editorial_tag"], "questionable")
        self.assertEqual(
            evidence["shared_person_link"]["shared_identity_id"],
            SHARED_PERSON,
        )
        # Editorial judgment stays Civic Mirror metadata; it is not a canonical assertion.
        self.assertNotIn(
            "questionable",
            [row["value"] for row in result["assertions"]],
        )

    def test_partner_assertion_is_directly_promotable_against_canonical_core_after_review(self):
        package = json.loads(FACTORY_PATH.read_text(encoding="utf-8"))
        core = from_jurisdiction_package(package)
        self.assertEqual(validate_core(core), [])

        result = adapt_seegov_snapshot(
            seegov_snapshot(),
            identity_registry=registry(),
            contract=contract(),
            base_snapshot_id=core["snapshot_id"],
        )
        assertion = result["assertions"][0]
        accepted = review_assertion(
            assertion,
            outcome="accepted",
            reviewer="test-reviewer",
            reviewer_authority="civicdata_representation",
            reviewed_at="2026-09-26T12:05:00Z",
            reason="Acceptance test for canonical-core promotion path",
        )
        promoted = promote_accepted_assertion(
            core,
            accepted,
            new_snapshot_id="factory:jurisdiction-co-akron:partner-test",
            promoted_at="2026-09-26T12:06:00Z",
        )
        target = next(
            row
            for row in promoted["memberships"]
            if row["membership_id"] == "role-co-akron-trustee-jared-jefferson"
        )
        self.assertEqual(target["label"], "Mayor Pro Tem")
        self.assertEqual(promoted["certification"]["status"], "uncertified")

    def test_civic_mirror_bills_and_events_remain_product_owned(self):
        result = adapt_civic_mirror_snapshot(
            civic_mirror_snapshot(),
            identity_registry=registry(),
            contract=contract(),
            base_snapshot_id=BASE_SNAPSHOT,
        )
        self.assertEqual(
            result["product_objects"]["bills"][0]["bill_external_id"],
            "bill/example-001",
        )
        self.assertEqual(
            result["product_objects"]["events"][0]["event_external_id"],
            "event/example-001",
        )
        self.assertEqual(len(result["assertions"]), 1)

    def test_missing_partner_registry_mapping_holds_observation(self):
        snapshot = civic_mirror_snapshot()
        snapshot["evidence"][0]["person_external_id"] = "official/unreviewed"
        result = adapt_civic_mirror_snapshot(
            snapshot,
            identity_registry=registry(),
            contract=contract(),
            base_snapshot_id=BASE_SNAPSHOT,
        )
        self.assertEqual(result["assertions"], [])
        self.assertEqual(len(result["held_observations"]), 1)
        self.assertEqual(
            result["held_observations"][0]["status"],
            "identity_conflict",
        )

    def test_partner_adapter_rejects_missing_registry(self):
        with self.assertRaisesRegex(
            PartnerAdapterError,
            "IDENTITY_REGISTRY_REQUIRED",
        ):
            adapt_seegov_snapshot(
                seegov_snapshot(),
                identity_registry=None,  # type: ignore[arg-type]
                contract=contract(),
                base_snapshot_id=BASE_SNAPSHOT,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
