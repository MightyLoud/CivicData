import copy
import importlib.util
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).parents[1]
TOOL_PATH = ROOT / "tools" / "candidate_election_package.py"
SCHEMA_PATH = ROOT / "schemas" / "candidate_election_package_v0.1.schema.json"
RELEASE_PATH = (
    ROOT
    / "data"
    / "normalized"
    / "tx"
    / "tx-candidate-election-2026-001.manifest.json"
)

spec = importlib.util.spec_from_file_location("candidate_election_package", TOOL_PATH)
cep = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cep)

EXPECTED_COUNTS = {
    "07552": (3, 3),
    "08128": (6, 6),
    "17917": (1, 1),
    "26808": (3, 3),
    "33794": (3, 3),
    "35228": (5, 5),
    "38548": (8, 8),
    "39952": (16, 8),
    "46824": (9, 9),
    "47316": (4, 4),
}
EXPECTED_DATES = {
    "07552": "2026-11-03",
    "08128": "2026-11-03",
    "17917": "2026-05-02",
    "26808": "2026-11-03",
    "33794": "2026-05-02",
    "35228": "2026-05-02",
    "38548": "2026-11-03",
    "39952": "2026-11-03",
    "46824": "2026-05-02",
    "47316": "2026-05-02",
}
EXPECTED_ENTITY_TOTALS = {
    "candidacies": 50,
    "contact_points": 0,
    "contests": 25,
    "divisions": 15,
    "elections": 10,
    "external_identifiers": 0,
    "jurisdiction_divisions": 15,
    "office_divisions": 25,
    "offices": 25,
    "people": 50,
}


def release():
    return json.loads(RELEASE_PATH.read_text(encoding="utf-8"))


def package_paths():
    return sorted(
        ROOT.glob("data/normalized/tx/*/candidate-election/2026/canonical.json")
    )


def packages():
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in package_paths()
    ]


def test_schema_is_parseable_and_versioned():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert (
        schema["properties"]["contract_version"]["const"]
        == cep.CONTRACT_VERSION
    )


def test_exact_package_set_and_reconciliation():
    rows = packages()
    assert len(rows) == 10
    assert {
        row["jurisdiction"]["source_jurisdiction_key"] for row in rows
    } == set(EXPECTED_COUNTS)
    for row in rows:
        fp = row["jurisdiction"]["source_jurisdiction_key"]
        raw_count, candidacy_count = EXPECTED_COUNTS[fp]
        assert row["reconciliation"]["source_scope_total"] == raw_count
        assert row["reconciliation"]["normalized_total"] == raw_count
        assert row["reconciliation"]["qa_ready_total"] == raw_count
        assert len(row["records"]["candidacies"]) == candidacy_count
        assert row["reconciliation"]["canonical_candidacy_total"] == candidacy_count
        assert row["records"]["elections"][0]["election_date"] == EXPECTED_DATES[fp]
        assert cep.validate_package(row) == []


def test_aggregate_contract_totals():
    manifest = release()
    assert manifest["package_count"] == 10
    assert manifest["entity_totals"] == EXPECTED_ENTITY_TOTALS
    assert manifest["provenance_totals"]["source_record_refs"] == 53
    assert manifest["provenance_totals"]["source_evidence"] == 55
    assert manifest["reconciliation_totals"] == {
        "canonical_candidacy_total": 50,
        "normalized_total": 58,
        "public_source_record_ref_count": 53,
        "qa_ready_total": 58,
        "record_type_counts": {
            "Candidate": 50,
            "Gap": 1,
            "Retired": 4,
            "Structure": 3,
        },
        "source_scope_total": 58,
    }
    assert all(manifest["qa_summary"].values())
    assert manifest["publication_status"] == "STAGED_NOT_PUBLISHED"


def test_kyle_non_candidate_rows_are_accounted_not_published():
    kyle = next(
        row
        for row in packages()
        if row["jurisdiction"]["source_jurisdiction_key"] == "39952"
    )
    assert kyle["reconciliation"]["record_type_counts"] == {
        "Candidate": 8,
        "Structure": 3,
        "Gap": 1,
        "Retired": 4,
    }
    assert len(kyle["provenance"]["source_record_refs"]) == 11
    assert len(kyle["reconciliation"]["excluded_source_records"]) == 5
    assert {
        row["record_type"]
        for row in kyle["reconciliation"]["excluded_source_records"]
    } == {"Gap", "Retired"}
    assert all(
        row["record_type"] in {"Candidate", "Structure"}
        for row in kyle["provenance"]["source_record_refs"]
    )


def test_built_outputs_verify():
    assert cep.verify_release(ROOT) == []
    for package_row in release()["packages"]:
        package_dir = ROOT / package_row["path"]
        assert cep.verify_built_package(package_dir) == []


def test_deterministic_release_rerun_is_byte_identical():
    bundle = {
        "contract_version": cep.CONTRACT_VERSION,
        "release_id": cep.RELEASE_ID,
        "packages": packages(),
    }
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        first_root = pathlib.Path(first)
        second_root = pathlib.Path(second)
        cep.build_release(bundle, first_root)
        cep.build_release(bundle, second_root)
        first_files = {
            path.relative_to(first_root): path.read_bytes()
            for path in first_root.rglob("*")
            if path.is_file()
        }
        second_files = {
            path.relative_to(second_root): path.read_bytes()
            for path in second_root.rglob("*")
            if path.is_file()
        }
        assert first_files == second_files
        committed_files = {
            path.relative_to(ROOT): path.read_bytes()
            for path in (ROOT / "data" / "normalized" / "tx").rglob("*")
            if path.is_file()
        }
        assert first_files == committed_files


def test_fail_closed_controls():
    base = packages()[0]

    changed = copy.deepcopy(base)
    changed["qa"]["parity_ok"] = False
    assert "qa:parity_ok" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["records"]["candidacies"][0]["contest_id"] = "missing-contest"
    assert "candidacy_contest_fk" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["provenance"]["source_record_refs"][0]["raw_payload_json"] = "{}"
    assert "restricted_fields" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["publication_status"] = "PUBLISHED"
    assert "publication_status" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["records"]["contact_points"] = [
        {
            "contact_point_id": "contact-private",
            "person_id": changed["records"]["people"][0]["person_id"],
            "contact_type": "EMAIL",
            "contact_value_normalized": "private@example.com",
            "sensitivity": "RESTRICTED",
            "publication_ok": "FALSE",
            "source_evidence_id": changed["provenance"]["source_evidence"][0][
                "source_evidence_id"
            ],
            "contact_status": "ACTIVE",
        }
    ]
    errors = cep.validate_package(changed)
    assert "contact_sensitivity" in errors
    assert "contact_publication_ok" in errors


def run():
    test_schema_is_parseable_and_versioned()
    test_exact_package_set_and_reconciliation()
    test_aggregate_contract_totals()
    test_kyle_non_candidate_rows_are_accounted_not_published()
    test_built_outputs_verify()
    test_deterministic_release_rerun_is_byte_identical()
    test_fail_closed_controls()
    print(
        json.dumps(
            {
                "status": "PASS",
                "packages": 10,
                "raw_normalized_qa": "58/58/58",
                "candidacies": 50,
                "publication_status": "STAGED_NOT_PUBLISHED",
                "deterministic_rerun": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    run()
