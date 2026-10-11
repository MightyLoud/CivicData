"""Synthetic compatibility tests, never real Eagle address acceptance."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import jurisdiction_package as generic, jurisdiction_package_strict as strict
from tools import co_factory_export as producer
from tools.canonical_representation_core import from_jurisdiction_package, validate_core
from tools.shared_authority_dependencies import include_reviewed_dependencies, SharedAuthorityError
from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote import package_source, representation, representation_catalog, contract_v1


def fixture(capacity=6, allocation=3):
    data = json.loads((ROOT / "tests/fixtures/shared_authority/synthetic.json").read_text())
    package, policy = data["package"], data["reviewed_dependencies"]
    package["records"]["offices"][0]["seats"] = allocation
    policy["represented_offices"][0]["seats"] = allocation
    policy["body_capacities"]["synthetic-shared-body"] = capacity
    return package, policy


def snapshot(package, policy):
    rows = {name: copy.deepcopy(value) for name, value in package["records"].items()}
    rows.update(copy.deepcopy(package["provenance"]))
    rows["jurisdictions"] = [copy.deepcopy(package["jurisdiction"])] + copy.deepcopy(policy["jurisdictions"])
    mapping = {name: table for name, (table, _) in producer.TABLE_MAP.items()}
    mapping.update(jurisdictions="01_Jurisdiction", source_evidence="08_SourceEvidence", source_assertions="09_SourceAssertion")
    tables = {}
    for name, native in mapping.items():
        values = rows[name]
        columns = sorted({key for row in values for key in row})
        # Preserve sparse native records exactly while satisfying the producer's
        # declared column-order invariant. No missing fields are fabricated.
        if values and any(set(row) != set(columns) for row in values):
            columns = list(values[0])
        tables[native] = {"columns": columns, "rows": [{"source_row": i + 2, "values": row} for i, row in enumerate(values)]}
    for native, values in (("11_KnownGap", []), ("12_AddressTest", package["qa"]["address_tests"]), ("13_QA", package["qa"]["checks"])):
        tables[native] = {"columns": list(values[0]) if values else [], "rows": [{"source_row": i + 2, "values": row} for i, row in enumerate(values)]}
    return {"tables": tables}, rows


def gps(jid="synthetic-gps"):
    return {"payload": {"jurisdictions": [{"jurisdiction_id": jid}], "district_assignments": [],
                        "officeholders": [{"person_id": "poison-gps-person"}]}}


def render(package, policy=None, result=None):
    return representation.build_representation_from_civic_gps_result(
        package, "Synthetic address, not geocoded", gps() if result is None else result,
        binding={"package_jurisdiction_id": "jurisdiction-test", "civic_gps_jurisdiction_id": "synthetic-gps"},
        reviewed_dependencies=policy)


class SharedAuthorityTests(unittest.TestCase):
    def rejected(self, package, policy):
        self.assertTrue(generic.validate(package, reviewed_dependencies=policy))
        self.assertTrue(strict.validate(package, reviewed_dependencies=policy))
        for convert in (from_jurisdiction_package, export_factory_package):
            with self.assertRaises(ValueError):
                convert(package, reviewed_dependencies=policy)
        self.assertEqual(render(package, policy)["status"], "FAIL-CLOSED")

    def test_capacity_identity_and_existing_schemas(self):
        import jsonschema
        for capacity, allocation in ((6, 3), (11, 2)):
            with self.subTest(capacity=capacity):
                package, policy = fixture(capacity, allocation)
                self.assertEqual(generic.validate(package, reviewed_dependencies=policy), [])
                self.assertEqual(strict.validate(package, reviewed_dependencies=policy), [])
                core = from_jurisdiction_package(package, reviewed_dependencies=policy)
                contract = export_factory_package(package, generated_at="2026-10-11T00:00:00Z", reviewed_dependencies=policy)
                self.assertEqual(validate_core(core), [])
                self.assertEqual(contract_v1.validate_contract(contract, require_certified=False), [])
                self.assertIn("CONTRACT_NOT_CERTIFIED", contract_v1.validate_contract(contract, require_certified=True))
                self.assertNotEqual(core["certification"]["status"], "certified")
                for value, schema in ((package, "jurisdiction_package_v0.1"), (core, "canonical_representation_core_v0.1"), (contract, "representation_contract_v1")):
                    jsonschema.validate(value, json.loads((ROOT / "schemas" / (schema + ".schema.json")).read_text()))
                institutional = policy["jurisdictions"][0]["ocd_jurisdiction_id"]
                self.assertEqual(core["organizations"][0]["jurisdiction_ocdid"], institutional)
                self.assertEqual(contract["organizations"][0]["jurisdiction_ocdid"], institutional)
                self.assertEqual(contract["posts"][0]["jurisdiction_ocdid"], package["jurisdiction"]["ocd_jurisdiction_id"])
                model = render(package, policy)
                self.assertEqual(model["status"], "PASS", model)
                office = model["applicable_offices"][0]
                self.assertEqual((office["organization_seat_capacity"], office["seat_capacity"]), (capacity, allocation))
                self.assertEqual(office["body_id"], "synthetic-shared-body")
                self.assertEqual(office["represented_jurisdiction_id"], "jurisdiction-test")

    def test_institutional_jurisdiction_assertion_is_retained(self):
        package, policy = fixture()
        assertion = copy.deepcopy(package["provenance"]["source_assertions"][0])
        assertion.update(assertion_id="institution-identity", subject_type="Jurisdiction", subject_id=policy["jurisdictions"][0]["jurisdiction_id"])
        package["provenance"]["source_assertions"].append(assertion)
        policy["provenance"]["source_assertions"].append(copy.deepcopy(assertion))
        contract = export_factory_package(package, reviewed_dependencies=policy)
        self.assertEqual(contract_v1.validate_contract(contract, require_certified=False), [])
        institution = policy["jurisdictions"][0]["ocd_jurisdiction_id"]
        self.assertTrue(any(row["subject_type"] == "jurisdiction" and row["subject_id"] == institution for row in contract["assertions"]))
        core = from_jurisdiction_package(package, reviewed_dependencies=policy)
        self.assertTrue(any(row["subject_type"] == "jurisdiction" and row["subject_id"] == institution for row in core["assertions"]))
        contract["assertions"][-1]["subject_id"] = "ocd-jurisdiction/unreferenced"
        self.assertTrue(contract_v1.validate_contract(contract, require_certified=False))

    def test_native_jurisdiction_shape_needs_no_new_division_column(self):
        package, policy = fixture()
        package["jurisdiction"].pop("division_id")
        native = policy["jurisdictions"][0]
        policy["institutional_divisions"] = {native["jurisdiction_id"]: native.pop("division_id")}
        self.assertEqual(strict.validate(package, reviewed_dependencies=policy), [])
        core = from_jurisdiction_package(package, reviewed_dependencies=policy)
        self.assertEqual(validate_core(core), [])
        model = render(package, policy)
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["resolved_division_id"], "division-test")
        mapping = policy.pop("institutional_divisions")
        self.rejected(package, policy)
        policy["institutional_divisions"] = mapping
        native["division_id"] = "division-test"
        self.rejected(package, policy)

    def test_missing_policy_and_embedded_self_authorization(self):
        package, policy = fixture()
        self.rejected(package, None)
        package["qa"]["reviewed_dependencies"] = policy
        self.rejected(package, None)

    def test_missing_duplicate_and_mismatched_body(self):
        for mutation in (lambda p: p["records"].update(bodies=[]),
                         lambda p: p["records"]["bodies"].append(copy.deepcopy(p["records"]["bodies"][0])),
                         lambda p: p["records"]["role_terms"][0].update(body_id="wrong-body"),
                         lambda p: p["records"]["offices"][0].pop("body_id")):
            with self.subTest(mutation=mutation):
                package, policy = fixture(); mutation(package); self.rejected(package, policy)

    def test_exact_crosswalk_and_source_review(self):
        for table, key, value in (("identifier_crosswalk", "external_id", "ocd-jurisdiction/incorrect"),
                                  ("bodies", "jurisdiction_id", "jurisdiction-test"),
                                  ("divisions", "ocd_division_id", "ocd-division/wrong")):
            package, policy = fixture(); package["records"][table][0][key] = value
            self.rejected(package, policy)
        package, policy = fixture(); package["provenance"]["source_evidence"][0]["url"] = "https://example.org/drift"
        self.rejected(package, policy)

    def test_ambiguous_crosswalk_even_when_both_reviewed(self):
        package, policy = fixture(); extra = copy.deepcopy(package["records"]["identifier_crosswalk"][0]); extra["crosswalk_id"] = "second-crosswalk"
        package["records"]["identifier_crosswalk"].append(extra); policy["records"]["identifier_crosswalk"].append(copy.deepcopy(extra))
        self.rejected(package, policy)

    def test_capacity_and_wrong_represented_jurisdiction(self):
        for mutation in (lambda p, r: r["body_capacities"].update({"synthetic-shared-body": 2}),
                         lambda p, r: p["records"]["offices"][0].update(jurisdiction_id="jurisdiction-actual-authority"),
                         lambda p, r: r.update(reviewed_by="")):
            package, policy = fixture(); mutation(package, policy); self.rejected(package, policy)

    def test_institutional_ocdid_cannot_be_rewritten_to_package(self):
        package, policy = fixture(); value = package["jurisdiction"]["ocd_jurisdiction_id"]
        policy["jurisdictions"][0]["ocd_jurisdiction_id"] = value
        policy["records"]["identifier_crosswalk"][0]["external_id"] = value
        package["records"]["identifier_crosswalk"][0]["external_id"] = value
        self.rejected(package, policy)

    def test_current_holders_cannot_exceed_representative_allocation(self):
        package, policy = fixture()
        for index in range(3):
            person = copy.deepcopy(package["records"]["people"][0]); person["person_id"] = "synthetic-extra-person-" + str(index)
            term = copy.deepcopy(package["records"]["role_terms"][0]); term.update(role_term_id="synthetic-extra-term-" + str(index), person_id=person["person_id"])
            package["records"]["people"].append(person); package["records"]["role_terms"].append(term)
        self.rejected(package, policy)

    def test_partial_scope_and_blocking_gaps_stay_closed(self):
        for field, value in (("complete_jurisdiction", False), ("blocking_gap_count", 1)):
            package, policy = fixture(); package["qa"][field] = value
            self.assertTrue(generic.validate(package, reviewed_dependencies=policy))
            self.assertTrue(strict.validate(package, reviewed_dependencies=policy))
            self.assertEqual(render(package, policy)["status"], "FAIL-CLOSED")
            contract = export_factory_package(package, governed_package=True, reviewed_dependencies=policy)
            self.assertNotEqual(contract["certification"]["status"], "certified")

    def test_unknown_temporal_claims_stay_unknown(self):
        package, policy = fixture(); term = package["records"]["role_terms"][0]
        term.update(status="UNKNOWN", selection_date="2025-01-01", term_expiration_year="2029", valid_from="2026-01-01", valid_to="2029-12-31", interval_semantics="OBSERVATION")
        package["qa"]["complete_jurisdiction"] = True
        core = from_jurisdiction_package(package, reviewed_dependencies=policy)
        contract = export_factory_package(package, governed_package=True, reviewed_dependencies=policy)
        for item in (core["memberships"][0], contract["memberships"][0]):
            self.assertIsNone(item["start_date"]); self.assertIsNone(item["end_date"])
        self.assertEqual(core["memberships"][0]["membership_status"], "UNKNOWN")
        self.assertNotEqual(contract["certification"]["status"], "certified")
        self.assertEqual(render(package, policy)["status"], "FAIL-CLOSED")

    def test_dependencies_never_activate_service_or_adjacent_geography(self):
        package, policy = fixture()
        self.assertEqual(render(package, policy, gps("synthetic-institution-not-constituency"))["status"], "FAIL-CLOSED")
        self.assertNotIn("service_area", render(package, policy))

    def test_exact_producer_closure_and_snapshot_drift(self):
        package, policy = fixture(); _, rows = snapshot(package, policy)
        scoped = copy.deepcopy(package)
        for section in ("records", "provenance"):
            for table, records in scoped[section].items():
                scoped[section][table] = [r for r in records if r.get("jurisdiction_id") == "jurisdiction-test"]
        restored = include_reviewed_dependencies(scoped, rows, policy)
        self.assertEqual(strict.validate(restored, reviewed_dependencies=policy), [])
        self.assertEqual(len(restored["records"]["bodies"]), 1)
        rows["bodies"][0]["name"] = "source drift"
        with self.assertRaises(SharedAuthorityError):
            include_reviewed_dependencies(scoped, rows, policy)

    def test_scoped_producer_builds_reviewed_dependencies_and_counts(self):
        package, policy = fixture()
        package["jurisdiction"]["release_ready"] = True
        package["jurisdiction"].pop("division_id")
        institution = policy["jurisdictions"][0]
        policy["institutional_divisions"] = {institution["jurisdiction_id"]: institution.pop("division_id")}
        native, _ = snapshot(package, policy)
        # The synthetic native snapshot has fixed-column rows, as Sheets does.
        for table in native["tables"].values():
            columns = sorted({key for item in table["rows"] for key in item["values"]})
            table["columns"] = columns
            for item in table["rows"]:
                item["values"] = {key: item["values"].get(key) for key in columns}
        # Reuse the real 01_Jurisdiction column contract, with synthetic values.
        source_contract = json.loads((ROOT / "data/source/co/d329-co-factory-snapshot.json").read_text())
        jurisdiction_columns = source_contract["tables"]["01_Jurisdiction"]["columns"]
        self.assertNotIn("division_id", jurisdiction_columns)
        native["tables"]["01_Jurisdiction"]["columns"] = jurisdiction_columns
        for item in native["tables"]["01_Jurisdiction"]["rows"]:
            self.assertNotIn("division_id", item["values"])
            item["values"] = {key: item["values"].get(key) for key in jurisdiction_columns}
        native_tables = {name: [item["values"] for item in table["rows"]] for name, table in native["tables"].items()}
        for family, (table, key) in producer.TABLE_MAP.items():
            if family in policy["records"]:
                indexed = {row[key]: row for row in native_tables[table]}
                policy["records"][family] = [copy.deepcopy(indexed[row[key]]) for row in policy["records"][family]]
        for family, table, key in (("source_evidence", "08_SourceEvidence", "source_id"), ("source_assertions", "09_SourceAssertion", "assertion_id")):
            indexed = {row[key]: row for row in native_tables[table]}
            policy["provenance"][family] = [copy.deepcopy(indexed[row[key]]) for row in policy["provenance"][family]]
        policy["jurisdictions"] = [copy.deepcopy(row) for row in native_tables["01_Jurisdiction"] if row["jurisdiction_id"] != "jurisdiction-test"]
        policy["represented_offices"] = copy.deepcopy(native_tables["04_Office"])
        built = producer.build_package(native, "jurisdiction-test", reviewed_dependencies=policy)
        self.assertEqual(strict.validate(built, reviewed_dependencies=policy), [])
        self.assertEqual(built["records"]["bodies"][0]["body_id"], "synthetic-shared-body")
        for table, rows in built["records"].items():
            self.assertEqual(built["qa"]["source_counts"][table], len(rows))
        with self.assertRaises(ValueError):
            producer.build_package(native, "jurisdiction-test")

    def test_conflicting_status_and_actual_date_aliases_are_rejected(self):
        for changes in ({"currentness_status": "UNKNOWN"}, {"role_term_status": "FORMER"},
                        {"term_start_date": "2024-01-01", "start_date": "2025-01-01"},
                        {"term_end_date": None, "end_date": "2029-01-01"}):
            package, policy = fixture(); package["records"]["role_terms"][0].update(changes)
            self.rejected(package, policy)

    def test_actual_legacy_address_function_uses_policy_through_catalog(self):
        package, policy = fixture()
        class SyntheticResolver:
            def resolve(self, address, observed_on=None):
                return gps()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "package"
            strict.build(package, out, reviewed_dependencies=policy)
            self.assertEqual(strict.verify_package(out, reviewed_dependencies=policy), [])
            self.assertTrue(strict.verify_package(out))
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for file in sorted(out.iterdir()):
                    archive.write(file, "package/" + file.name)
            raw = stream.getvalue(); (root / "synthetic.part01").write_text(base64.b64encode(raw).decode())
            entry = {"entry_id": "synthetic-only", "profile": "municipal_representation", "civic_gps_jurisdiction_id": "synthetic-gps", "package_jurisdiction_id": "jurisdiction-test", "package_schema_version": "0.1", "artifact": {"encoding": "base64-parts", "parts_glob": "synthetic.part*", "archive_sha256": hashlib.sha256(raw).hexdigest(), "package_subdir": "package"}}
            catalog = root / "catalog.json"; catalog.write_text(json.dumps({"catalog_version": "0.1", "entries": [entry]}))
            kwargs = dict(repo_root=root, resolver=SyntheticResolver(), catalog_path=catalog)
            before = hashlib.sha256(raw).hexdigest()
            model = representation_catalog.build_representation_from_live_address("SYNTHETIC INPUT, NOT A LIVE ADDRESS", reviewed_dependencies=policy, **kwargs)
            self.assertEqual(model["status"], "PASS", model)
            self.assertEqual(model["applicable_offices"][0]["organization_id"], "synthetic-shared-body")
            self.assertEqual(model["canonical_writes"], 0)
            self.assertEqual(representation_catalog.build_representation_from_live_address("synthetic", **kwargs)["status"], "FAIL-CLOSED")
            self.assertEqual(hashlib.sha256(base64.b64decode((root / "synthetic.part01").read_text())).hexdigest(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
