#!/usr/bin/env python3
"""Read-only Empowered.Vote Essentials adapter for EV-CDT-001 fixtures.

EV-IMP-001 is deliberately bounded: the adapter consumes a governed frozen
consumer payload, resolves only addresses that are already present as governed
address controls, and never mutates CivicData.Tech source data.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

TACOMA_JURISDICTION = "jur-us-wa-tacoma"
TACOMA_DIVISION = "division:us/wa/tacoma"


def _norm_address(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _source_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["Source_ID"]): row for row in payload.get("sources", [])}


def _official_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["office_id"]): row for row in payload.get("officials", [])}


def _control_for_address(payload: dict[str, Any], address: str) -> dict[str, Any] | None:
    target = _norm_address(address)
    for control in payload.get("address_controls", []):
        if _norm_address(str(control.get("input", ""))) == target:
            return control
    return None


def _source_projection(source: dict[str, Any] | None) -> dict[str, Any] | None:
    if not source:
        return None
    return {
        "source_id": source.get("Source_ID"),
        "title": source.get("Title"),
        "publisher": source.get("Publisher"),
        "url": source.get("Source_URL_or_File"),
        "authority_level": source.get("Authority_Level"),
        "verification_status": source.get("Verification_Status"),
        "verified_as_of": source.get("Verified_As_Of_ISO"),
    }


def build_essentials(payload: dict[str, Any], address: str) -> dict[str, Any]:
    """Build a deterministic, read-only Essentials model for one frozen control."""
    control = _control_for_address(payload, address)
    if control is None:
        return {
            "status": "FAIL-CLOSED",
            "error": "ADDRESS_NOT_IN_FROZEN_FIXTURE",
            "input_address": address,
            "supported_addresses": sorted(
                str(x.get("input")) for x in payload.get("address_controls", [])
            ),
            "canonical_writes": 0,
        }

    source_idx = _source_index(payload)
    official_idx = _official_index(payload)
    resolved_jurisdictions = list(control.get("resolved_jurisdictions", []))
    tacoma_active = TACOMA_JURISDICTION in resolved_jurisdictions
    district_division = control.get("fixture_tacoma_division_id")

    applicable_offices: list[dict[str, Any]] = []
    applicable_office_ids: set[str] = set()
    if tacoma_active:
        for office in payload.get("offices", []):
            geography_id = office.get("geography_id")
            if geography_id not in {TACOMA_DIVISION, district_division}:
                continue
            office_id = str(office["id"])
            applicable_office_ids.add(office_id)
            official = official_idx.get(office_id)
            source_id = (official or {}).get("source_id") or office.get("source_id")
            source = _source_projection(source_idx.get(str(source_id)))
            applicable_offices.append(
                {
                    "office_id": office_id,
                    "office_name": office.get("name"),
                    "seat_type": (official or {}).get("seat_type") or office.get("classification_or_role"),
                    "division_id": geography_id,
                    "current_status": office.get("current_status"),
                    "holder": None if not official else {
                        "person_id": official.get("person_id"),
                        "name": official.get("person_name"),
                        "currentness_status": official.get("currentness_status"),
                        "leadership_role": official.get("leadership_role"),
                        "selection_method": official.get("selection_method"),
                        "term_start": (official.get("term_start") or {}).get("iso_date"),
                        "term_end": (official.get("term_end") or {}).get("iso_date"),
                        "term_end_basis": official.get("term_end_basis"),
                    },
                    "provenance": source,
                }
            )

    contests = []
    contest_ids: set[str] = set()
    for contest in payload.get("contests", []):
        if contest.get("office_id") not in applicable_office_ids:
            continue
        contest_id = str(contest["contest_id"])
        contest_ids.add(contest_id)
        source_id = (contest.get("source_ids") or [None])[0]
        contests.append(
            {
                "contest_id": contest_id,
                "contest_name": contest.get("contest_name"),
                "election_id": contest.get("election_id"),
                "office_id": contest.get("office_id"),
                "provenance": _source_projection(source_idx.get(str(source_id))),
            }
        )

    candidacies_by_contest: dict[str, list[dict[str, Any]]] = {cid: [] for cid in contest_ids}
    person_lookup = {
        str(row.get("candidate_id")): row.get("person_id")
        for row in payload.get("candidate_identities", [])
        if row.get("person_id")
    }
    for candidacy in payload.get("candidacies", []):
        contest_id = str(candidacy.get("contest_id"))
        if contest_id not in contest_ids:
            continue
        source_candidate_id = str(candidacy.get("source_candidate_id"))
        candidacies_by_contest[contest_id].append(
            {
                "candidacy_id": candidacy.get("candidacy_id"),
                "candidate_source_id": source_candidate_id,
                "person_id": person_lookup.get(source_candidate_id),
                "candidate_name": candidacy.get("candidate_name"),
                "ballot_name": candidacy.get("ballot_name"),
                "outcome": candidacy.get("outcome"),
                "votes": candidacy.get("votes"),
                "vote_share": candidacy.get("vote_share"),
                "is_write_in_bucket": source_candidate_id.startswith("candidate:write-in/"),
                "provenance": _source_projection(source_idx.get(str(candidacy.get("source_id")))),
            }
        )

    for contest in contests:
        contest["candidates"] = sorted(
            candidacies_by_contest[contest["contest_id"]],
            key=lambda row: (
                0 if row.get("outcome") == "WINNER" else 1,
                str(row.get("candidate_name") or ""),
                str(row.get("candidate_source_id") or ""),
            ),
        )

    applicable_offices.sort(key=lambda row: (str(row["seat_type"]), str(row["office_name"])))
    contests.sort(key=lambda row: (str(row["election_id"]), str(row["contest_name"])))

    model: dict[str, Any] = {
        "status": "PASS",
        "contract_id": payload.get("contract_id"),
        "fixture_id": payload.get("fixture_id"),
        "consumer_gate": "EV-IMP-001",
        "input_address": address,
        "address_control_id": control.get("control_id"),
        "resolved_jurisdictions": sorted(resolved_jurisdictions),
        "district_assignments": dict(sorted((control.get("district_assignments") or {}).items())),
        "jurisdiction": payload.get("jurisdiction") if tacoma_active else None,
        "representation_scope_note": (
            "Detailed representation shown here is limited to the frozen Tacoma FX01 package. "
            "Other resolved jurisdictions may be present without detailed officials in this fixture."
        ),
        "applicable_offices": applicable_offices,
        "recent_certified_contests": contests,
        "known_scope_limits": payload.get("known_gaps", []),
        "warnings": payload.get("warnings", []),
        "source_snapshot": payload.get("scope", {}).get("snapshot_as_of"),
        "canonical_writes": 0,
    }
    canonical_bytes = json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    model["deterministic_sha256"] = hashlib.sha256(canonical_bytes).hexdigest()
    return model


def load_payload(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_model(model: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(model, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
