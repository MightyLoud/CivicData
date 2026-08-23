#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "consumers" / "empowered_vote" / "package_source.py"
TACOMA_ARCHIVE = ROOT / "data" / "packages" / "wa" / "tacoma" / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip"
STACKED_PROOF = ROOT / "data" / "reference" / "wa" / "tacoma" / "EV-IMP-002_Tacoma_Stacked_Proof_2026-08-23.json"

spec = importlib.util.spec_from_file_location("ev_package_source", SRC)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def fixture_v01():
    return {
        "schema_version": "0.1",
        "jurisdiction": {"jurisdiction_id": "jurisdiction:us/wa/tacoma", "name": "City of Tacoma", "state_abbr": "WA", "geoid": "5370000", "division_id": "division:us/wa/tacoma"},
        "records": {
            "divisions": [{"division_id": "division:us/wa/tacoma"}],
            "bodies": [{"body_id": "body:us/wa/tacoma/city_council"}],
            "offices": [{"office_id": "office:us/wa/tacoma/mayor", "name": "Mayor", "geography_id": "division:us/wa/tacoma", "current_status": "CURRENT", "source_id": "SRC-TAC-COUNCIL"}],
            "people": [{"person_id": "person:anders_ibsen", "name": "Anders Ibsen"}],
            "role_terms": [{"role_term_id": "role-term:1", "person_id": "person:anders_ibsen", "office_id": "office:us/wa/tacoma/mayor", "currentness_status": "CURRENT_VERIFIED", "selection_method": "ELECTION", "term_start": "2026-01-01", "term_end": "2029-12-31", "source_id": "SRC-TAC-COUNCIL"}],
            "leadership_roles": [], "identifier_crosswalk": [],
        },
        "provenance": {"source_evidence": [{"source_id": "SRC-TAC-COUNCIL", "Title": "Council", "Source_URL_or_File": "https://tacoma.gov/"}], "source_assertions": []},
        "qa": {"parity_ok": True, "qa_fail_count": 0, "blocking_gap_count": 0, "address_tests": [{"control_id": "1", "input": "747 Market Street, Tacoma, WA 98402", "result": True, "fixture_tacoma_division_id": "division:us/wa/tacoma", "resolved_jurisdictions": ["jur-us-wa-tacoma"], "district_assignments": {}}, {"control_id": "2", "input": "6500 South Sheridan Avenue, Tacoma, WA 98408", "result": True, "fixture_tacoma_division_id": "division:us/wa/tacoma", "resolved_jurisdictions": ["jur-us-wa-tacoma"], "district_assignments": {}}], "checks": []},
        "warnings": [],
    }


def fixture_v02():
    x = fixture_v01()
    x["schema_version"] = "0.2"
    x["records"]["elections"] = [{"election_id": "election:us/wa/pierce/2025-11-04", "election_date": "2025-11-04", "source_ids": ["SRC-TAC-EL-2025"]}]
    x["records"]["contests"] = [{"contest_id": "contest:us/wa/tacoma/mayor/2025-11-04", "election_id": "election:us/wa/pierce/2025-11-04", "office_id": "office:us/wa/tacoma/mayor", "contest_name": "Mayor", "source_ids": ["SRC-TAC-EL-2025"]}]
    x["records"]["candidacies"] = [
        {"candidacy_id": "cand:anders", "contest_id": "contest:us/wa/tacoma/mayor/2025-11-04", "candidate_kind": "PERSON", "source_candidate_id": "person-or-candidate:anders_ibsen", "person_id": "person:anders_ibsen", "candidate_name": "Anders Ibsen", "ballot_name": "Anders Ibsen", "source_id": "SRC-TAC-EL-2025", "outcome": "WINNER", "votes": 1, "vote_share": 0.99},
        {"candidacy_id": "cand:writein", "contest_id": "contest:us/wa/tacoma/mayor/2025-11-04", "candidate_kind": "WRITE_IN_BUCKET", "source_candidate_id": "candidate:write-in/test", "person_id": None, "candidate_name": "Write-in", "ballot_name": "Write-in", "source_id": "SRC-TAC-EL-2025", "outcome": "OTHER", "votes": 0, "vote_share": 0.01},
    ]
    x["provenance"]["source_evidence"].append({"source_id": "SRC-TAC-EL-2025", "Title": "Election", "Source_URL_or_File": "https://results.vote.wa.gov/"})
    x["qa"]["election_scope_complete"] = True
    x["qa"]["unexplained_loss"] = 0
    return x


def build_package(root: Path, package: dict):
    root.mkdir(parents=True, exist_ok=True)
    jurisdiction = mod.canonical_json_bytes(package)
    qa = mod.canonical_json_bytes(package["qa"])
    (root / "jurisdiction.json").write_bytes(jurisdiction)
    (root / "qa_report.json").write_bytes(qa)
    manifest = {"schema_version": package["schema_version"], "jurisdiction_id": package["jurisdiction"]["jurisdiction_id"], "files": [{"path": "jurisdiction.json", "bytes": len(jurisdiction)}, {"path": "qa_report.json", "bytes": len(qa)}]}
    manifest_bytes = mod.canonical_json_bytes(manifest)
    (root / "manifest.json").write_bytes(manifest_bytes)
    sums = "".join(f"{mod.sha256_file(root / name)}  {name}\n" for name in ("jurisdiction.json", "qa_report.json", "manifest.json"))
    (root / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")


def assert_code(fn, code):
    try:
        fn()
    except mod.PackageContractError as exc:
        assert exc.code == code, (exc.code, str(exc))
    else:
        raise AssertionError(f"expected {code}")


def assert_real_tacoma_package():
    assert TACOMA_ARCHIVE.is_file(), TACOMA_ARCHIVE
    assert STACKED_PROOF.is_file(), STACKED_PROOF
    proof = json.loads(STACKED_PROOF.read_text(encoding="utf-8"))
    assert proof["status"] == "PASS"
    assert proof["package_schema_version"] == "0.2"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(TACOMA_ARCHIVE) as zf:
            zf.extractall(root)
        package_dir = root / "Tacoma_Jurisdiction_Package_v0.2_2026-08-23" / "package"
        assert package_dir.is_dir(), package_dir
        before = mod.directory_digest(package_dir)
        package = mod.load_jurisdiction_package(package_dir)
        after = mod.directory_digest(package_dir)
        assert before == after
        assert package["schema_version"] == "0.2"
        assert package["jurisdiction"]["jurisdiction_id"] == "jurisdiction:us/wa/tacoma"
        assert mod.package_capabilities(package) == {"representation": True, "elections": True, "full_essentials": True, "read_only": True}
        assert len(package["records"]["offices"]) == 10
        assert len(package["records"]["people"]) == 17
        assert len(package["records"]["elections"]) == 2
        assert len(package["records"]["contests"]) == 9
        assert len(package["records"]["candidacies"]) == 26

        market = mod.build_essentials_from_package(package, "747 Market Street, Tacoma, WA 98402")
        assert market["status"] == "PASS"
        assert market["canonical_writes"] == 0
        assert len(market["applicable_offices"]) == 6
        assert len(market["recent_certified_contests"]) == 5
        assert sum(len(x["candidates"]) for x in market["recent_certified_contests"]) == 15
        assert market["district_assignments"]["DIST-WA-TACOMA-COUNCIL"] == "2"

        wapato = mod.build_essentials_from_package(package, "6500 South Sheridan Avenue, Tacoma, WA 98408")
        assert wapato["status"] == "PASS"
        assert len(wapato["applicable_offices"]) == 6
        assert wapato["district_assignments"]["DIST-WA-TACOMA-COUNCIL"] == "5"

        lakewood = mod.build_essentials_from_package(package, "6000 Main St SW, Lakewood, WA 98499")
        assert lakewood["status"] == "PASS"
        assert lakewood["applicable_offices"] == []
        assert lakewood["recent_certified_contests"] == []

        market2 = mod.build_essentials_from_package(package, "747 Market Street, Tacoma, WA 98402")
        assert market["deterministic_sha256"] == market2["deterministic_sha256"]
        unsupported = mod.build_essentials_from_package(package, "1 Made Up Road, Tacoma, WA")
        assert unsupported["status"] == "FAIL-CLOSED"
        assert unsupported["error"] == "ADDRESS_NOT_IN_GOVERNED_PACKAGE"
        assert unsupported["canonical_writes"] == 0


def run():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "v01"
        build_package(p, fixture_v01())
        before = mod.directory_digest(p)
        package = mod.load_jurisdiction_package(p)
        after = mod.directory_digest(p)
        assert before == after
        assert mod.package_capabilities(package) == {"representation": True, "elections": False, "full_essentials": False, "read_only": True}
        rep = mod.representation_projection(package)
        assert rep["status"] == "PASS" and rep["canonical_writes"] == 0
        assert_code(lambda: mod.require_full_essentials(package), "FULL_ESSENTIALS_UNSUPPORTED_BY_PACKAGE_V0_1")
        (p / "jurisdiction.json").write_text("{}\n", encoding="utf-8")
        assert_code(lambda: mod.load_jurisdiction_package(p), "PACKAGE_CHECKSUM_MISMATCH")

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "v02"
        build_package(p, fixture_v02())
        package = mod.load_jurisdiction_package(p)
        assert mod.package_capabilities(package) == {"representation": True, "elections": True, "full_essentials": True, "read_only": True}
        model = mod.build_essentials_from_package(package, "747 Market Street, Tacoma, WA 98402")
        assert model["status"] == "PASS" and model["canonical_writes"] == 0
        candidates = model["recent_certified_contests"][0]["candidates"]
        assert candidates[0]["person_id"] == "person:anders_ibsen"
        assert candidates[1]["person_id"] is None and candidates[1]["is_write_in_bucket"] is True

    assert_real_tacoma_package()
    print(json.dumps({"status": "PASS", "v01_backward_compatibility": "PASS", "v02_contract": "PASS", "real_tacoma_package": "PASS", "full_essentials": "PASS", "read_only": "PASS", "determinism": "PASS", "tamper_detection": "PASS", "canonical_writes": 0}, sort_keys=True))


if __name__ == "__main__":
    run()
