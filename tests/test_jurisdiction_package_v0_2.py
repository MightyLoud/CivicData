import importlib.util
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).parents[1]
P = ROOT / "tools" / "jurisdiction_package.py"
spec = importlib.util.spec_from_file_location("jp", P)
jp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(jp)


def fixture_v02():
    return {
        "schema_version": "0.2",
        "jurisdiction": {
            "jurisdiction_id": "jurisdiction-test",
            "name": "Test City",
            "state_abbr": "WA",
            "geoid": "5399999",
        },
        "records": {
            "divisions": [{"division_id": "division-test", "name": "Test City"}],
            "bodies": [{"body_id": "body-test", "name": "Test Council"}],
            "offices": [{"office_id": "office-test", "name": "Mayor"}],
            "people": [
                {"person_id": "person-winner", "name": "Winner Person"},
                {"person_id": "person-loser", "name": "Loser Person"},
            ],
            "role_terms": [
                {"role_term_id": "term-winner", "person_id": "person-winner", "office_id": "office-test"}
            ],
            "leadership_roles": [],
            "identifier_crosswalk": [],
            "elections": [
                {
                    "election_id": "election-test-2025",
                    "election_date": "2025-11-04",
                    "source_ids": ["src-election"],
                }
            ],
            "contests": [
                {
                    "contest_id": "contest-test-mayor-2025",
                    "election_id": "election-test-2025",
                    "office_id": "office-test",
                    "contest_name": "Mayor",
                    "source_ids": ["src-election"],
                }
            ],
            "candidacies": [
                {
                    "candidacy_id": "candidacy-winner",
                    "contest_id": "contest-test-mayor-2025",
                    "candidate_kind": "PERSON",
                    "source_candidate_id": "source-candidate-winner",
                    "person_id": "person-winner",
                    "candidate_name": "Winner Person",
                    "ballot_name": "Winner Person",
                    "source_id": "src-election",
                    "outcome": "WINNER",
                    "votes": 100,
                    "vote_share": 0.6,
                },
                {
                    "candidacy_id": "candidacy-loser",
                    "contest_id": "contest-test-mayor-2025",
                    "candidate_kind": "PERSON",
                    "source_candidate_id": "source-candidate-loser",
                    "person_id": "person-loser",
                    "candidate_name": "Loser Person",
                    "ballot_name": "Loser Person",
                    "source_id": "src-election",
                    "outcome": "LOSER",
                    "votes": 65,
                    "vote_share": 0.39,
                },
                {
                    "candidacy_id": "candidacy-writein",
                    "contest_id": "contest-test-mayor-2025",
                    "candidate_kind": "WRITE_IN_BUCKET",
                    "source_candidate_id": "write-in-bucket",
                    "person_id": None,
                    "candidate_name": "Write-in",
                    "ballot_name": "Write-in",
                    "source_id": "src-election",
                    "outcome": "OTHER",
                    "votes": 2,
                    "vote_share": 0.01,
                },
            ],
        },
        "provenance": {
            "source_evidence": [{"source_id": "src-election", "url": "https://example.gov/election"}],
            "source_assertions": [],
        },
        "qa": {
            "parity_ok": True,
            "qa_fail_count": 0,
            "blocking_gap_count": 0,
            "address_tests": [{"result": True}, {"result": True}],
            "checks": [],
            "election_scope_complete": True,
            "unexplained_loss": 0,
        },
        "warnings": [],
    }


def fixture_v01():
    x = fixture_v02()
    x["schema_version"] = "0.1"
    for table in ("elections", "contests", "candidacies"):
        del x["records"][table]
    x["qa"].pop("election_scope_complete")
    x["qa"].pop("unexplained_loss")
    return x


def run():
    assert jp.validate(fixture_v01()) == []
    assert jp.validate(fixture_v02()) == []

    x = fixture_v02()
    x["records"]["candidacies"][1]["person_id"] = "person-missing"
    assert "candidacy_person_fk" in jp.validate(x)

    x = fixture_v02()
    x["records"]["candidacies"][2]["person_id"] = "person-winner"
    assert "write_in_person_forbidden" in jp.validate(x)

    x = fixture_v02()
    x["records"]["contests"][0]["election_id"] = "missing-election"
    assert "contest_election_fk" in jp.validate(x)

    x = fixture_v02()
    x["records"]["candidacies"][0]["source_id"] = "missing-source"
    assert "candidacy_source_fk" in jp.validate(x)

    x = fixture_v02()
    x["qa"]["election_scope_complete"] = False
    assert "election_scope_complete" in jp.validate(x)

    x = fixture_v02()
    x["qa"]["unexplained_loss"] = 1
    assert "unexplained_loss" in jp.validate(x)

    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d)
        jp.build(fixture_v02(), out)
        assert (out / "elections.csv").exists()
        assert (out / "contests.csv").exists()
        assert (out / "candidacies.csv").exists()
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == "0.2"
        assert any(row["path"] == "candidacies.csv" for row in manifest["files"])

    print(json.dumps({
        "status": "PASS",
        "v01_backward_compatible": True,
        "v02_election_contract": True,
        "named_candidate_identity": "FAIL-CLOSED",
        "write_in_identity": "NON_PERSON",
        "election_scope_complete_required": True,
        "unexplained_loss_required": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
