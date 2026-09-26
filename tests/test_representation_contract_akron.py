from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.civicpatch.rendered_open_data import export_rendered_roster
from adapters.factory.export_representation import export_factory_package
from tools.reconcile_representation import reconcile

try:
    import jsonschema
except ImportError:  # local stdlib-only runs still exercise semantic tests
    jsonschema = None

STAMP_FACTORY = "2026-08-19T00:00:00Z"
STAMP_CIVICPATCH = "2025-07-09T00:16:44Z"
FACTORY_PATH = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
CIVICPATCH_PATH = ROOT / "tests/fixtures/representation/akron_civicpatch_rendered_2025-07-09.json"
SCHEMA_PATH = ROOT / "schemas/representation_contract_v1.schema.json"


def load_outputs():
    factory_source = json.loads(FACTORY_PATH.read_text(encoding="utf-8"))
    civicpatch_source = json.loads(CIVICPATCH_PATH.read_text(encoding="utf-8"))
    factory = export_factory_package(factory_source, generated_at=STAMP_FACTORY)
    civicpatch = export_rendered_roster(civicpatch_source, generated_at=STAMP_CIVICPATCH)
    return factory, civicpatch


class AkronRepresentationProjectionTests(unittest.TestCase):
    def test_factory_projection_is_certified_and_preserves_seat_model(self):
        factory, _ = load_outputs()
        self.assertEqual(factory["jurisdiction"]["jurisdiction_ocdid"],
                         "ocd-jurisdiction/country:us/state:co/place:akron/government")
        self.assertEqual(factory["certification"]["status"], "certified")
        self.assertEqual({row["role_id"] for row in factory["posts"]}, {"mayor", "trustee"})
        trustee = next(row for row in factory["posts"] if row["role_id"] == "trustee")
        self.assertEqual(trustee["meta_headcount"], 6)
        self.assertEqual(len(factory["memberships"]), 7)
        jared = next(
            row for row in factory["memberships"]
            if next(p for p in factory["people"] if p["id"] == row["person_id"])["name"] == "Jared Jefferson"
        )
        self.assertEqual(jared["label"], "Mayor Pro Tem")
        self.assertEqual(jared["end_date"], "2028")

    def test_rendered_projection_is_uncertified_and_retains_historical_shape(self):
        _, civicpatch = load_outputs()
        self.assertEqual(civicpatch["certification"]["status"], "uncertified")
        self.assertEqual({row["role_id"] for row in civicpatch["posts"]},
                         {"mayor", "mayor-pro-tempore", "trustee"})
        trustee = next(row for row in civicpatch["posts"] if row["role_id"] == "trustee")
        self.assertEqual(trustee["meta_headcount"], 5)
        self.assertEqual(len(civicpatch["people"]), 7)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_both_real_akron_projections_validate_against_contract_schema(self):
        factory, civicpatch = load_outputs()
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        for name, payload in (("factory", factory), ("civicpatch", civicpatch)):
            errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
            self.assertEqual(errors, [], msg=f"{name}: {[e.message for e in errors]}")

    def test_real_akron_reconciliation_is_fail_closed(self):
        factory, civicpatch = load_outputs()
        report = reconcile(factory, civicpatch)

        self.assertEqual(report["canonical_writes"], 0)
        self.assertEqual(report["freshness"]["older_observed_side"], "civicpatch")
        self.assertEqual(report["counts"]["BLOCKED"], 0)

        people_crosswalks = [
            row for row in report["crosswalk_candidates"] if row["entity_type"] == "person"
        ]
        self.assertEqual(
            {row["normalized_name"] for row in people_crosswalks},
            {"braden brent", "crystann benson", "jared jefferson"},
        )
        self.assertTrue(all(row["status"] == "PROPOSED" for row in people_crosswalks))

        reasons = [row["reason"] for row in report["differences"]]
        self.assertIn("LEADERSHIP_TITLE_AS_POST", reasons)
        self.assertIn("POST_FIELDS_DIFFER", reasons)
        self.assertIn("PERSON_ONLY_IN_FACTORY", reasons)
        self.assertIn("PERSON_ONLY_IN_CIVICPATCH", reasons)

        trustee_conflicts = [
            row for row in report["differences"]
            if row["entity_type"] == "post"
            and row["reason"] == "POST_FIELDS_DIFFER"
            and row["fields"].get("meta_headcount")
        ]
        self.assertEqual(len(trustee_conflicts), 1)
        self.assertEqual(
            trustee_conflicts[0]["fields"]["meta_headcount"],
            {"factory": 6, "civicpatch": 5},
        )

    def test_common_akron_trustees_are_semantically_reconciled_without_auto_linking(self):
        factory, civicpatch = load_outputs()
        report = reconcile(factory, civicpatch)
        same_members = [
            row for row in report["differences"]
            if row["entity_type"] == "membership" and row["status"] == "SAME"
        ]
        same_names = {row["key"][0] for row in same_members}
        self.assertEqual(same_names, {"braden brent", "crystann benson"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
