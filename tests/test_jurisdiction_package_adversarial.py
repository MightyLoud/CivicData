import copy
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from tools import jurisdiction_package as jp


def fixture_v01():
    jurisdiction_id = "jurisdiction-test"
    return {
        "schema_version": "0.1",
        "jurisdiction": {
            "jurisdiction_id": jurisdiction_id,
            "name": "Test City",
            "state_abbr": "CO",
            "geoid": "0800000",
        },
        "records": {
            "divisions": [{"division_id": "division-test", "jurisdiction_id": jurisdiction_id}],
            "bodies": [{"body_id": "body-test", "jurisdiction_id": jurisdiction_id}],
            "offices": [{
                "office_id": "office-test",
                "body_id": "body-test",
                "represented_division_id": "division-test",
                "jurisdiction_id": jurisdiction_id,
            }],
            "people": [{"person_id": "person-test", "jurisdiction_id": jurisdiction_id}],
            "role_terms": [{
                "role_term_id": "role-test",
                "person_id": "person-test",
                "office_id": "office-test",
                "body_id": "body-test",
                "assertion_ids": "assertion-test",
                "source_ids": "source-test",
                "jurisdiction_id": jurisdiction_id,
            }],
            "leadership_roles": [{
                "leadership_id": "leadership-test",
                "person_id": "person-test",
                "office_id": "office-test",
                "body_id": "body-test",
                "source_ids": "source-test",
                "jurisdiction_id": jurisdiction_id,
            }],
            "identifier_crosswalk": [{
                "crosswalk_id": "crosswalk-test",
                "entity_id": jurisdiction_id,
                "entity_type": "Jurisdiction",
                "source_id": "source-test",
                "jurisdiction_id": jurisdiction_id,
            }],
        },
        "provenance": {
            "source_evidence": [{
                "source_id": "source-test",
                "jurisdiction_id": jurisdiction_id,
                "supports_entity_id": jurisdiction_id,
                "supports_entity_type": "Jurisdiction",
            }],
            "source_assertions": [{
                "assertion_id": "assertion-test",
                "source_id": "source-test",
                "jurisdiction_id": jurisdiction_id,
                "subject_id": "role-test",
                "subject_type": "RoleTerm",
                "object_id": "office-test",
                "object_type": "ID",
                "object_value": "office-test",
            }],
        },
        "qa": {
            "parity_ok": True,
            "qa_fail_count": 0,
            "blocking_gap_count": 0,
            "address_tests": [
                {
                    "test_id": "address-test-1",
                    "address_input": "1 Main St",
                    "jurisdiction_id": jurisdiction_id,
                    "boundary_source_id": "source-test",
                    "actual_division_id": "division-test",
                    "expected_division_id": "division-test",
                    "actual_office_ids": "office-test",
                    "expected_office_ids": "office-test",
                    "result": True,
                },
                {
                    "test_id": "address-test-2",
                    "address_input": "2 Main St",
                    "jurisdiction_id": jurisdiction_id,
                    "boundary_source_id": "source-test",
                    "actual_division_id": "division-test",
                    "expected_division_id": "division-test",
                    "actual_office_ids": "office-test",
                    "expected_office_ids": "office-test",
                    "result": True,
                },
            ],
            "checks": [{"qa_id": "qa-test", "source_id": "source-test", "result": True}],
        },
        "warnings": [{
            "gap_id": "gap-test",
            "jurisdiction_id": jurisdiction_id,
            "entity_id": "body-test",
            "entity_type": "Body",
            "source_id": "source-test",
            "blocking": False,
            "status": "OPEN",
        }],
    }


def fixture_v02():
    package = fixture_v01()
    package["schema_version"] = "0.2"
    package["records"].update({
        "elections": [{
            "election_id": "election-test",
            "election_date": "2026-11-03",
            "source_ids": ["source-test"],
        }],
        "contests": [{
            "contest_id": "contest-test",
            "election_id": "election-test",
            "office_id": "office-test",
            "contest_name": "Mayor",
            "source_ids": ["source-test"],
        }],
        "candidacies": [{
            "candidacy_id": "candidacy-test",
            "contest_id": "contest-test",
            "candidate_kind": "PERSON",
            "source_candidate_id": "candidate-source-test",
            "person_id": "person-test",
            "candidate_name": "Test Person",
            "source_id": "source-test",
            "outcome": "WINNER",
            "votes": 10,
            "vote_share": 1.0,
        }],
    })
    package["qa"].update({"election_scope_complete": True, "unexplained_loss": 0})
    return package


def assert_invalid(package, expected=None):
    errors = jp.validate(package)
    assert errors
    if expected:
        assert expected in errors or any(item.startswith(expected) for item in errors), errors


def test_schema_contract_fail_closed():
    assert_invalid([])
    for key, value in (("state_abbr", "ZZ"), ("geoid", "not-a-geoid")):
        package = fixture_v01()
        package["jurisdiction"][key] = value
        assert_invalid(package)
    package = fixture_v01()
    package["unexpected"] = True
    assert_invalid(package)
    package = fixture_v01()
    del package["records"]["bodies"]
    assert_invalid(package)
    package = fixture_v01()
    package["records"]["people"] = "not-an-array"
    assert_invalid(package)

    mutations = (
        ("election_date", "2026-02-30", None),
        ("outcome", "ELECTED", "outcome"),
        ("votes", -1, "votes"),
        ("vote_share", 1.1, "vote_share"),
    )
    for field, value, expected in mutations:
        package = fixture_v02()
        target = package["records"]["elections"][0] if field == "election_date" else package["records"]["candidacies"][0]
        target[field] = value
        assert_invalid(package, expected)


def test_provenance_entity_and_relationship_controls():
    package = fixture_v01()
    package["provenance"]["source_evidence"][0]["supports_entity_id"] = "missing"
    assert_invalid(package, "source_target_fk")
    package = fixture_v01()
    package["provenance"]["source_evidence"][0]["supports_entity_type"] = "Body"
    assert_invalid(package, "source_entity_family")
    package = fixture_v01()
    package["provenance"]["source_assertions"][0]["subject_id"] = "missing"
    assert_invalid(package, "assertion_subject_fk")
    package = fixture_v01()
    package["provenance"]["source_assertions"][0]["subject_type"] = "Office"
    assert_invalid(package, "assertion_entity_family")
    package = fixture_v01()
    package["provenance"]["source_assertions"][0]["object_value"] = "missing"
    assert_invalid(package, "assertion_object_fk")
    package = fixture_v01()
    package["records"]["leadership_roles"][0]["office_id"] = "missing"
    assert_invalid(package, "leadership_office_fk")
    package = fixture_v01()
    package["records"]["role_terms"] = []
    assert_invalid(package, "leadership_role_term_relationship")


def test_address_and_blocking_controls():
    package = fixture_v01()
    package["qa"]["address_tests"][1]["test_id"] = "address-test-1"
    assert_invalid(package, "address_test_id_unique")
    package = fixture_v01()
    package["qa"]["address_tests"][1]["address_input"] = " 1 MAIN ST "
    assert_invalid(package, "address_test_independence")
    package = fixture_v01()
    package["warnings"][0]["blocking"] = "FALSE"
    assert_invalid(package, "warning_blocking_boolean")
    package = fixture_v01()
    package["warnings"][0]["entity_type"] = "Office"
    assert_invalid(package, "warning_entity_family")


def _build_temp():
    directory = tempfile.TemporaryDirectory()
    out = pathlib.Path(directory.name) / "package"
    jp.build(fixture_v01(), out)
    assert jp.verify_package(out) == []
    return directory, out


def test_exact_inventory_manifest_checksum_and_path_controls():
    holder, out = _build_temp()
    with holder:
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].append(copy.deepcopy(manifest["files"][0]))
        manifest_path.write_text(jp.canonical_json(manifest), encoding="utf-8")
        assert "manifest_path_unique" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].pop()
        manifest_path.write_text(jp.canonical_json(manifest), encoding="utf-8")
        assert "manifest_file_set" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][0]["path"] = "../escape"
        manifest_path.write_text(jp.canonical_json(manifest), encoding="utf-8")
        assert "manifest_unsafe_path" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][0]["path"] = "/absolute/path"
        manifest_path.write_text(jp.canonical_json(manifest), encoding="utf-8")
        assert "manifest_unsafe_path" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        sums = out / "SHA256SUMS.txt"
        first = sums.read_text(encoding="utf-8").splitlines()[0]
        sums.write_text(sums.read_text(encoding="utf-8") + first + "\n", encoding="utf-8")
        assert "checksum_target_unique" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        sums = out / "SHA256SUMS.txt"
        sums.write_text("0" * 64 + "  ..\\escape\n", encoding="utf-8")
        assert "checksum_unsafe_path" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        nested = out / "nested"
        nested.mkdir()
        (nested / "extra.txt").write_text("stale", encoding="utf-8")
        errors = jp.verify_package(out)
        assert any(item.startswith("nested_directory:") for item in errors)
        assert "package_inventory" in errors

    holder, out = _build_temp()
    with holder:
        target = pathlib.Path(holder.name) / "target.txt"
        target.write_text("target", encoding="utf-8")
        os.symlink(target, out / "linked.txt")
        assert any(item.startswith("package_symlink:") for item in jp.verify_package(out))

    holder, out = _build_temp()
    with holder:
        (out / "jurisdiction.json").write_text("[]\n", encoding="utf-8")
        assert "schema:$:type" in jp.verify_package(out)

    holder, out = _build_temp()
    with holder:
        (out / "manifest.json").write_text("[]\n", encoding="utf-8")
        assert "manifest_object" in jp.verify_package(out)


def test_build_cleans_stale_output():
    try:
        jp._prepare_clean_output(ROOT)
    except ValueError as error:
        assert str(error) == "unsafe_output_path"
    else:
        raise AssertionError("repository root must never be accepted as an output directory")
    with tempfile.TemporaryDirectory() as directory:
        out = pathlib.Path(directory) / "package"
        out.mkdir()
        (out / "stale.txt").write_text("stale", encoding="utf-8")
        nested = out / "old"
        nested.mkdir()
        (nested / "old.txt").write_text("old", encoding="utf-8")
        jp.build(fixture_v01(), out)
        assert not (out / "stale.txt").exists()
        assert not nested.exists()
        assert jp.verify_package(out) == []


def test_build_rejects_traversal_and_symlinked_ancestors_without_mutation():
    with tempfile.TemporaryDirectory() as directory:
        victim = pathlib.Path(directory) / "victim"
        scratch = victim / "scratch"
        scratch.mkdir(parents=True)
        sentinel = victim / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        try:
            jp._prepare_clean_output(scratch / "..")
        except ValueError as error:
            assert str(error) == "unsafe_output_path"
        else:
            raise AssertionError("lexical traversal must fail before output cleanup")
        assert sentinel.read_text(encoding="utf-8") == "keep"
        assert scratch.is_dir()

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        target = root / "target"
        target.mkdir()
        sentinel = target / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        output = root / "output"
        os.symlink(target, output, target_is_directory=True)
        try:
            jp._prepare_clean_output(output)
        except ValueError as error:
            assert str(error) == "unsafe_output_path"
        else:
            raise AssertionError("a symlinked output target must fail before cleanup")
        assert sentinel.read_text(encoding="utf-8") == "keep"

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        target = root / "target"
        victim = target / "victim"
        victim.mkdir(parents=True)
        sentinel = victim / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        alias = root / "alias"
        os.symlink(target, alias, target_is_directory=True)
        output = alias / "victim"
        assert not output.is_symlink()
        try:
            jp._prepare_clean_output(output)
        except ValueError as error:
            assert str(error) == "unsafe_output_path"
        else:
            raise AssertionError("a symlinked output ancestor must fail before cleanup")
        assert sentinel.read_text(encoding="utf-8") == "keep"


def run():
    assert jp.validate(fixture_v01()) == []
    assert jp.validate(fixture_v02()) == []
    test_schema_contract_fail_closed()
    test_provenance_entity_and_relationship_controls()
    test_address_and_blocking_controls()
    test_exact_inventory_manifest_checksum_and_path_controls()
    test_build_cleans_stale_output()
    test_build_rejects_traversal_and_symlinked_ancestors_without_mutation()
    print(json.dumps({
        "status": "PASS",
        "decision_id": "D-387",
        "blocker_families": 4,
        "schema": "FAIL_CLOSED",
        "inventory": "EXACT_RECURSIVE",
        "provenance_entity_integrity": "PASS",
    }, sort_keys=True))


if __name__ == "__main__":
    run()
