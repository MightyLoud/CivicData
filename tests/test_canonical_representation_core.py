from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.canonical_representation_core import (
    from_jurisdiction_package,
    validate_core,
)

FIXTURES = ROOT / "acceptance" / "representation" / "canonical_core"
SCHEMA = ROOT / "schemas" / "canonical_representation_core_v0.1.schema.json"
AKRON = ROOT / "data" / "normalized" / "co" / "jurisdiction-co-akron" / "jurisdiction.json"
ALMA = ROOT / "data" / "normalized" / "co" / "jurisdiction-co-alma" / "jurisdiction.json"


def load_fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class CanonicalRepresentationCoreTests(unittest.TestCase):
    def test_all_level_fixtures_validate(self):
        for name in ("municipality", "county", "state_legislative", "congressional"):
            with self.subTest(name=name):
                self.assertEqual(validate_core(load_fixture(name)), [])

    def test_level_examples_cover_required_scope(self):
        municipality = load_fixture("municipality")
        county = load_fixture("county")
        state_leg = load_fixture("state_legislative")
        congressional = load_fixture("congressional")

        self.assertIn("MUNICIPAL", {x["level"] for x in municipality["jurisdictions"]})
        self.assertIn("COUNTY", {x["level"] for x in county["jurisdictions"]})
        self.assertIn("STATE", {x["level"] for x in state_leg["jurisdictions"]})
        self.assertIn("FEDERAL", {x["level"] for x in congressional["jurisdictions"]})
        self.assertIn(
            "STATE_LEGISLATIVE_DISTRICT",
            {x["division_type"] for x in state_leg["divisions"]},
        )
        self.assertIn(
            "CONGRESSIONAL_DISTRICT",
            {x["division_type"] for x in congressional["divisions"]},
        )

    def test_municipality_fixture_preserves_parent_hierarchy(self):
        snapshot = load_fixture("municipality")
        jurisdictions = {
            row["jurisdiction_ocdid"]: row for row in snapshot["jurisdictions"]
        }
        municipal = jurisdictions[
            "ocd-jurisdiction/country:us/state:zz/place:exampleville/government"
        ]
        county = jurisdictions[
            "ocd-jurisdiction/country:us/state:zz/county:example/government"
        ]
        self.assertEqual(
            municipal["parent_jurisdiction_ocdid"],
            county["jurisdiction_ocdid"],
        )
        self.assertEqual(
            county["parent_jurisdiction_ocdid"],
            "ocd-jurisdiction/country:us/state:zz/government",
        )

        divisions = {row["division_ocdid"]: row for row in snapshot["divisions"]}
        self.assertEqual(
            divisions[
                "ocd-division/country:us/state:zz/place:exampleville"
            ]["parent_division_ocdid"],
            "ocd-division/country:us/state:zz/county:example",
        )

    def test_schema_documents_primary_keys_and_required_fields(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        defs = schema["$defs"]
        expected = {
            "jurisdiction": "jurisdiction_ocdid",
            "division": "division_ocdid",
            "organization": "organization_id",
            "role": "role_id",
            "post": "post_id",
            "person": "person_id",
            "membership": "membership_id",
            "evidence": "evidence_id",
            "assertion": "assertion_id",
        }
        for definition, primary_key in expected.items():
            with self.subTest(definition=definition):
                self.assertIn(primary_key, defs[definition]["required"])
                self.assertIn(primary_key, defs[definition]["properties"])

    def test_schema_documents_enumerated_fields(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        defs = schema["$defs"]
        self.assertEqual(
            set(defs["jurisdiction"]["properties"]["level"]["enum"]),
            {"FEDERAL", "STATE", "COUNTY", "MUNICIPAL", "OTHER"},
        )
        self.assertIn(
            "CONGRESSIONAL_DISTRICT",
            defs["division"]["properties"]["division_type"]["enum"],
        )
        self.assertIn(
            "STATE_LEGISLATIVE_DISTRICT",
            defs["division"]["properties"]["division_type"]["enum"],
        )
        self.assertEqual(
            set(defs["membership"]["properties"]["confidence"]["$ref"] for _ in [0]),
            {"#/$defs/confidence"},
        )

    def test_source_metadata_and_confidence_are_explicit(self):
        snapshot = load_fixture("county")
        evidence = snapshot["evidence"][0]
        for field in (
            "source_url",
            "source_class",
            "source_type",
            "retrieved_at",
            "confidence",
        ):
            self.assertIn(field, evidence)
            self.assertTrue(evidence[field])
        self.assertEqual(snapshot["memberships"][0]["confidence"], "HIGH")
        self.assertEqual(snapshot["assertions"][0]["confidence"], "HIGH")

    def test_duplicate_primary_key_fails_closed(self):
        snapshot = load_fixture("county")
        snapshot["people"].append(deepcopy(snapshot["people"][0]))
        errors = validate_core(snapshot)
        self.assertTrue(
            any(error.startswith("DUPLICATE_PRIMARY_KEY:people:") for error in errors),
            errors,
        )

    def test_broken_parent_jurisdiction_fails_closed(self):
        snapshot = load_fixture("municipality")
        snapshot["jurisdictions"][-1]["parent_jurisdiction_ocdid"] = (
            "ocd-jurisdiction/country:us/state:zz/county:missing/government"
        )
        self.assertIn("PARENT_JURISDICTION_FK", validate_core(snapshot))

    def test_broken_membership_foreign_keys_fail_closed(self):
        snapshot = load_fixture("county")
        snapshot["memberships"][0]["person_id"] = "person-missing"
        snapshot["memberships"][0]["post_id"] = "post-missing"
        errors = validate_core(snapshot)
        self.assertIn("MEMBERSHIP_PERSON_FK", errors)
        self.assertIn("MEMBERSHIP_POST_FK", errors)

    def test_broken_source_reference_fails_closed(self):
        snapshot = load_fixture("county")
        snapshot["posts"][0]["source_ids"] = ["missing-evidence"]
        self.assertIn("SOURCE_REFERENCE_INVALID:posts", validate_core(snapshot))

    def test_assertion_subject_and_evidence_relationships_are_validated(self):
        snapshot = load_fixture("county")
        snapshot["assertions"][0]["subject_id"] = "missing-post"
        snapshot["assertions"][0]["evidence_ids"] = ["missing-evidence"]
        errors = validate_core(snapshot)
        self.assertIn("ASSERTION_SUBJECT_FK", errors)
        self.assertIn("ASSERTION_EVIDENCE_FK", errors)

    def test_certified_snapshot_requires_raw_normalized_qa_and_parity(self):
        snapshot = load_fixture("county")
        snapshot["certification"]["qa_passed"] = False
        errors = validate_core(snapshot)
        self.assertIn("CERTIFIED_GATES_INCOMPLETE", errors)

        snapshot = load_fixture("county")
        snapshot["assertions"][0]["normalization_status"] = "RAW"
        self.assertIn(
            "NORMALIZED_COMPLETE_WITH_UNREVIEWED_RAW_ASSERTIONS",
            validate_core(snapshot),
        )

        snapshot = load_fixture("county")
        snapshot["review"]["parity_ok"] = False
        errors = validate_core(snapshot)
        self.assertIn("PARITY_GATE_MISMATCH", errors)

    def test_reviewed_nonblocking_conflict_can_coexist_with_certified_scope(self):
        package = json.loads(ALMA.read_text(encoding="utf-8"))
        core = from_jurisdiction_package(package)
        errors = validate_core(core)
        self.assertEqual(errors, [])
        self.assertEqual(core["certification"]["status"], "certified")
        held = [
            row
            for row in core["assertions"]
            if row["review_status"] == "NEEDS_EVIDENCE"
        ]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["normalization_status"], "RAW")

    def test_existing_akron_pilot_converts_and_validates(self):
        package = json.loads(AKRON.read_text(encoding="utf-8"))
        core = from_jurisdiction_package(package)
        errors = validate_core(core)
        self.assertEqual(errors, [])
        self.assertEqual(core["jurisdictions"][0]["level"], "MUNICIPAL")
        self.assertEqual(core["review"]["qa_result"], "PASS")
        self.assertTrue(core["review"]["parity_ok"])
        self.assertEqual(core["certification"]["status"], "certified")
        self.assertGreaterEqual(len(core["evidence"]), 1)
        self.assertGreaterEqual(len(core["assertions"]), 1)

    def test_akron_internal_leadership_does_not_overload_post_role(self):
        package = json.loads(AKRON.read_text(encoding="utf-8"))
        core = from_jurisdiction_package(package)
        memberships = {
            row["membership_id"]: row for row in core["memberships"]
        }
        posts = {row["post_id"]: row for row in core["posts"]}
        target = next(
            row for row in memberships.values()
            if row.get("label") == "Mayor Pro Tem"
        )
        self.assertEqual(posts[target["post_id"]]["role_id"], "trustee")


if __name__ == "__main__":
    unittest.main(verbosity=2)
