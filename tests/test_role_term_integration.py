"""Synthetic regression controls; no Texas civic facts or live GIS proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import jurisdiction_package as builder
from consumers.empowered_vote import package_source, representation


def fixture():
    records = {name: [] for name in builder.BASE_TABLES}
    for chamber, district in (("house", "49"), ("senate", "14")):
        records["divisions"].append({"division_id": f"test-{chamber}-{district}"})
        records["people"].append({"person_id": f"test-person-{chamber}",
                                  "canonical_name": f"Synthetic {chamber} member",
                                  "person_status": "PROVISIONAL"})
        records["offices"].append({"office_id": f"test-office-{chamber}", "seats": 1,
                                   "represented_division_id": f"test-{chamber}-{district}"})
        records["role_terms"].append({
            "role_term_id": f"test-term-{chamber}", "person_id": f"test-person-{chamber}",
            "office_id": f"test-office-{chamber}", "source_record_id": f"test-source-record-{chamber}",
            "role_term_status": "CURRENT", "term_start_date": "2025-01-14", "term_end_date": "",
            "observed_at": "2026-08-22 00:00:00", "source_ids": ["test-evidence"],
        })
    return {"schema_version": "0.1",
            "jurisdiction": {"jurisdiction_id": "test-jurisdiction", "name": "Synthetic",
                             "state_abbr": "TX", "geoid": "48"},
            "records": records, "provenance": {"source_evidence": [{"source_id": "test-evidence"}],
                                               "source_assertions": []},
            "qa": {"parity_ok": True, "qa_fail_count": 0, "blocking_gap_count": 0,
                   "address_tests": [{"result": True}, {"result": True}], "checks": []},
            "warnings": []}


def bindings():
    return [{"binding_id": chamber, "package_jurisdiction_id": "test-jurisdiction",
             "civic_gps_jurisdiction_id": "test-gps-jurisdiction",
             "district_adapter_id": f"test-adapter-{chamber}",
             "division_template": f"test-{chamber}-{{district_key}}"}
            for chamber in ("house", "senate")]


def gps():
    return {"payload": {"jurisdictions": [{"jurisdiction_id": "test-gps-jurisdiction"}],
                        "district_assignments": [{"adapter_id": "test-adapter-house", "district_key": "49"},
                                                 {"adapter_id": "test-adapter-senate", "district_key": "14"}],
                        "officeholders": [{"person_id": "poison", "name": "Never import GPS facts"}]}}


class IdentityValidationTests(unittest.TestCase):
    def test_valid_source_graph(self):
        self.assertEqual(builder.validate(fixture()), [])

    def test_orphan_person_and_office_rejected(self):
        p = fixture()
        p["records"]["role_terms"][0].update(person_id="missing-person", office_id="missing-office")
        self.assertIn("role_term_person_fk", builder.validate(p))
        self.assertIn("role_term_office_fk", builder.validate(p))

    def test_duplicate_primary_ids_in_every_base_table(self):
        for table, keys in builder.PRIMARY_KEYS.items():
            with self.subTest(table=table):
                p = fixture()
                p["records"][table] += [{keys[0]: "duplicate-test"}, {keys[0]: "duplicate-test"}]
                self.assertIn("duplicate_id:duplicate-test", builder.validate(p))

    def test_missing_primary_id_does_not_use_source_id(self):
        p = fixture()
        p["records"]["people"][0] = {"source_id": "test-evidence"}
        self.assertIn("primary_id:people", builder.validate(p))

    def test_alias_only_primary_ids_supported(self):
        p = fixture()
        for table in ("people", "offices"):
            key = builder.PRIMARY_KEYS[table][0]
            for row in p["records"][table]:
                row["id"] = row.pop(key)
        self.assertEqual(builder.validate(p), [])

    def test_conflicting_id_alias_rejected(self):
        p = fixture()
        p["records"]["people"][0]["id"] = "different-person"
        self.assertIn("primary_id_alias_conflict:people", builder.validate(p))

    def test_malformed_identity_returns_errors(self):
        for value in ([], {}, 5):
            with self.subTest(value=value):
                p = fixture()
                p["records"]["people"][0]["person_id"] = value
                self.assertIn("primary_id:people", builder.validate(p))

    def test_role_term_evidence_reference_must_resolve(self):
        p = fixture()
        p["records"]["role_terms"][0]["source_ids"] = ["missing-evidence"]
        self.assertIn("role_term_source_fk", builder.validate(p))

    def test_existing_semicolon_evidence_encoding_is_validated(self):
        p = fixture()
        p["provenance"]["source_evidence"].append({"source_id": "test-evidence-2"})
        p["records"]["role_terms"][0]["source_ids"] = "test-evidence;test-evidence-2"
        before = copy.deepcopy(p)
        self.assertEqual(builder.validate(p), [])
        self.assertEqual(p, before)
        p["records"]["role_terms"][0]["source_ids"] += ";missing-evidence"
        self.assertIn("role_term_source_fk", builder.validate(p))

    def test_consumer_load_rejects_orphan_even_with_recomputed_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            builder.build(fixture(), out)
            p = json.loads((out / "jurisdiction.json").read_text())
            p["records"]["role_terms"][0]["person_id"] = "missing-person"
            (out / "jurisdiction.json").write_text(builder.canonical_json(p))
            manifest = json.loads((out / "manifest.json").read_text())
            for row in manifest["files"]:
                row["bytes"] = (out / row["path"]).stat().st_size
            (out / "manifest.json").write_text(builder.canonical_json(manifest))
            sums = "".join(f"{package_source.sha256_file(path)}  {path.name}\n"
                           for path in sorted(out.iterdir()) if path.name != "SHA256SUMS.txt")
            (out / "SHA256SUMS.txt").write_text(sums)
            with self.assertRaises(package_source.PackageContractError) as error:
                package_source.load_jurisdiction_package(out)
            self.assertEqual(error.exception.code, "PACKAGE_IDENTITY_GRAPH_INVALID")


class RepresentationTests(unittest.TestCase):
    def preview(self, package=None, geographic=None, configured=None):
        return representation.preview_representation_for_bindings(
            fixture() if package is None else package, "SYNTHETIC INPUT",
            gps() if geographic is None else geographic,
            bindings=bindings() if configured is None else configured)

    def test_two_chambers_preserve_ids_dates_provenance_and_identity(self):
        p = fixture()
        before = copy.deepcopy(p)
        result = self.preview(p)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["publication_eligible"])
        self.assertFalse(result["complete_jurisdiction"])
        self.assertEqual(result["scope"], "BOUND_BINDINGS_ONLY")
        self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(len(result["projections"]), 2)
        for projection in result["projections"]:
            chamber = projection["binding_id"]
            model = projection["representation"]
            holder = model["applicable_offices"][0]["holders"][0]
            self.assertEqual(holder["role_term_id"], f"test-term-{chamber}")
            self.assertEqual(holder["person_id"], f"test-person-{chamber}")
            self.assertEqual(holder["status"], "CURRENT")
            self.assertEqual(holder["person_status"], "PROVISIONAL")
            self.assertEqual(holder["term_start"], "2025-01-14")
            self.assertIsNone(holder["term_end"])
            self.assertEqual(holder["source_record_id"], f"test-source-record-{chamber}")
            self.assertEqual(holder["observed_at"], "2026-08-22 00:00:00")
            self.assertEqual(holder["source_ids"], ["test-evidence"])
            self.assertEqual(len(model["warnings"]), 1)
            self.assertFalse(model["publication_eligible"])
        self.assertEqual(p, before)

    def test_default_consumer_rejects_provisional_identity(self):
        model = representation.build_representation_from_civic_gps_result(
            fixture(), "SYNTHETIC INPUT", gps(), binding=bindings()[0])
        self.assertEqual(model["error"], "PERSON_IDENTITY_PROVISIONAL")

    def test_provisional_status_alias_is_preserved(self):
        p = fixture()
        p["records"]["people"][0]["status"] = p["records"]["people"][0].pop("person_status")
        model = self.preview(p)
        holder = model["projections"][0]["representation"]["applicable_offices"][0]["holders"][0]
        self.assertEqual(holder["person_status"], "PROVISIONAL")

    def test_current_role_does_not_override_conflicting_provisional_identity(self):
        p = fixture()
        p["records"]["people"][0]["status"] = "CURRENT"
        model = representation.build_representation_from_civic_gps_result(
            p, "SYNTHETIC INPUT", gps(), binding=bindings()[0])
        self.assertEqual(model["error"], "PERSON_IDENTITY_PROVISIONAL")

    def test_conflicting_field_aliases_fail_closed(self):
        for extra in ({"status": "FORMER"}, {"start_date": "2024-01-01"}, {"end_date": "2027-01-01"}):
            with self.subTest(extra=extra):
                p = fixture()
                p["records"]["role_terms"][0].update(extra)
                self.assertEqual(self.preview(p)["error"], "ROLE_TERM_FIELD_CONFLICT")

    def test_invalid_or_partial_tx_date_rejected(self):
        for value in ("2025", "2025-01", "2025-02-30", "20250114", 45671):
            with self.subTest(value=value):
                p = fixture()
                p["records"]["role_terms"][0]["term_start_date"] = value
                self.assertEqual(self.preview(p)["error"], "ROLE_TERM_DATE_INVALID")

    def test_unknown_date_remains_unknown(self):
        p = fixture()
        p["records"]["role_terms"][0]["term_start_date"] = ""
        holder = self.preview(p)["projections"][0]["representation"]["applicable_offices"][0]["holders"][0]
        self.assertIsNone(holder["term_start"])

    def test_outside_jurisdiction_returns_no_partial_result(self):
        g = gps()
        g["payload"]["jurisdictions"] = []
        result = self.preview(geographic=g)
        self.assertEqual(result["error"], "CIVIC_GPS_JURISDICTION_NOT_ACTIVE")
        self.assertNotIn("projections", result)

    def test_outside_district_returns_no_partial_result(self):
        g = gps()
        g["payload"]["district_assignments"][1]["district_key"] = "15"
        result = self.preview(geographic=g)
        self.assertEqual(result["error"], "CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE")
        self.assertNotIn("projections", result)

    def test_missing_district_returns_no_partial_result(self):
        g = gps()
        g["payload"]["district_assignments"].pop()
        self.assertEqual(self.preview(geographic=g)["error"], "CIVIC_GPS_REQUIRED_DISTRICT_MISSING")

    def test_ambiguous_boundary_returns_no_partial_result(self):
        g = gps()
        g["payload"]["district_assignments"].append({"adapter_id": "test-adapter-house", "district_key": "50"})
        result = self.preview(geographic=g)
        self.assertEqual(result["error"], "CIVIC_GPS_AMBIGUOUS_DISTRICT")
        self.assertNotIn("projections", result)

    def test_mislabeled_chamber_does_not_match_other_district(self):
        g = gps()
        g["payload"]["district_assignments"][0]["district_key"] = "14"
        self.assertEqual(self.preview(geographic=g)["error"], "CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE")

    def test_binding_names_must_be_unique(self):
        b = bindings()
        b[1]["binding_id"] = b[0]["binding_id"]
        self.assertEqual(self.preview(configured=b)["error"], "REPRESENTATION_BINDING_ID_INVALID")

    def test_binding_cannot_fall_back_to_statewide_projection(self):
        b = bindings()
        b[0].pop("district_adapter_id")
        self.assertEqual(self.preview(configured=b)["error"], "REPRESENTATION_DISTRICT_BINDING_REQUIRED")

    def test_overlapping_bindings_rejected(self):
        b = bindings()
        b[1].update(district_adapter_id=b[0]["district_adapter_id"], division_template=b[0]["division_template"])
        self.assertEqual(self.preview(configured=b)["error"], "REPRESENTATION_BINDING_OVERLAP")

    def test_direct_consumer_rejects_duplicate_people(self):
        p = fixture()
        p["records"]["people"].append(copy.deepcopy(p["records"]["people"][0]))
        self.assertEqual(self.preview(p)["error"], "PACKAGE_IDENTITY_GRAPH_INVALID")

    def test_direct_consumer_rejects_unresolved_evidence(self):
        p = fixture()
        p["records"]["role_terms"][0]["source_ids"] = ["missing-evidence"]
        self.assertEqual(self.preview(p)["error"], "PACKAGE_ROLE_TERM_EVIDENCE_INVALID")

    def test_explicit_district_map_preserves_opaque_canonical_ids(self):
        p, b = fixture(), bindings()
        for i, key in enumerate(("49", "14")):
            opaque_id = f"opaque-canonical-division-{i}"
            p["records"]["divisions"][i]["division_id"] = opaque_id
            p["records"]["offices"][i]["represented_division_id"] = opaque_id
            b[i].pop("division_template")
            b[i]["district_division_map"] = {key: opaque_id}
        result = self.preview(p, configured=b)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual([x["representation"]["resolved_division_id"] for x in result["projections"]],
                         ["opaque-canonical-division-0", "opaque-canonical-division-1"])
        b[0]["district_division_map"] = {"50": "opaque-canonical-division-0"}
        self.assertEqual(self.preview(p, configured=b)["error"], "CIVIC_GPS_DISTRICT_NOT_IN_BINDING")

    def test_district_map_cannot_mint_a_division(self):
        b = bindings()
        b[0].pop("division_template")
        b[0]["district_division_map"] = {"49": "not-in-package"}
        self.assertEqual(self.preview(configured=b)["error"], "CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE")

    def test_conflicting_binding_forms_rejected(self):
        b = bindings()
        b[0]["district_division_map"] = {"49": "test-house-49"}
        self.assertEqual(self.preview(configured=b)["error"], "CIVIC_GPS_DISTRICT_BINDING_INVALID")

    def test_review_role_term_is_not_returned_as_current(self):
        p = fixture()
        p["records"]["role_terms"][0]["role_term_status"] = "REVIEW"
        self.assertEqual(self.preview(p)["error"], "PACKAGE_REPRESENTATION_EMPTY")

    def test_repeat_and_binding_order_are_deterministic(self):
        self.assertEqual(self.preview(), self.preview(configured=list(reversed(bindings()))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
