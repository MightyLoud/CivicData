"""Committed successor Texas package/receipt controls; activation does not rewrite the source package."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import package_catalog, production_profile, representation
from tools.jurisdiction_package import canonical_json
from tools.texas_successor_contract import build_successor_contract

DATA = ROOT / "data" / "packages" / "tx" / "legislative"
ARCHIVE_BASENAME = "Tx_Legislative_Two_Office_v0.1.zip.b64.part"
ACTIVE_ENTRY_SHA = "1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_json(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class TexasSuccessorPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads((DATA / "successor-package-metadata-v0.1.json").read_text(encoding="utf-8"))
        cls.receipt = json.loads((DATA / "acceptance-v0.1.json").read_text(encoding="utf-8"))
        cls.snapshot = json.loads((DATA / "source-snapshot-v0.1.json").read_text(encoding="utf-8"))
        parts = sorted(DATA.glob(ARCHIVE_BASENAME + "*"))
        assert len(parts) == cls.meta["archive_part_count"] == 4
        encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
        cls.archive_bytes = base64.b64decode(encoded, validate=True)
        cls.tmp = tempfile.TemporaryDirectory()
        archive_path = Path(cls.tmp.name) / "package.zip"
        archive_path.write_bytes(cls.archive_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(cls.tmp.name)
        cls.package_dir = Path(cls.tmp.name) / "Tx_Legislative_Two_Office_v0.1" / "package"
        cls.package = json.loads((cls.package_dir / "jurisdiction.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_archive_and_package_hashes_match_committed_metadata(self):
        self.assertEqual(len(self.archive_bytes), self.meta["archive_bytes"])
        self.assertEqual(sha(self.archive_bytes), self.meta["archive_sha256"])
        package_bytes = (self.package_dir / "jurisdiction.json").read_bytes()
        self.assertEqual(sha(package_bytes), self.meta["jurisdiction_json_sha256"])
        self.assertEqual(sha((DATA / "acceptance-v0.1.json").read_bytes()), self.meta["acceptance_receipt_sha256"])
        self.assertEqual(self.receipt["deterministic_sha256"], self.meta["acceptance_deterministic_sha256"])

    def test_receipt_rebuilds_deterministically_from_exact_successor_package(self):
        divisions = {row["division_kind"]: row["division_id"] for row in self.package["records"]["divisions"]}
        rebuilt = build_successor_contract(
            (self.package_dir / "jurisdiction.json").read_bytes(),
            historical_live_evidence_sha256=self.meta["historical_live_evidence_sha256"],
            historical_live_tested_commit=self.meta["historical_live_tested_commit"],
            runtime_zip_sha256=self.receipt["inputs"]["runtime_zip_sha256"],
            identity_resolution_head=self.meta["identity_resolution_head"],
            source_workbook_id=self.meta["source_workbook_id"],
            source_workbook_modified_time=self.meta["source_workbook_modified_time"],
            house_division_id=divisions["SLDL"],
            senate_division_id=divisions["SLDU"],
        )
        self.assertEqual(rebuilt, self.receipt)

    def test_profile_loader_accepts_exact_successor_without_rewriting_source_qa(self):
        loaded = production_profile.load_profile_package(
            self.package_dir,
            profile_id=production_profile.PROFILE_ID,
            acceptance_receipt=self.receipt,
            bindings=self.receipt["scope"]["bindings"],
        )
        self.assertEqual({row["identity_resolution_status"] for row in loaded["records"]["people"]}, {"AUTHORITATIVE"})
        self.assertEqual({row["role_term_status"] for row in loaded["records"]["role_terms"]}, {"CURRENT"})
        self.assertEqual({row["term_start_date"] for row in loaded["records"]["role_terms"]}, {"2025-01-14"})
        self.assertEqual({row["term_end_date"] for row in loaded["records"]["role_terms"]}, {""})
        self.assertEqual(loaded["qa"]["blocking_gap_count"], 5)
        self.assertEqual(loaded["qa"]["address_tests"], [])
        self.assertFalse(loaded["qa"]["complete_jurisdiction"])
        self.assertFalse(loaded["qa"]["publication_eligible"])

    def test_two_binding_representation_replays_current_authoritative_civic_facts(self):
        jid = self.package["jurisdiction"]["jurisdiction_id"]
        gps = {"payload": {"jurisdictions": [{"jurisdiction_id": jid}], "district_assignments": [
            {"adapter_id": "DIST-TX-HOUSE-H2316", "district_key": "49"},
            {"adapter_id": "DIST-TX-SENATE-S2168", "district_key": "14"},
        ]}}
        preview = representation.preview_representation_for_bindings(
            self.package, "SYNTHETIC SUCCESSOR REPLAY", gps, bindings=self.receipt["scope"]["bindings"])
        self.assertEqual(preview["status"], "PASS")
        self.assertEqual(len(preview["projections"]), 2)
        holders = [projection["representation"]["applicable_offices"][0]["holders"][0]
                   for projection in preview["projections"]]
        self.assertEqual({holder["person_status"] for holder in holders}, {"AUTHORITATIVE"})
        self.assertEqual({holder["term_start"] for holder in holders}, {"2025-01-14"})
        self.assertEqual({holder["term_end"] for holder in holders}, {None})

    def test_receipt_carries_old_live_evidence_only_as_geography_evidence(self):
        acceptance = self.receipt["acceptance"]
        self.assertEqual(acceptance["geometry_evidence_reuse_scope"], "GEOGRAPHY_ONLY__NO_OLD_REPRESENTATION_REPLAY")
        self.assertEqual(self.receipt["gate_disposition"]["PUBLIC_PERSON_IDENTITY"], "RESOLVED_AUTHORITATIVE")
        self.assertFalse(self.receipt["production_release_eligible"])
        self.assertFalse(self.receipt["publication_eligible"])
        self.assertEqual(self.receipt["canonical_writes"], 0)

    def test_default_catalog_activates_only_the_exact_certified_successor_profile(self):
        entries = package_catalog.load_catalog()["entries"]
        matches = [
            row for row in entries
            if row.get("profile") == "state_legislative_representation"
            and (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
        ]
        self.assertEqual(len(matches), 1)
        entry = matches[0]
        self.assertEqual(entry["entry_id"], "tx-legislative-two-office-v0.1-hosted-candidate")
        self.assertEqual(sha_json(entry), ACTIVE_ENTRY_SHA)
        reconstructed = package_catalog.reconstruct_package(entry, ROOT)
        self.assertEqual(reconstructed, self.package)


if __name__ == "__main__":
    unittest.main(verbosity=2)
