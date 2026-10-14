"""Synthetic count fixtures and compatibility controls; no new civic facts."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from adapters.factory.count_contract import CountContractError, assess_factory_counts
from adapters.factory.export_representation import ExportError, export_factory_package

ROOT = Path(__file__).resolve().parents[1]
BJ = "jurisdiction-tx-09640"
VJ = "jurisdiction-vt-cousub-5000975175"


def fixture(jid=BJ):
    sizes = [1, 2, 2, 2] if jid == BJ else [3]
    basis = "OFFICE_CONTAINERS" if jid == BJ else "SEAT_CAPACITY"
    offices = [{"office_id": f"synthetic-office-{n}", "jurisdiction_id": jid, "status": "ACTIVE", "seats": seats, "occupancy_status": "FILLED"} for n, seats in enumerate(sizes)]
    terms = [{"role_term_id": f"synthetic-role-{n}-{m}", "person_id": f"synthetic-person-{n}-{m}", "office_id": office["office_id"], "jurisdiction_id": jid, "status": "CURRENT"} for n, office in enumerate(offices) for m in range(office["seats"])]
    return {"jurisdiction": {"jurisdiction_id": jid, "name": "Synthetic count fixture"}, "records": {"divisions": [], "bodies": [], "offices": offices, "people": [], "role_terms": terms}, "qa": {"factory_count_contract": {"schema": "CIVIC_FACTORY_COUNT_CONTRACT_v0.1", "jurisdiction_id": jid, "scope": "ACTIVE_OFFICES_CURRENT_ROLE_TERMS", "tracker_count_basis": basis, "active_offices": len(offices) if basis == "OFFICE_CONTAINERS" else sum(sizes), "current_role_terms": len(terms), "vacant_offices": 0, "source_workbook_sha256": "1" * 64}}}


class FactoryCountContractTests(unittest.TestCase):
    def test_container_profile_separates_four_containers_from_seven_seats(self):
        r = assess_factory_counts(fixture())
        self.assertEqual((r["active_office_containers"], r["seat_capacity"], r["current_role_terms"]), (4, 7, 7))

    def test_seat_profile_preserves_one_container_three_seats(self):
        r = assess_factory_counts(fixture(VJ))
        self.assertEqual((r["active_office_containers"], r["seat_capacity"], r["current_role_terms"]), (1, 3, 3))

    def test_unknown_jurisdiction_without_sidecar_has_no_new_gate(self):
        self.assertIsNone(assess_factory_counts({"jurisdiction": {"jurisdiction_id": "jurisdiction-test-unprofiled"}}))
        with self.assertRaises(CountContractError):
            assess_factory_counts({"jurisdiction": {"jurisdiction_id": "jurisdiction-test-unprofiled"}, "qa": {"factory_count_contract": None}})

    def test_profiled_jurisdiction_requires_sidecar(self):
        p = fixture(); p["qa"].pop("factory_count_contract")
        with self.assertRaisesRegex(CountContractError, "required"):
            assess_factory_counts(p)

    def test_wrong_basis_is_rejected_even_if_counter_matches_capacity(self):
        p = fixture(); p["qa"]["factory_count_contract"].update(tracker_count_basis="SEAT_CAPACITY", active_offices=7)
        with self.assertRaisesRegex(CountContractError, "basis"):
            assess_factory_counts(p)

    def test_invalid_tracker_integer_values_are_rejected(self):
        for field in ["active_offices", "current_role_terms", "vacant_offices"]:
            for value in [None, "", True, -1, 1.5, "NaN", "Infinity"]:
                with self.subTest(field=field, value=value):
                    p = fixture(); p["qa"]["factory_count_contract"][field] = value
                    with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_invalid_seats_cannot_be_truncated_or_filled_from_tracker(self):
        for value in [None, "", True, 0, -1, 1.5, "NaN", "Infinity"]:
            with self.subTest(value=value):
                p = fixture(); p["records"]["offices"][0]["seats"] = value
                with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_integer_float_seats_are_accepted_without_rounding(self):
        p = fixture(); p["records"]["offices"][0]["seats"] = 1.0
        self.assertEqual(assess_factory_counts(p)["seat_capacity"], 7)

    def test_counter_drift_is_rejected(self):
        for field in ["active_offices", "current_role_terms", "vacant_offices"]:
            with self.subTest(field=field):
                p = fixture(); p["qa"]["factory_count_contract"][field] += 1
                with self.assertRaisesRegex(CountContractError, "counts disagree"): assess_factory_counts(p)

    def test_missing_current_role_is_rejected_even_with_adjusted_counter(self):
        p = fixture(); p["records"]["role_terms"].pop(); p["qa"]["factory_count_contract"]["current_role_terms"] -= 1
        with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_missing_office_or_broken_current_link_is_rejected(self):
        for mutation in [lambda p: p["records"]["offices"].pop(), lambda p: p["records"]["role_terms"][0].update(office_id="superseded-synthetic-id")]:
            p = fixture(); mutation(p)
            with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_duplicate_office_role_or_person_occupancy_is_rejected(self):
        for mutation in [lambda p: p["records"]["offices"].append(deepcopy(p["records"]["offices"][0])), lambda p: p["records"]["role_terms"].append(deepcopy(p["records"]["role_terms"][0])), lambda p: p["records"]["role_terms"][2].update(person_id=p["records"]["role_terms"][1]["person_id"])]:
            p = fixture(); mutation(p)
            with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_occupied_vacant_unknown_or_overfilled_office_is_rejected(self):
        for mutation in [lambda p: p["records"]["offices"][0].update(occupancy_status="VACANT"), lambda p: p["records"]["offices"][0].update(occupancy_status="UNKNOWN"), lambda p: p["records"]["role_terms"][-1].update(office_id=p["records"]["offices"][0]["office_id"])]:
            p = fixture(); mutation(p)
            with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_explicit_two_seat_vacancy_reconciles(self):
        p = fixture(); office = p["records"]["offices"][1]; office["occupancy_status"] = "VACANT"
        p["records"]["role_terms"] = [r for r in p["records"]["role_terms"] if r["office_id"] != office["office_id"]]
        p["qa"]["factory_count_contract"].update(current_role_terms=5, vacant_offices=2)
        r = assess_factory_counts(p)
        self.assertEqual((r["seat_capacity"], r["current_role_terms"], r["explicit_vacant_seats"]), (7, 5, 2))

    def test_conflicting_seat_alias_is_rejected(self):
        p = fixture(); p["records"]["offices"][0]["seat_count"] = 2
        with self.assertRaisesRegex(CountContractError, "Conflicting"): assess_factory_counts(p)

    def test_mixed_jurisdiction_or_inactive_scope_is_rejected(self):
        for table, field, value in [("offices", "jurisdiction_id", VJ), ("role_terms", "jurisdiction_id", VJ), ("offices", "status", "SUPERSEDED"), ("role_terms", "status", "FORMER")]:
            p = fixture(); p["records"][table][0][field] = value
            with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_contract_binding_and_source_hash_are_required(self):
        for field, value in [("schema", "UNKNOWN"), ("jurisdiction_id", VJ), ("scope", "ALL_HISTORY"), ("source_workbook_sha256", ""), ("source_workbook_sha256", "F" * 64)]:
            p = fixture(); p["qa"]["factory_count_contract"][field] = value
            with self.assertRaises(CountContractError): assess_factory_counts(p)

    def test_registry_malformed_missing_duplicates_or_bad_profile_stop_export(self):
        from adapters.factory import count_contract as cc
        valid = json.loads(cc.PROFILES_PATH.read_text())
        bad = deepcopy(valid); bad["profiles"][BJ]["tracker_count_basis"] = []
        for raw in [b"{", b'{"schema":"one","schema":"two"}', json.dumps(bad).encode()]:
            with patch.object(cc, "PROFILES_PATH") as path:
                path.read_bytes.return_value = raw
                with self.assertRaises(CountContractError): assess_factory_counts(fixture())
        with patch.object(cc, "PROFILES_PATH") as path:
            path.read_bytes.side_effect = FileNotFoundError()
            with self.assertRaises(CountContractError): assess_factory_counts(fixture())

    def test_assessment_never_mutates_source_records_or_approval(self):
        p = fixture(); p["qa"]["approved_by"] = "Synthetic approval fixture"; before = deepcopy(p)
        assess_factory_counts(p)
        self.assertEqual(p, before)

    def test_row_order_does_not_change_count_diagnostic(self):
        p = fixture(); before = assess_factory_counts(p)
        p["records"]["offices"].reverse(); p["records"]["role_terms"].reverse()
        self.assertEqual(assess_factory_counts(p), before)

    def test_exporter_enforces_count_gate_before_crosswalk_and_preserves_crosswalk_hold(self):
        p = fixture(); p["qa"]["factory_count_contract"]["active_offices"] = 7
        with self.assertRaisesRegex(ExportError, "Factory count contract"): export_factory_package(p)
        for jid in [BJ, VJ]:
            with self.assertRaisesRegex(ExportError, "governed jurisdiction OCDID/crosswalk"): export_factory_package(fixture(jid))

    def test_five_existing_colorado_payloads_remain_exactly_identical(self):
        paths = sorted((ROOT / "data/normalized/co").glob("*/jurisdiction.json"))
        self.assertEqual(len(paths), 5)
        for path in paths:
            with self.subTest(jurisdiction=path.parent.name):
                p = json.loads(path.read_text())
                self.assertIsNone(assess_factory_counts(p))
                output = export_factory_package(p, generated_at="2026-10-14T12:43:19Z")
                with patch("adapters.factory.export_representation.assess_factory_counts", return_value=None):
                    legacy_output = export_factory_package(p, generated_at="2026-10-14T12:43:19Z")
                self.assertEqual(output, legacy_output)


if __name__ == "__main__":
    unittest.main()
