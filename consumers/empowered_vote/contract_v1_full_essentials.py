#!/usr/bin/env python3
"""Empowered Vote Full Essentials consumer for Contract v1 election extension.

Representation remains the base authority. Elections, contests, and candidacies
are consumed only when the optional Contract v1 election extension is separately
certified. Civic GPS contributes geography only.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Mapping

from consumers.empowered_vote import contract_v1, package_source

CONSUMER_GATE = "EV-RC1-FULL-001"


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "FAIL-CLOSED",
        "consumer_gate": CONSUMER_GATE,
        "input_address": address,
        "error": code,
        "canonical_writes": 0,
    }
    if detail:
        out["detail"] = detail
    return out


def _identifier(row: Mapping[str, Any], scheme: str) -> str | None:
    for identifier in row.get("identifiers") or []:
        if (
            isinstance(identifier, Mapping)
            and identifier.get("scheme") == scheme
            and identifier.get("id") not in (None, "")
        ):
            return str(identifier["id"])
    return None


def _provenance(evidence: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if evidence is None:
        return None
    raw = evidence.get("raw_record")
    raw = raw if isinstance(raw, Mapping) else {}
    return {
        "source_id": (
            raw.get("source_id")
            or raw.get("Source_ID")
            or _identifier(evidence, "civicdata_factory_evidence")
        ),
        "title": evidence.get("title") or raw.get("title") or raw.get("Title"),
        "publisher": raw.get("publisher") or raw.get("Publisher"),
        "url": evidence.get("url"),
        "authority_level": raw.get("authority_level") or raw.get("Authority_Level"),
        "verification_status": raw.get("verification_status") or raw.get("Verification_Status"),
        "verified_as_of": (
            raw.get("verified_as_of")
            or raw.get("Verified_As_Of_ISO")
            or evidence.get("captured_at")
        ),
    }


def _first_evidence(
    row: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    refs = row.get("evidence_ids")
    if not isinstance(refs, list) or not refs:
        return None
    source = evidence_by_id.get(str(refs[0]))
    return _provenance(source)


def build_full_essentials_from_civic_gps_result(
    contract: dict[str, Any],
    address: str,
    civic_gps_result: Any,
    *,
    binding: dict[str, Any],
) -> dict[str, Any]:
    """Join Contract-certified civic facts to Civic GPS geography."""
    errors = contract_v1.validate_contract(
        contract,
        require_certified=True,
        require_elections=True,
    )
    if errors:
        election_errors = [
            error
            for error in errors
            if (
                "ELECTION" in error
                or "CANDIDACY" in error
                or "CONTEST" in error
                or "WRITE_IN" in error
            )
        ]
        primary = "CONTRACT_ELECTIONS_NOT_CERTIFIED" if "CONTRACT_ELECTIONS_NOT_CERTIFIED" in errors else (
            "CONTRACT_ELECTION_EXTENSION_INVALID" if election_errors else
            ("CONTRACT_NOT_CERTIFIED" if "CONTRACT_NOT_CERTIFIED" in errors else "CONTRACT_INVALID")
        )
        return _fail(address, primary, ",".join(errors))

    representation = contract_v1.build_representation_from_civic_gps_result(
        contract,
        address,
        civic_gps_result,
        binding=binding,
    )
    if representation.get("status") != "PASS":
        return representation

    applicable_post_ids = {
        str(row.get("post_id"))
        for row in representation.get("applicable_offices", [])
        if isinstance(row, Mapping) and row.get("post_id")
    }
    if not applicable_post_ids:
        return _fail(address, "CONTRACT_APPLICABLE_POSTS_EMPTY")

    evidence_by_id = {
        str(row["id"]): row
        for row in contract.get("evidence", [])
        if isinstance(row, Mapping) and row.get("id")
    }
    elections_by_id = {
        str(row["id"]): row
        for row in contract.get("elections", [])
        if isinstance(row, Mapping) and row.get("id")
    }
    people_by_id = {
        str(row["id"]): row
        for row in contract.get("people", [])
        if isinstance(row, Mapping) and row.get("id")
    }

    candidacies_by_contest: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidacy in contract.get("candidacies", []):
        if isinstance(candidacy, Mapping):
            candidacies_by_contest[str(candidacy.get("contest_id"))].append(candidacy)

    contests: list[dict[str, Any]] = []
    for contest in contract.get("contests", []):
        if not isinstance(contest, Mapping) or str(contest.get("post_id")) not in applicable_post_ids:
            continue
        election = elections_by_id.get(str(contest.get("election_id")))
        if election is None:
            return _fail(address, "CONTRACT_CONTEST_ELECTION_FK", str(contest.get("id")))

        contract_contest_id = str(contest["id"])
        legacy_contest_id = _identifier(contest, "civicdata_factory_contest") or contract_contest_id
        legacy_election_id = _identifier(election, "civicdata_factory_election") or str(election["id"])

        post = next(
            (
                row
                for row in representation["applicable_offices"]
                if str(row.get("post_id")) == str(contest.get("post_id"))
            ),
            None,
        )
        if post is None:
            return _fail(address, "CONTRACT_CONTEST_POST_NOT_APPLICABLE", contract_contest_id)

        candidate_rows: list[dict[str, Any]] = []
        for candidacy in candidacies_by_contest.get(contract_contest_id, []):
            contract_person_id = candidacy.get("person_id")
            person = (
                people_by_id.get(str(contract_person_id))
                if contract_person_id is not None
                else None
            )
            legacy_person_id = (
                _identifier(person, "civicdata_factory_person")
                if person is not None
                else None
            )
            kind = candidacy.get("candidate_kind")
            candidate_rows.append(
                {
                    "candidacy_id": (
                        _identifier(candidacy, "civicdata_factory_candidacy")
                        or str(candidacy["id"])
                    ),
                    "contract_candidacy_id": str(candidacy["id"]),
                    "candidate_source_id": candidacy.get("source_candidate_id"),
                    "person_id": legacy_person_id,
                    "contract_person_id": contract_person_id,
                    "shared_person_id": (
                        person.get("shared_identity_id")
                        if person is not None
                        else None
                    ),
                    "candidate_name": candidacy.get("candidate_name"),
                    "ballot_name": candidacy.get("ballot_name"),
                    "outcome": (
                        str(candidacy["outcome"]).upper()
                        if candidacy.get("outcome") is not None
                        else None
                    ),
                    "votes": candidacy.get("votes"),
                    "vote_share": candidacy.get("vote_share"),
                    "is_write_in_bucket": kind == "write_in_bucket",
                    "provenance": _first_evidence(candidacy, evidence_by_id),
                }
            )
        candidate_rows.sort(
            key=lambda row: (
                0 if row.get("outcome") == "WINNER" else 1,
                str(row.get("candidate_name") or ""),
                str(row.get("candidate_source_id") or ""),
            )
        )

        contests.append(
            {
                "contest_id": legacy_contest_id,
                "contract_contest_id": contract_contest_id,
                "contest_name": contest.get("name"),
                "election_id": legacy_election_id,
                "contract_election_id": str(election["id"]),
                "election_date": election.get("election_date"),
                "office_id": post.get("office_id"),
                "post_id": post.get("post_id"),
                "provenance": _first_evidence(contest, evidence_by_id),
                "candidates": candidate_rows,
            }
        )

    contests.sort(
        key=lambda row: (
            str(row.get("election_date") or ""),
            str(row.get("contest_name") or ""),
            str(row.get("contest_id") or ""),
        )
    )

    out = copy.deepcopy(representation)
    out["consumer_gate"] = CONSUMER_GATE
    out["representation_only"] = False
    out["full_essentials_supported"] = True
    out["recent_certified_contests"] = contests
    out["election_certification"] = copy.deepcopy(contract["election_certification"])
    out["canonical_writes"] = 0
    out.pop("deterministic_sha256", None)
    out["deterministic_sha256"] = package_source.sha256_bytes(
        package_source.canonical_json_bytes(out)
    )
    return out
