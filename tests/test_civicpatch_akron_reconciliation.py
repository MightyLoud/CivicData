from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.civicpatch.adapter import (
    core_semantic_projection,
    round_trip_semantic_projection,
    validate_civicpatch_officials,
)
from consumers.civicpatch.build_akron_partner_patch import (
    ACTIONS_NAME,
    BUNDLE_NAME,
    MANIFEST_NAME,
    YAML_NAME,
    build_partner_patch,
)
from consumers.civicpatch.reconcile import (
    CivicPatchReconciliationError,
    apply_reconciliation,
    validate_reconciliation_plan,
)
from consumers.civicpatch.adapter import export_core_to_civicpatch
from tools.canonical_representation_core import from_jurisdiction_package
from tools.snapshot_manifest import validate_manifest, verify_payload

PACKAGE = ROOT / "data" / "normalized" / "co" / "jurisdiction-co-akron" / "jurisdiction.json"
CURRENT = ROOT / "acceptance" / "civicpatch" / "akron_current_pinned_69331c2.json"
PLAN = ROOT / "acceptance" / "civicpatch" / "akron_identity_reconciliation_v0.1.json"
COMMITTED = ROOT / "candidates" / "civicpatch" / "akron_v0.1" / "place_akron.yml"

GENERATED_AT = "2026-09-26T15:35:00Z"


def inputs():
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    core = from_jurisdiction_package(package)
    candidate = export_core_to_civicpatch(
        core,
        generated_at=GENERATED_AT,
        source_package_path=str(PACKAGE.relative_to(ROOT)),
    )
    return core, current, plan, candidate


class AkronCivicPatchReconciliationTests(unittest.TestCase):
    def test_reconciliation_plan_is_complete_and_explicit(self):
        _, current, plan, candidate = inputs()
        self.assertEqual(
            validate_reconciliation_plan(
                plan,
                current_officials=current["officials"],
                candidate_bundle=candidate,
            ),
            [],
        )
        self.assertTrue(
            plan["constraints"]["exact_name_matching_is_not_identity_authority"]
        )
        self.assertFalse(plan["constraints"]["upstream_write_authorized"])
        self.assertEqual(len(plan["accepted_crosswalks"]), 3)
        self.assertEqual(len(plan["additions"]), 4)
        self.assertEqual(len(plan["omissions"]), 4)

    def test_existing_civicpatch_ids_are_retained_only_for_reviewed_crosswalks(self):
        _, current, plan, candidate = inputs()
        reconciled = apply_reconciliation(candidate, current["officials"], plan)
        by_name = {row["name"]: row for row in reconciled["officials"]}
        self.assertEqual(
            by_name["Braden Brent"]["id"],
            "d31247df-3332-490e-b45d-fa8e7bb55e0b",
        )
        self.assertEqual(
            by_name["Crystann Benson"]["id"],
            "623089fb-bd23-4615-a440-1a61da966c15",
        )
        self.assertEqual(
            by_name["Jared Jefferson"]["id"],
            "dd07c3f5-1432-4c30-9bc9-9f73bb3385c2",
        )

    def test_new_current_officials_remain_preview_ids(self):
        _, current, plan, candidate = inputs()
        reconciled = apply_reconciliation(candidate, current["officials"], plan)
        by_name = {row["name"]: row for row in reconciled["officials"]}
        expected = {
            "Annette Bowin": "a6ef02f9-486d-5be0-ae9c-98adb41b1380",
            "Joe Tarnow": "df8d894e-22b7-5c95-9f28-075fc482d767",
            "Ron Kraich": "ddf9fb74-0e42-5d87-872f-119183b07ec7",
            "Terry Alexander": "59fce3b5-547d-5f0b-8f8c-5ed03a510ed9",
        }
        for name, preview_id in expected.items():
            with self.subTest(name=name):
                self.assertEqual(by_name[name]["id"], preview_id)

        receipts = {
            row["core_person_id"]: row
            for row in reconciled["receipt"]["person_crosswalks"]
        }
        for core_id in (
            "person-co-akron-annette-bowin",
            "person-co-akron-joe-tarnow",
            "person-co-akron-ron-kraich",
            "person-co-akron-terry-alexander",
        ):
            self.assertEqual(
                receipts[core_id]["status"],
                "NEW_PREVIEW_ID_PENDING_PARTNER_ACCEPTANCE",
            )

    def test_stale_current_rows_are_omissions_not_identity_deletes(self):
        _, current, plan, candidate = inputs()
        reconciled = apply_reconciliation(candidate, current["officials"], plan)
        actions = reconciled["reconciliation"]["actions"]
        omissions = {
            row["name"]: row for row in actions
            if row["action"] == "OMIT_STALE_ROSTER_ROW_NOT_IDENTITY_DELETE"
        }
        self.assertEqual(
            set(omissions),
            {"Brandon Hill", "Ariella Gonzales-Vondy", "David Kembel", "Jennifer Hansen"},
        )
        self.assertFalse(reconciled["reconciliation"]["upstream_write_authorized"])

    def test_jared_identity_retained_but_formal_role_corrected(self):
        _, current, plan, candidate = inputs()
        reconciled = apply_reconciliation(candidate, current["officials"], plan)
        jared = next(row for row in reconciled["officials"] if row["name"] == "Jared Jefferson")
        self.assertEqual(jared["id"], "dd07c3f5-1432-4c30-9bc9-9f73bb3385c2")
        self.assertEqual(jared["roles"][0]["role_id"], "trustee")
        self.assertEqual(jared["roles"][0]["name"], "Trustee")

        receipt = next(
            row for row in reconciled["receipt"]["membership_crosswalks"]
            if row["core_person_id"] == "person-co-akron-jared-jefferson"
        )
        self.assertEqual(receipt["internal_label"], "Mayor Pro Tem")
        self.assertFalse(receipt["internal_label_exported_as_formal_role"])

    def test_no_name_heuristic_can_fill_missing_crosswalk(self):
        _, current, plan, candidate = inputs()
        broken = deepcopy(plan)
        broken["accepted_crosswalks"] = [
            row for row in broken["accepted_crosswalks"]
            if row["name"] != "Braden Brent"
        ]
        errors = validate_reconciliation_plan(
            broken,
            current_officials=current["officials"],
            candidate_bundle=candidate,
        )
        self.assertIn("CANDIDATE_COVERAGE_INCOMPLETE", errors)
        self.assertIn("CURRENT_COVERAGE_INCOMPLETE", errors)
        with self.assertRaisesRegex(CivicPatchReconciliationError, "PLAN_INVALID"):
            apply_reconciliation(candidate, current["officials"], broken)

    def test_accepted_crosswalk_requires_review_evidence(self):
        _, current, plan, candidate = inputs()
        broken = deepcopy(plan)
        broken["accepted_crosswalks"][0]["evidence_ids"] = []
        self.assertIn(
            "ACCEPTED_EVIDENCE_INVALID",
            validate_reconciliation_plan(
                broken,
                current_officials=current["officials"],
                candidate_bundle=candidate,
            ),
        )

    def test_partner_ready_patch_round_trips_to_same_canonical_semantics(self):
        core, current, plan, candidate = inputs()
        reconciled = apply_reconciliation(candidate, current["officials"], plan)
        self.assertEqual(
            round_trip_semantic_projection(reconciled),
            core_semantic_projection(core),
        )
        self.assertEqual(validate_civicpatch_officials(reconciled["officials"]), [])

    def test_generated_partner_yaml_matches_committed_candidate_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_partner_patch(Path(tmp))
            generated = (Path(tmp) / YAML_NAME).read_bytes()
        self.assertEqual(generated, COMMITTED.read_bytes())

    def test_partner_patch_manifest_and_actions_are_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build_partner_patch(out)
            bundle = json.loads((out / BUNDLE_NAME).read_text(encoding="utf-8"))
            manifest = json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))
            actions = json.loads((out / ACTIONS_NAME).read_text(encoding="utf-8"))

        self.assertEqual(validate_manifest(manifest), [])
        verify_payload(manifest, bundle)
        self.assertEqual(manifest["schema_version"], "civicpatch-partner-patch/0.1")
        self.assertTrue(manifest["scope"]["complete_jurisdiction"])
        self.assertEqual(manifest["certification"]["status"], "certified")
        self.assertFalse(actions["upstream_write_authorized"])
        self.assertEqual(actions["target"]["path"], "data/co/local/place_akron.yml")

    def test_generation_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            build_partner_patch(Path(a))
            build_partner_patch(Path(b))
            for name in (YAML_NAME, BUNDLE_NAME, MANIFEST_NAME, ACTIONS_NAME):
                with self.subTest(name=name):
                    self.assertEqual(
                        (Path(a) / name).read_bytes(),
                        (Path(b) / name).read_bytes(),
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
