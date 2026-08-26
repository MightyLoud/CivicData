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


def test_schema_is_enforced_and_assertion_hash_is_field_scoped():
    rows = packages()
    assert all(cep.validate_schema(row) == [] for row in rows)
    base = rows[0]
    assert all(
        row["assertion_kind"] in {"IDENTITY", "RELATIONSHIP"}
        and "asserted_value_hash" not in row
        for row in base["provenance"]["evidence_links"]
    )

    changed = copy.deepcopy(base)
    del changed["source_authority"]["workbook_title"]
    assert "schema:$.source_authority.workbook_title:required" in cep.validate_package(
        changed
    )

    changed = copy.deepcopy(base)
    changed["unexpected_top_level"] = "not allowed"
    assert "schema:$.unexpected_top_level:additionalProperties" in cep.validate_package(
        changed
    )

    changed = copy.deepcopy(base)
    changed["generated_at"] = "not-a-date-time"
    assert "schema:$.generated_at:format" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    del changed["provenance"]["source_evidence"][0]["source_url"]
    assert (
        "schema:$.provenance.source_evidence[0].source_url:required"
        in cep.validate_package(changed)
    )

    changed = copy.deepcopy(base)
    changed["provenance"]["evidence_links"][0]["assertion_kind"] = "FIELD"
    assert (
        "schema:$.provenance.evidence_links[0].asserted_value_hash:required"
        in cep.validate_package(changed)
    )
    changed["provenance"]["evidence_links"][0]["asserted_value_hash"] = "0" * 64
    assert cep.validate_package(changed) == []

    changed = copy.deepcopy(base)
    changed["provenance"]["evidence_links"][0]["assertion_kind"] = "FIELDD"
    errors = cep.validate_package(changed)
    assert (
        "schema:$.provenance.evidence_links[0].assertion_kind:enum" in errors
    )
    assert "evidence_link_assertion_kind" in errors

    changed = copy.deepcopy(base)
    changed["provenance"]["evidence_links"][0]["target_entity"] = "Person"
    assert "evidence_link_target_entity_fk" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["records"]["external_identifiers"] = [
        {"arbitrary_public_payload": "not governed"}
    ]
    errors = cep.validate_package(changed)
    assert "schema:$.records.external_identifiers:const" in errors
    assert "external_identifiers_reserved" in errors

    changed = copy.deepcopy(base)
    changed["generated_at"] = "2026-08-25 00:00:00-06:00"
    assert "schema:$.generated_at:format" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["source_authority"]["freshness_date"] = "2026-W35-2"
    assert (
        "schema:$.source_authority.freshness_date:format"
        in cep.validate_package(changed)
    )


def test_provenance_reconciliation_entity_and_format_attacks_fail_closed():
    rows = packages()
    base = rows[0]

    changed = copy.deepcopy(base)
    first_source = changed["provenance"]["source_record_refs"][0][
        "source_record_id"
    ]
    for evidence in changed["provenance"]["source_evidence"]:
        evidence["source_record_id"] = first_source
    assert "source_record_evidence_coverage" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    first_context_source = changed["provenance"]["context_source_record_refs"][0][
        "source_record_id"
    ]
    for evidence in changed["provenance"]["context_evidence"]:
        evidence["source_record_id"] = first_context_source
    assert (
        "context_source_record_evidence_coverage"
        in cep.validate_package(changed)
    )

    changed = copy.deepcopy(base)
    changed["provenance"]["source_record_refs"][0]["record_type"] = "Structure"
    assert (
        "public_source_record_type_reconciliation"
        in cep.validate_package(changed)
    )

    changed = copy.deepcopy(base)
    changed["provenance"]["source_record_refs"][1]["source_native_id"] = (
        changed["provenance"]["source_record_refs"][0]["source_native_id"]
    )
    assert "duplicate_source_native_id" in cep.validate_package(changed)

    kyle = copy.deepcopy(
        next(
            row
            for row in rows
            if row["jurisdiction"]["source_jurisdiction_key"] == "39952"
        )
    )
    first_excluded = copy.deepcopy(
        kyle["reconciliation"]["excluded_source_records"][0]
    )
    kyle["reconciliation"]["excluded_source_records"] = [
        copy.deepcopy(first_excluded) for _ in range(5)
    ]
    errors = cep.validate_package(kyle)
    assert "duplicate_excluded_source_record_id" in errors
    assert "duplicate_excluded_source_native_id" in errors
    assert "excluded_source_record_type_reconciliation" in errors

    kyle = copy.deepcopy(
        next(
            row
            for row in rows
            if row["jurisdiction"]["source_jurisdiction_key"] == "39952"
        )
    )
    kyle["reconciliation"]["excluded_source_records"][0][
        "source_record_id"
    ] = kyle["provenance"]["source_record_refs"][0]["source_record_id"]
    assert "excluded_source_record_overlap" in cep.validate_package(kyle)

    kyle = copy.deepcopy(
        next(
            row
            for row in rows
            if row["jurisdiction"]["source_jurisdiction_key"] == "39952"
        )
    )
    kyle["reconciliation"]["excluded_source_records"][0][
        "source_native_id"
    ] = kyle["provenance"]["source_record_refs"][0]["source_native_id"]
    assert "excluded_source_native_id_overlap" in cep.validate_package(kyle)

    changed = copy.deepcopy(base)
    changed["records"]["contact_points"] = [
        {
            "contact_point_id": "contact-person-owned",
            "person_id": changed["records"]["people"][0]["person_id"],
            "contact_type": "EMAIL",
            "contact_value_normalized": "public@example.com",
            "sensitivity": "PUBLIC",
            "publication_ok": "TRUE",
            "source_evidence_id": changed["provenance"]["source_evidence"][0][
                "source_evidence_id"
            ],
            "contact_status": "ACTIVE",
        }
    ]
    assert cep.validate_package(changed) == []

    changed = copy.deepcopy(base)
    changed["records"]["contact_points"] = [
        {
            "contact_point_id": "contact-unowned",
            "contact_type": "EMAIL",
            "contact_value_normalized": "public@example.com",
            "sensitivity": "PUBLIC",
            "publication_ok": "TRUE",
            "source_evidence_id": changed["provenance"]["source_evidence"][0][
                "source_evidence_id"
            ],
            "contact_status": "ACTIVE",
        }
    ]
    assert "schema:$.records.contact_points[0]:oneOf" in cep.validate_schema(
        changed
    )
    assert "contact_owner_cardinality" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["records"]["contact_points"] = [
        {
            "contact_point_id": "contact-double-owned",
            "person_id": changed["records"]["people"][0]["person_id"],
            "candidacy_id": changed["records"]["candidacies"][0][
                "candidacy_id"
            ],
            "contact_type": "EMAIL",
            "contact_value_normalized": "public@example.com",
            "sensitivity": "PUBLIC",
            "publication_ok": "TRUE",
            "source_evidence_id": changed["provenance"]["source_evidence"][0][
                "source_evidence_id"
            ],
            "contact_status": "ACTIVE",
        }
    ]
    assert "schema:$.records.contact_points[0]:oneOf" in cep.validate_schema(
        changed
    )
    assert "contact_owner_cardinality" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    office_id = changed["records"]["offices"][0]["office_id"]
    old_person_id = changed["records"]["people"][0]["person_id"]
    changed["records"]["people"][0]["person_id"] = office_id
    for candidacy in changed["records"]["candidacies"]:
        if candidacy["person_id"] == old_person_id:
            candidacy["person_id"] = office_id
    changed["provenance"]["evidence_links"][0]["target_entity"] = "Person"
    changed["provenance"]["evidence_links"][0]["target_id"] = office_id
    assert "cross_entity_id_collision" in cep.validate_package(changed)

    changed = copy.deepcopy(base)
    changed["provenance"]["source_evidence"][0]["observed_at"] = "not-a-date"
    assert (
        "schema:$.provenance.source_evidence[0].observed_at:format"
        in cep.validate_package(changed)
    )

    changed = copy.deepcopy(base)
    changed["records"]["jurisdiction_divisions"][0]["valid_from"] = "2026-W35-2"
    assert (
        "schema:$.records.jurisdiction_divisions[0].valid_from:format"
        in cep.validate_package(changed)
    )

    changed = copy.deepcopy(base)
    for key in ("source_url", "source_url_normalized"):
        changed["provenance"]["source_evidence"][0][key] = (
            "https://example.com/not valid"
        )
    errors = cep.validate_package(changed)
    assert "schema:$.provenance.source_evidence[0].source_url:format" in errors
    assert (
        "schema:$.provenance.source_evidence[0].source_url_normalized:format"
        in errors
    )

    for malformed_uri in (
        "https://example.com/%ZZ",
        "https://example.com\\invalid",
        "https://example.com/{invalid}",
    ):
        changed = copy.deepcopy(base)
        for key in ("source_url", "source_url_normalized"):
            changed["provenance"]["source_evidence"][0][key] = malformed_uri
        errors = cep.validate_package(changed)
        assert "schema:$.provenance.source_evidence[0].source_url:format" in errors
        assert (
            "schema:$.provenance.source_evidence[0].source_url_normalized:format"
            in errors
        )

    changed = copy.deepcopy(base)
    for key in ("source_url", "source_url_normalized"):
        changed["provenance"]["source_evidence"][0][key] = (
            "https://example.com/valid%20path?x=1&y=2#fragment"
        )
    assert cep.validate_package(changed) == []

    duplicate_jurisdiction_bundle = copy.deepcopy(rows)
    duplicate_jurisdiction_bundle[1]["jurisdiction"]["jurisdiction_id"] = (
        duplicate_jurisdiction_bundle[0]["jurisdiction"]["jurisdiction_id"]
    )
    with tempfile.TemporaryDirectory() as output:
        try:
            cep.build_release(
                {
                    "contract_version": cep.CONTRACT_VERSION,
                    "release_id": cep.RELEASE_ID,
                    "packages": duplicate_jurisdiction_bundle,
                },
                pathlib.Path(output),
            )
        except ValueError as error:
            assert str(error) == "duplicate bundle jurisdiction_id"
        else:
            raise AssertionError("duplicate jurisdiction_id must fail closed")

    valid_bundle = {
        "contract_version": cep.CONTRACT_VERSION,
        "release_id": cep.RELEASE_ID,
        "packages": rows,
    }
    with tempfile.TemporaryDirectory() as output:
        output_root = pathlib.Path(output)
        manifest = cep.build_release(valid_bundle, output_root)
        duplicate_path = output_root / manifest["packages"][1]["path"] / "canonical.json"
        duplicate_package = json.loads(duplicate_path.read_text(encoding="utf-8"))
        duplicate_package["jurisdiction"]["jurisdiction_id"] = rows[0][
            "jurisdiction"
        ]["jurisdiction_id"]
        duplicate_path.write_text(
            cep.canonical_json(duplicate_package), encoding="utf-8"
        )
        assert "release_duplicate_jurisdiction_id" in cep.verify_release(
            output_root
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


def test_release_fails_closed_on_incomplete_or_tampered_aggregate():
    rows = packages()
    incomplete = {
        "contract_version": cep.CONTRACT_VERSION,
        "release_id": cep.RELEASE_ID,
        "packages": rows[:1],
    }
    with tempfile.TemporaryDirectory() as output:
        try:
            cep.build_release(incomplete, pathlib.Path(output))
        except ValueError as error:
            assert str(error) == "bundle package set"
        else:
            raise AssertionError("one-package fixed release must fail closed")

    bundle = {
        "contract_version": cep.CONTRACT_VERSION,
        "release_id": cep.RELEASE_ID,
        "packages": rows,
    }
    with tempfile.TemporaryDirectory() as output:
        output_root = pathlib.Path(output)
        cep.build_release(bundle, output_root)
        manifest_path = (
            output_root
            / "data"
            / "normalized"
            / "tx"
            / f"{cep.RELEASE_ID}.manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entity_totals"]["candidacies"] = 999
        manifest["qa_summary"]["parity_ok"] = False
        manifest_path.write_text(cep.canonical_json(manifest), encoding="utf-8")
        errors = cep.verify_release(output_root)
        assert any(error.startswith("release_output_mismatch:") for error in errors)


def test_filesystem_and_checksum_attacks_fail_closed():
    bundle = {
        "contract_version": cep.CONTRACT_VERSION,
        "release_id": cep.RELEASE_ID,
        "packages": packages(),
    }

    with tempfile.TemporaryDirectory() as output:
        output_root = pathlib.Path(output)
        manifest = cep.build_release(bundle, output_root)
        package_dir = output_root / manifest["packages"][0]["path"]
        unexpected = package_dir / "extra" / "unexpected.txt"
        unexpected.parent.mkdir()
        unexpected.write_text("unexpected\n", encoding="utf-8")
        package_errors = cep.verify_built_package(package_dir)
        assert "output_file_set" in package_errors
        assert "output_entry_type" in package_errors
        assert "release_output_file_set" in cep.verify_release(output_root)

    with tempfile.TemporaryDirectory() as output:
        output_root = pathlib.Path(output)
        manifest = cep.build_release(bundle, output_root)
        package_dir = output_root / manifest["packages"][0]["path"]
        sums_path = package_dir / "SHA256SUMS.txt"
        lines = sums_path.read_text(encoding="utf-8").splitlines()
        sums_path.write_text(
            "\n".join(lines + [lines[0]]) + "\n", encoding="utf-8"
        )
        assert "checksum_duplicate" in cep.verify_built_package(package_dir)
        assert any(
            error.startswith("release_output_mismatch:")
            for error in cep.verify_release(output_root)
        )

    with tempfile.TemporaryDirectory() as output:
        output_root = pathlib.Path(output)
        manifest = cep.build_release(bundle, output_root)
        package_dir = output_root / manifest["packages"][0]["path"]
        sums_path = package_dir / "SHA256SUMS.txt"
        sums_path.write_text(
            sums_path.read_text(encoding="utf-8")
            + f"{'0' * 64}  /definitely/not/here\n",
            encoding="utf-8",
        )
        assert "checksum_path" in cep.verify_built_package(package_dir)

    with tempfile.TemporaryDirectory() as output:
        output_root = pathlib.Path(output)
        manifest = cep.build_release(bundle, output_root)
        package_dir = output_root / manifest["packages"][0]["path"]
        manifest_path = package_dir / "manifest.json"
        package_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        package_manifest["files"][0]["path"] = "/etc/passwd"
        manifest_path.write_text(
            cep.canonical_json(package_manifest), encoding="utf-8"
        )
        errors = cep.verify_built_package(package_dir)
        assert "manifest_content" in errors
        assert "manifest_path" in errors


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
    test_schema_is_enforced_and_assertion_hash_is_field_scoped()
    test_provenance_reconciliation_entity_and_format_attacks_fail_closed()
    test_exact_package_set_and_reconciliation()
    test_aggregate_contract_totals()
    test_kyle_non_candidate_rows_are_accounted_not_published()
    test_built_outputs_verify()
    test_deterministic_release_rerun_is_byte_identical()
    test_release_fails_closed_on_incomplete_or_tampered_aggregate()
    test_filesystem_and_checksum_attacks_fail_closed()
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
