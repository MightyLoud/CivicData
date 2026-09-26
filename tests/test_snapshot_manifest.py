from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.snapshot_manifest import (
    SnapshotManifestError,
    build_manifest,
    same_governed_snapshot,
    validate_manifest,
    verify_payload,
)

FIXTURES = ROOT / "acceptance" / "representation" / "snapshot_manifest"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SnapshotManifestTests(unittest.TestCase):
    def test_factory_example_manifest_and_payload_verify(self):
        manifest = load("factory-example.manifest.json")
        payload = load("factory-example.json")
        self.assertEqual(validate_manifest(manifest), [])
        verify_payload(manifest, payload)
        self.assertEqual(manifest["producer"]["system"], "jurisdiction_factory")
        self.assertEqual(manifest["certification"]["status"], "certified")

    def test_civicpatch_example_manifest_and_payload_verify(self):
        manifest = load("civicpatch-example.manifest.json")
        payload = load("civicpatch-example.json")
        self.assertEqual(validate_manifest(manifest), [])
        verify_payload(manifest, payload)
        self.assertEqual(manifest["producer"]["system"], "civicpatch")
        self.assertEqual(manifest["certification"]["status"], "uncertified")

    def test_builder_reproduces_committed_factory_manifest(self):
        payload = load("factory-example.json")
        expected = load("factory-example.manifest.json")
        actual = build_manifest(
            payload=payload,
            payload_locator="factory-example.json",
            payload_media_type="application/json",
            schema_version="representation-contract/1.0.0-draft",
            generated_at="2026-09-25T18:00:00Z",
            producer_system="jurisdiction_factory",
            adapter_version="factory-representation/0.1",
            source_snapshots=[{
                "system": "jurisdiction_factory",
                "snapshot_id": "CO-AKRON-2026-08-19",
                "locator": "data/normalized/co/jurisdiction-co-akron/jurisdiction.json",
            }],
            jurisdiction_ocdid=(
                "ocd-jurisdiction/country:us/state:co/place:akron/government"
            ),
            division_ocdids=[
                "ocd-division/country:us/state:co/place:akron"
            ],
            complete_jurisdiction=True,
            certification={
                "status": "certified",
                "raw_complete": True,
                "normalized_complete": True,
                "qa_passed": True,
                "parity_ok": True,
                "verified_at": "2026-08-19T00:00:00Z",
            },
            canonical_data_versions={
                "ocdid": (
                    "openstates/jurisdictions@"
                    "2301513c99d275cca23cbcdf04aba09dbced3247"
                ),
                "identity_registry": "shared-identity/0.1",
            },
        )
        self.assertEqual(actual, expected)

    def test_content_hash_changes_when_payload_changes(self):
        payload = load("factory-example.json")
        manifest = load("factory-example.manifest.json")
        changed = deepcopy(payload)
        changed["people"][0]["name"] = "Jared Jefferson Jr."
        with self.assertRaisesRegex(
            SnapshotManifestError,
            "PAYLOAD_(BYTES|HASH)_MISMATCH",
        ):
            verify_payload(manifest, changed)

        rebuilt = build_manifest(
            payload=changed,
            payload_locator="factory-example.json",
            payload_media_type="application/json",
            schema_version=manifest["schema_version"],
            generated_at=manifest["generated_at"],
            producer_system=manifest["producer"]["system"],
            adapter_version=manifest["producer"]["adapter_version"],
            source_snapshots=manifest["source_snapshots"],
            jurisdiction_ocdid=manifest["scope"]["jurisdiction_ocdid"],
            division_ocdids=manifest["scope"]["division_ocdids"],
            complete_jurisdiction=manifest["scope"]["complete_jurisdiction"],
            certification=manifest["certification"],
            canonical_data_versions=manifest["canonical_data_versions"],
        )
        self.assertNotEqual(
            rebuilt["payload"]["content_sha256"],
            manifest["payload"]["content_sha256"],
        )
        self.assertNotEqual(
            rebuilt["manifest_sha256"],
            manifest["manifest_sha256"],
        )

    def test_schema_version_change_changes_governed_snapshot(self):
        manifest = load("factory-example.manifest.json")
        rebuilt = build_manifest(
            payload=load("factory-example.json"),
            payload_locator=manifest["payload"]["locator"],
            payload_media_type=manifest["payload"]["media_type"],
            schema_version="representation-contract/1.0.1-draft",
            generated_at=manifest["generated_at"],
            producer_system=manifest["producer"]["system"],
            adapter_version=manifest["producer"]["adapter_version"],
            source_snapshots=manifest["source_snapshots"],
            jurisdiction_ocdid=manifest["scope"]["jurisdiction_ocdid"],
            division_ocdids=manifest["scope"]["division_ocdids"],
            complete_jurisdiction=manifest["scope"]["complete_jurisdiction"],
            certification=manifest["certification"],
            canonical_data_versions=manifest["canonical_data_versions"],
        )
        self.assertFalse(same_governed_snapshot(manifest, rebuilt))

    def test_adapter_version_change_changes_governed_snapshot(self):
        manifest = load("factory-example.manifest.json")
        rebuilt = build_manifest(
            payload=load("factory-example.json"),
            payload_locator=manifest["payload"]["locator"],
            payload_media_type=manifest["payload"]["media_type"],
            schema_version=manifest["schema_version"],
            generated_at=manifest["generated_at"],
            producer_system=manifest["producer"]["system"],
            adapter_version="factory-representation/0.2",
            source_snapshots=manifest["source_snapshots"],
            jurisdiction_ocdid=manifest["scope"]["jurisdiction_ocdid"],
            division_ocdids=manifest["scope"]["division_ocdids"],
            complete_jurisdiction=manifest["scope"]["complete_jurisdiction"],
            certification=manifest["certification"],
            canonical_data_versions=manifest["canonical_data_versions"],
        )
        self.assertFalse(same_governed_snapshot(manifest, rebuilt))

    def test_source_snapshot_change_changes_governed_snapshot(self):
        manifest = load("factory-example.manifest.json")
        source = deepcopy(manifest["source_snapshots"])
        source[0]["snapshot_id"] = "CO-AKRON-2026-09-25"
        rebuilt = build_manifest(
            payload=load("factory-example.json"),
            payload_locator=manifest["payload"]["locator"],
            payload_media_type=manifest["payload"]["media_type"],
            schema_version=manifest["schema_version"],
            generated_at=manifest["generated_at"],
            producer_system=manifest["producer"]["system"],
            adapter_version=manifest["producer"]["adapter_version"],
            source_snapshots=source,
            jurisdiction_ocdid=manifest["scope"]["jurisdiction_ocdid"],
            division_ocdids=manifest["scope"]["division_ocdids"],
            complete_jurisdiction=manifest["scope"]["complete_jurisdiction"],
            certification=manifest["certification"],
            canonical_data_versions=manifest["canonical_data_versions"],
        )
        self.assertFalse(same_governed_snapshot(manifest, rebuilt))

    def test_missing_required_field_is_rejected(self):
        manifest = load("factory-example.manifest.json")
        manifest.pop("schema_version")
        self.assertIn("MANIFEST_REQUIRED_FIELDS", validate_manifest(manifest))

    def test_missing_adapter_version_is_rejected(self):
        manifest = load("factory-example.manifest.json")
        manifest["producer"]["adapter_version"] = ""
        manifest["manifest_sha256"] = "0" * 64
        self.assertIn("PRODUCER_REQUIRED_FIELDS", validate_manifest(manifest))

    def test_certified_requires_all_gates(self):
        manifest = load("factory-example.manifest.json")
        manifest["certification"]["qa_passed"] = False
        manifest["manifest_sha256"] = "0" * 64
        self.assertIn("CERTIFIED_GATES_INCOMPLETE", validate_manifest(manifest))

    def test_manifest_hash_detects_metadata_tampering(self):
        manifest = load("factory-example.manifest.json")
        manifest["producer"]["adapter_version"] = "tampered/9.9"
        self.assertIn("MANIFEST_HASH_MISMATCH", validate_manifest(manifest))

    def test_generated_and_verified_times_must_be_offset_aware(self):
        manifest = load("factory-example.manifest.json")
        manifest["generated_at"] = "2026-09-25T18:00:00"
        manifest["certification"]["verified_at"] = "2026-08-19T00:00:00"
        manifest["manifest_sha256"] = "0" * 64
        errors = validate_manifest(manifest)
        self.assertIn("GENERATED_AT_INVALID", errors)
        self.assertIn("CERTIFICATION_VERIFIED_AT_INVALID", errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
