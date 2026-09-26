"""Regression controls for the bounded HI snapshot and published identities."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import hi_factory_refresh as hi


class HawaiiRefresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(hi.SNAPSHOT.read_text())

    def test_all_five_packages_and_exact_counts(self):
        packages = [hi.package(self.snapshot, county) for county in hi.COUNTIES]
        self.assertEqual(sum(len(p["records"]["role_terms"]) for p in packages), 38)
        self.assertEqual(sum(len(p["provenance"]["source_evidence"]) for p in packages), 43)
        self.assertEqual(sum(len(p["provenance"]["source_assertions"]) for p in packages), 82)
        self.assertEqual(sum(len(p["qa"]["checks"]) for p in packages), 83)
        self.assertTrue(all(not hi.jp.validate(p) for p in packages))

    def test_review_candidates_do_not_change_consumer_discovery(self):
        from tools.ev_onboarding_proposal import discover_package
        for county in hi.COUNTIES:
            jid = f"jurisdiction-hi-{county}-county"
            _, artifact = discover_package(hi.ROOT, jid)
            self.assertEqual(artifact["archive_sha256"], hi.BASE_HASHES[county])
            self.assertTrue(artifact["parts_glob"].startswith("data/packages/hi/"))

    def test_false_tracker_gate_is_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tables"]["00_Batch_Status"]["rows"][0]["values"]["freshness_ok"] = False
        with self.assertRaisesRegex(ValueError, "tracker gate"):
            hi.package(snapshot, "hawaii")

    def test_holder_replacement_is_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        terms = snapshot["tables"]["06_RoleTerm"]["rows"]
        terms[0]["values"]["person_id"] = terms[1]["values"]["person_id"]
        with self.assertRaisesRegex(ValueError, "holder/interval drift"):
            hi.package(snapshot, "hawaii")

    def test_batangan_cannot_revert_to_elected(self):
        snapshot = copy.deepcopy(self.snapshot)
        for item in snapshot["tables"]["06_RoleTerm"]["rows"]:
            if item["values"]["role_term_id"] == "role-hi-maui-kauanoe-batangan":
                item["values"]["selection_type"] = "ELECTED"
        with self.assertRaisesRegex(ValueError, "selection method drift"):
            hi.package(snapshot, "maui")

    def test_obsolete_assertion_subject_is_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        for item in snapshot["tables"]["09_SourceAssertion"]["rows"]:
            if item["values"]["assertion_id"] == "asrt-hi-raw001-kauai-council-mel-rapozo":
                item["values"]["subject_id"] = "office-hi-kauai-council-at-large-1"
        with self.assertRaisesRegex(ValueError, "assertion_subject_fk"):
            hi.package(snapshot, "kauai")


if __name__ == "__main__":
    unittest.main()
