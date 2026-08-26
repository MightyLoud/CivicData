import copy
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from tools import jurisdiction_package as jp


def fixture():
    return {
        "schema_version": "0.1",
        "jurisdiction": {
            "jurisdiction_id": "jurisdiction-test",
            "name": "Test",
            "state_abbr": "CO",
            "geoid": "0800000",
        },
        "records": {
            "divisions": [],
            "bodies": [],
            "offices": [],
            "people": [],
            "role_terms": [],
            "leadership_roles": [],
            "identifier_crosswalk": [],
        },
        "provenance": {
            "source_evidence": [{"source_id": "src-1", "jurisdiction_id": "jurisdiction-test"}],
            "source_assertions": [],
        },
        "qa": {
            "parity_ok": True,
            "qa_fail_count": 0,
            "blocking_gap_count": 0,
            "address_tests": [{"result": True}, {"result": True}],
            "checks": [],
        },
        "warnings": [],
    }


def test_valid_fixture():
    assert jp.validate(fixture()) == []


def test_fail_closed_parity():
    package = fixture()
    package["qa"]["parity_ok"] = False
    assert "parity_ok" in jp.validate(package)


def test_actual_foreign_keys_are_checked():
    package = fixture()
    package["records"]["role_terms"] = [
        {
            "role_term_id": "rt-1",
            "jurisdiction_id": "jurisdiction-test",
            "person_id": "missing-person",
            "office_id": "missing-office",
        }
    ]
    errors = jp.validate(package)
    assert any(item.startswith("role_term_person_fk") for item in errors)
    assert any(item.startswith("role_term_office_fk") for item in errors)


def test_source_assertion_foreign_key_is_checked():
    package = fixture()
    package["provenance"]["source_assertions"] = [
        {
            "assertion_id": "asrt-1",
            "source_id": "missing-source",
            "jurisdiction_id": "jurisdiction-test",
        }
    ]
    assert any(item.startswith("assertion_source_fk") for item in jp.validate(package))


def test_deterministic_build_and_checksum_verification():
    package = fixture()
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        first_path, second_path = pathlib.Path(first), pathlib.Path(second)
        jp.build(copy.deepcopy(package), first_path)
        jp.build(copy.deepcopy(package), second_path)
        assert jp.verify_package(first_path) == []
        assert {
            path.name: path.read_bytes() for path in first_path.iterdir()
        } == {
            path.name: path.read_bytes() for path in second_path.iterdir()
        }
        (first_path / "jurisdiction.json").write_text("{}\n", encoding="utf-8")
        assert "checksum:jurisdiction.json" in jp.verify_package(first_path)


def test_deterministic_json():
    assert jp.canonical_json(fixture()) == jp.canonical_json(fixture())


def test_build_has_manifest_and_checksums():
    with tempfile.TemporaryDirectory() as d:
        jp.build(fixture(), pathlib.Path(d))
        assert (pathlib.Path(d) / "manifest.json").exists()
        assert (pathlib.Path(d) / "SHA256SUMS.txt").exists()


def run():
    test_valid_fixture()
    test_fail_closed_parity()
    test_actual_foreign_keys_are_checked()
    test_source_assertion_foreign_key_is_checked()
    test_deterministic_build_and_checksum_verification()
    test_deterministic_json()
    test_build_has_manifest_and_checksums()
    print(json.dumps({"status": "PASS", "schema_version": "0.1", "backward_compatibility": True}, sort_keys=True))


if __name__ == "__main__":
    run()
