"""Publication controls for explicit provisional Person identities."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import package_source, representation
from test_role_term_integration import bindings, fixture, gps
from tools import jurisdiction_package as builder


def resolved_fixture():
    package = fixture()
    for person in package["records"]["people"]:
        person.pop("person_status", None)
        person.pop("identity_resolution_status", None)
        person.pop("status", None)
        person.pop("current_status", None)
    package["warnings"] = []
    return package


class PublicIdentityDispositionTests(unittest.TestCase):
    def test_internal_package_validation_retains_provisional_people(self):
        package = fixture()
        before = copy.deepcopy(package)
        self.assertEqual(builder.validate(package), [])
        self.assertEqual(package, before)

    def test_explicit_provisional_people_are_publication_blockers(self):
        errors = builder.validate_public_identity_disposition(fixture())
        self.assertEqual(errors, [
            "provisional_person:test-person-house",
            "provisional_person:test-person-senate",
        ])

    def test_every_supported_identity_status_alias_blocks(self):
        for alias in ("person_status", "identity_resolution_status", "status", "current_status"):
            with self.subTest(alias=alias):
                package = resolved_fixture()
                package["records"]["people"][0][alias] = " provisional "
                self.assertEqual(
                    builder.validate_public_identity_disposition(package),
                    ["provisional_person:test-person-house"],
                )

    def test_provisional_warning_blocks_even_if_person_status_is_omitted(self):
        package = resolved_fixture()
        package["warnings"] = [{
            "warning_id": "PROVISIONAL-PERSON:test-person-house",
            "person_id": "test-person-house",
            "status": "PROVISIONAL",
            "scope": "INTERNAL_REVIEW",
        }]
        self.assertEqual(
            builder.validate_public_identity_disposition(package),
            ["provisional_warning:test-person-house"],
        )

    def test_legacy_statusless_package_remains_compatible(self):
        package = resolved_fixture()
        self.assertEqual(builder.validate_public_identity_disposition(package), [])
        projection = package_source.representation_projection(package)
        self.assertEqual(projection["status"], "PASS")
        self.assertEqual(projection["people"], package["records"]["people"])

    def test_production_loader_rejects_provisional_package_after_valid_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder.build(fixture(), root)
            with self.assertRaises(package_source.PackageContractError) as error:
                package_source.load_jurisdiction_package(root)
            self.assertEqual(error.exception.code, "PACKAGE_PUBLIC_IDENTITY_UNRESOLVED")
            self.assertIn("test-person-house", error.exception.detail)
            self.assertIn("test-person-senate", error.exception.detail)

    def test_direct_public_projection_and_full_essentials_entry_fail_closed(self):
        package = fixture()
        for call in (
            lambda: package_source.representation_projection(package),
            lambda: package_source.require_full_essentials(package),
        ):
            with self.subTest(call=call):
                with self.assertRaises(package_source.PackageContractError) as error:
                    call()
                self.assertEqual(error.exception.code, "PACKAGE_PUBLIC_IDENTITY_UNRESOLVED")

    def test_internal_preview_remains_non_public_and_default_consumer_still_rejects(self):
        package = fixture()
        preview = representation.preview_representation_for_bindings(
            package, "SYNTHETIC INPUT", gps(), bindings=bindings()
        )
        self.assertEqual(preview["status"], "PASS")
        self.assertFalse(preview["publication_eligible"])
        direct = representation.build_representation_from_civic_gps_result(
            package, "SYNTHETIC INPUT", gps(), binding=bindings()[0]
        )
        self.assertEqual(direct["error"], "PERSON_IDENTITY_PROVISIONAL")


if __name__ == "__main__":
    unittest.main()
