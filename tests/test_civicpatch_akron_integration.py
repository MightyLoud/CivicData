from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.civicpatch.adapter import (
    ADAPTER_VERSION,
    CIVICPATCH_OPEN_DATA_COMMIT,
    CIVICPATCH_TOOLS_COMMIT,
    core_semantic_projection,
    round_trip_semantic_projection,
    validate_civicpatch_officials,
)
from consumers.civicpatch.build_akron_pilot import (
    BUNDLE_NAME,
    DRIFT_NAME,
    MANIFEST_NAME,
    YAML_NAME,
    build_artifacts,
)
from tools.canonical_representation_core import from_jurisdiction_package
from tools.snapshot_manifest import validate_manifest, verify_payload

PACKAGE = ROOT / "data" / "normalized" / "co" / "jurisdiction-co-akron" / "jurisdiction.json"


class CivicPatchAkronIntegrationTests(unittest.TestCase):
    def build(self, out: Path):
        build_artifacts(out)
        bundle = json.loads((out / BUNDLE_NAME).read_text(encoding="utf-8"))
        manifest = json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))
        drift = json.loads((out / DRIFT_NAME).read_text(encoding="utf-8"))
        yaml_text = (out / YAML_NAME).read_text(encoding="utf-8")
        return bundle, manifest, drift, yaml_text

    def test_real_certified_akron_package_exports_to_civicpatch_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, _, _, _ = self.build(Path(tmp))
        self.assertEqual(validate_civicpatch_officials(bundle["officials"]), [])
        self.assertEqual(
            [row["name"] for row in bundle["officials"]],
            [
                "Annette Bowin",
                "Braden Brent",
                "Crystann Benson",
                "Jared Jefferson",
                "Joe Tarnow",
                "Ron Kraich",
                "Terry Alexander",
            ],
        )
        self.assertEqual(len(bundle["officials"]), 7)
        self.assertTrue(bundle["source"]["certification"]["status"] == "certified")

    def test_formal_role_semantics_survive_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, _, _, yaml_text = self.build(Path(tmp))
        by_name = {row["name"]: row for row in bundle["officials"]}
        self.assertEqual(by_name["Annette Bowin"]["roles"][0]["role_id"], "mayor")
        for name in (
            "Braden Brent",
            "Crystann Benson",
            "Jared Jefferson",
            "Joe Tarnow",
            "Ron Kraich",
            "Terry Alexander",
        ):
            self.assertEqual(by_name[name]["roles"][0]["role_id"], "trustee")

        jared = next(
            row for row in bundle["receipt"]["membership_crosswalks"]
            if row["core_person_id"] == "person-co-akron-jared-jefferson"
        )
        self.assertEqual(jared["internal_label"], "Mayor Pro Tem")
        self.assertFalse(jared["internal_label_exported_as_formal_role"])
        self.assertNotIn("Mayor Pro Tem", yaml_text)
        self.assertNotIn("mayor-pro-tempore", yaml_text)

    def test_unknown_tenure_is_not_inferred_from_expiration_year_assertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, _, _, _ = self.build(Path(tmp))
        for official in bundle["officials"]:
            for role in official["roles"]:
                self.assertIsNone(role["start_date"])
                self.assertIsNone(role["end_date"])

    def test_preview_ids_are_deterministic_and_not_claimed_as_partner_ids(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            bundle_a, _, _, _ = self.build(Path(a))
            bundle_b, _, _, _ = self.build(Path(b))
        ids_a = [row["id"] for row in bundle_a["officials"]]
        ids_b = [row["id"] for row in bundle_b["officials"]]
        self.assertEqual(ids_a, ids_b)
        self.assertEqual(len(ids_a), len(set(ids_a)))
        self.assertFalse(bundle_a["candidate_id_policy"]["accepted_civicpatch_identity"])
        for row in bundle_a["receipt"]["person_crosswalks"]:
            self.assertEqual(
                row["status"],
                "PREVIEW_ONLY_REQUIRES_PARTNER_IDENTITY_REVIEW",
            )

    def test_bundle_round_trip_preserves_core_representation_semantics(self):
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        core = from_jurisdiction_package(package)
        expected = core_semantic_projection(core)
        with tempfile.TemporaryDirectory() as tmp:
            bundle, _, _, _ = self.build(Path(tmp))
        self.assertEqual(round_trip_semantic_projection(bundle), expected)

    def test_manifest_pins_source_adapter_and_partner_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, manifest, _, _ = self.build(Path(tmp))
        self.assertEqual(validate_manifest(manifest), [])
        verify_payload(manifest, bundle)
        self.assertEqual(manifest["producer"]["adapter_version"], ADAPTER_VERSION)
        self.assertEqual(
            manifest["canonical_data_versions"]["civicpatch_open_data"],
            f"CivicPatch/open-data@{CIVICPATCH_OPEN_DATA_COMMIT}",
        )
        self.assertEqual(
            manifest["canonical_data_versions"]["civicpatch_tools"],
            f"CivicPatch/civicpatch-tools@{CIVICPATCH_TOOLS_COMMIT}",
        )
        self.assertEqual(manifest["certification"]["status"], "certified")
        self.assertTrue(manifest["scope"]["complete_jurisdiction"])

    def test_pinned_civicpatch_drift_is_reported_without_identity_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, drift, _ = self.build(Path(tmp))
        self.assertFalse(drift["identity_resolution_performed"])
        self.assertEqual(drift["current_count"], 7)
        self.assertEqual(drift["candidate_count"], 7)
        self.assertEqual(
            drift["shared_names"],
            ["Braden Brent", "Crystann Benson", "Jared Jefferson"],
        )
        self.assertEqual(
            drift["candidate_only_names"],
            ["Annette Bowin", "Joe Tarnow", "Ron Kraich", "Terry Alexander"],
        )
        self.assertEqual(
            drift["current_only_names"],
            ["Ariella Gonzales-Vondy", "Brandon Hill", "David Kembel", "Jennifer Hansen"],
        )
        self.assertEqual(
            drift["role_differences_on_shared_names"],
            [{
                "name": "Jared Jefferson",
                "current_role_ids": ["mayor-pro-tempore"],
                "candidate_role_ids": ["trustee"],
            }],
        )

    def test_generated_artifacts_are_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            build_artifacts(Path(a))
            build_artifacts(Path(b))
            for name in (BUNDLE_NAME, YAML_NAME, MANIFEST_NAME, DRIFT_NAME):
                with self.subTest(name=name):
                    self.assertEqual(
                        (Path(a) / name).read_bytes(),
                        (Path(b) / name).read_bytes(),
                    )

    def test_yaml_candidate_has_civicpatch_publish_shape_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, yaml_text = self.build(Path(tmp))
        self.assertIn("- id: '", yaml_text)
        self.assertIn("  name: 'Annette Bowin'", yaml_text)
        self.assertIn(
            "    jurisdiction_ocdid: 'ocd-jurisdiction/country:us/state:co/place:akron/government'",
            yaml_text,
        )
        self.assertIn(
            "    division_ocdid: 'ocd-division/country:us/state:co/place:akron'",
            yaml_text,
        )
        self.assertIn("    role_id: 'trustee'", yaml_text)
        self.assertIn("    start_date: null", yaml_text)
        self.assertIn("    end_date: null", yaml_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
