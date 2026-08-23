#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "consumers" / "empowered_vote"

spec = importlib.util.spec_from_file_location("ev_adapter", EV / "adapter.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


def fixture():
    return {
        "contract_id": "EV-CDT-001",
        "fixture_id": "EV-CDT-001-FX01",
        "scope": {"snapshot_as_of": "2026-08-02"},
        "jurisdiction": {"id": "jurisdiction:us/wa/tacoma", "name": "City of Tacoma"},
        "address_controls": [
            {
                "control_id": "TAC-GEO-INT-001",
                "input": "747 Market Street, Tacoma, WA 98402",
                "resolved_jurisdictions": ["jur-us-wa-pierce", "jur-us-wa-tacoma"],
                "district_assignments": {"DIST-WA-TACOMA-COUNCIL": "2", "DIST-WA-PIERCE-COUNCIL": "4"},
                "fixture_tacoma_division_id": "division:us/wa/tacoma/council_district_2",
            },
            {
                "control_id": "TAC-GEO-NEG-001",
                "input": "6000 Main St SW, Lakewood, WA 98499",
                "resolved_jurisdictions": ["jur-us-wa-pierce"],
                "district_assignments": {"DIST-WA-PIERCE-COUNCIL": "6"},
                "fixture_tacoma_division_id": None,
            },
        ],
        "sources": [
            {
                "Source_ID": "SRC-TAC-COUNCIL",
                "Title": "Meet Tacoma City Council",
                "Publisher": "City of Tacoma",
                "Source_URL_or_File": "https://tacoma.gov/government/departments/city-council/",
                "Authority_Level": "PRIMARY — OFFICIAL GOVERNMENT",
                "Verification_Status": "VERIFIED",
                "Verified_As_Of_ISO": "2026-08-02",
            },
            {
                "Source_ID": "SRC-TAC-EL-2025",
                "Title": "November 4, 2025 General Election",
                "Publisher": "Washington Secretary of State / Pierce County",
                "Source_URL_or_File": "https://results.vote.wa.gov/results/20251104/pierce/",
                "Authority_Level": "PRIMARY — OFFICIAL ELECTION ADMINISTRATOR",
                "Verification_Status": "VERIFIED",
                "Verified_As_Of_ISO": "2026-08-02",
            },
        ],
        "offices": [
            {"id": "office:us/wa/tacoma/mayor", "name": "Mayor", "geography_id": "division:us/wa/tacoma", "current_status": "CURRENT", "classification_or_role": "CITYWIDE legislative seat", "source_id": "SRC-TAC-COUNCIL"},
            {"id": "office:us/wa/tacoma/council/district_2", "name": "Councilmember — Position 2", "geography_id": "division:us/wa/tacoma/council_district_2", "current_status": "CURRENT", "classification_or_role": "DISTRICT legislative seat", "source_id": "SRC-TAC-COUNCIL"},
            {"id": "office:us/wa/tacoma/council/district_5", "name": "Councilmember — Position 5", "geography_id": "division:us/wa/tacoma/council_district_5", "current_status": "CURRENT", "classification_or_role": "DISTRICT legislative seat", "source_id": "SRC-TAC-COUNCIL"},
        ],
        "officials": [
            {"office_id": "office:us/wa/tacoma/mayor", "person_id": "person:anders_ibsen", "person_name": "Anders Ibsen", "seat_type": "CITYWIDE", "currentness_status": "CURRENT_VERIFIED", "selection_method": "ELECTION", "term_start": {"iso_date": "2026-01-01"}, "term_end": {"iso_date": "2029-12-31"}, "term_end_basis": "Four-year elected term", "source_id": "SRC-TAC-COUNCIL"},
            {"office_id": "office:us/wa/tacoma/council/district_2", "person_id": "person:sarah_rumbaugh", "person_name": "Sarah Rumbaugh", "seat_type": "DISTRICT", "currentness_status": "CURRENT_VERIFIED", "selection_method": "ELECTION", "term_start": {"iso_date": "2026-01-01"}, "term_end": {"iso_date": "2029-12-31"}, "term_end_basis": "Four-year elected term", "source_id": "SRC-TAC-COUNCIL"},
            {"office_id": "office:us/wa/tacoma/council/district_5", "person_id": "person:chanjolee_joe_bushnell", "person_name": "Chanjolee \"Joe\" Bushnell", "seat_type": "DISTRICT", "currentness_status": "CURRENT_VERIFIED", "selection_method": "ELECTION", "term_start": {"iso_date": "2026-01-01"}, "term_end": {"iso_date": "2029-12-31"}, "term_end_basis": "Four-year elected term", "source_id": "SRC-TAC-COUNCIL"},
        ],
        "contests": [
            {"contest_id": "contest:us/wa/tacoma/council/district_2/2025-11-04", "contest_name": "Council District No. 2", "election_id": "election:us/wa/pierce/2025-11-04", "office_id": "office:us/wa/tacoma/council/district_2", "source_ids": ["SRC-TAC-EL-2025"]},
        ],
        "candidacies": [
            {"candidacy_id": "ev-local:candidacy:sarah", "source_candidate_id": "person-or-candidate:sarah_rumbaugh", "candidate_name": "Sarah Rumbaugh", "ballot_name": "Sarah Rumbaugh", "contest_id": "contest:us/wa/tacoma/council/district_2/2025-11-04", "outcome": "WINNER", "votes": 7752, "vote_share": 0.6651, "source_id": "SRC-TAC-EL-2025"},
            {"candidacy_id": "ev-local:candidacy:ben", "source_candidate_id": "person-or-candidate:ben_lackey", "candidate_name": "Ben Lackey", "ballot_name": "Ben Lackey", "contest_id": "contest:us/wa/tacoma/council/district_2/2025-11-04", "outcome": "LOSER", "votes": 3836, "vote_share": 0.3291, "source_id": "SRC-TAC-EL-2025"},
            {"candidacy_id": "ev-local:candidacy:writein", "source_candidate_id": "candidate:write-in/us/wa/tacoma/council/district_2/2025-11-04", "candidate_name": "Write-in", "ballot_name": "Write-in", "contest_id": "contest:us/wa/tacoma/council/district_2/2025-11-04", "outcome": "OTHER", "votes": 67, "vote_share": 0.0057, "source_id": "SRC-TAC-EL-2025"},
        ],
        "candidate_identities": [
            {"candidate_id": "person-or-candidate:sarah_rumbaugh", "person_id": "person:sarah_rumbaugh"},
            {"candidate_id": "person-or-candidate:ben_lackey", "person_id": "person:ben_lackey"},
        ],
        "known_gaps": [{"Gap_ID": "TAC-GAP-005", "Status": "OUT OF SCOPE — V0.1"}],
        "warnings": [],
    }


def office_ids(model):
    return {row["office_id"] for row in model["applicable_offices"]}


def run():
    payload = fixture()
    market = mod.build_essentials(payload, "747 Market Street, Tacoma, WA 98402")
    assert market["status"] == "PASS"
    assert market["canonical_writes"] == 0
    assert set(market["resolved_jurisdictions"]) == {"jur-us-wa-pierce", "jur-us-wa-tacoma"}
    assert market["district_assignments"]["DIST-WA-TACOMA-COUNCIL"] == "2"
    assert office_ids(market) == {"office:us/wa/tacoma/mayor", "office:us/wa/tacoma/council/district_2"}
    d2 = next(x for x in market["applicable_offices"] if x["office_id"].endswith("district_2"))
    assert d2["holder"]["person_id"] == "person:sarah_rumbaugh"
    assert d2["holder"]["currentness_status"] == "CURRENT_VERIFIED"
    assert len(market["recent_certified_contests"]) == 1
    candidates = market["recent_certified_contests"][0]["candidates"]
    assert [x["outcome"] for x in candidates] == ["WINNER", "LOSER", "OTHER"]
    assert candidates[0]["person_id"] == "person:sarah_rumbaugh"
    assert candidates[1]["person_id"] == "person:ben_lackey"
    assert candidates[2]["person_id"] is None and candidates[2]["is_write_in_bucket"] is True
    assert all(x["provenance"] and x["provenance"]["url"] for x in market["applicable_offices"])

    market2 = mod.build_essentials(payload, "747 Market Street, Tacoma, WA 98402")
    assert market["deterministic_sha256"] == market2["deterministic_sha256"]

    lakewood = mod.build_essentials(payload, "6000 Main St SW, Lakewood, WA 98499")
    assert lakewood["status"] == "PASS"
    assert lakewood["resolved_jurisdictions"] == ["jur-us-wa-pierce"]
    assert lakewood["applicable_offices"] == []
    assert lakewood["recent_certified_contests"] == []

    unsupported = mod.build_essentials(payload, "1 Made Up Road, Tacoma, WA")
    assert unsupported["status"] == "FAIL-CLOSED"
    assert unsupported["error"] == "ADDRESS_NOT_IN_FROZEN_FIXTURE"
    assert unsupported["canonical_writes"] == 0

    print(json.dumps({
        "status": "PASS",
        "applicability": "PASS",
        "identity": "PASS",
        "provenance": "PASS",
        "determinism": "PASS",
        "unsupported_address": "FAIL-CLOSED",
        "canonical_writes": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    run()
