#!/usr/bin/env python3
"""SeeGov → shared civic spine read-only adapter.

Meetings/transcripts/moments remain SeeGov-owned. Only explicit representation
observations are translated into governed partner assertions.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Mapping

from adapters.partner_assertions import (
    PartnerAdapterError,
    PartnerAssertionBuilder,
)


def adapt_seegov_snapshot(
    snapshot: Mapping[str, Any],
    *,
    identity_registry: Mapping[str, Any],
    contract: Mapping[str, Any],
    base_snapshot_id: str,
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise PartnerAdapterError("SEEGOV_SNAPSHOT_INVALID")
    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    captured_at = str(snapshot.get("captured_at") or "").strip()
    jurisdiction_ocdid = str(snapshot.get("jurisdiction_ocdid") or "").strip()
    if not snapshot_id or not captured_at or not jurisdiction_ocdid.startswith("ocd-jurisdiction/"):
        raise PartnerAdapterError("SEEGOV_SNAPSHOT_METADATA_INVALID")

    builder = PartnerAssertionBuilder(
        source_system="seegov",
        identity_registry=identity_registry,
        contract=contract,
        base_snapshot_id=base_snapshot_id,
        snapshot_id=snapshot_id,
        captured_at=captured_at,
    )

    organization_links: dict[str, dict[str, Any]] = {}
    person_links: dict[str, dict[str, Any]] = {}
    assertions: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    meetings_out: list[dict[str, Any]] = []

    for meeting in snapshot.get("meetings", []):
        if not isinstance(meeting, Mapping):
            raise PartnerAdapterError("SEEGOV_MEETING_INVALID")
        meeting_id = str(meeting.get("meeting_id") or "").strip()
        org_external_id = str(meeting.get("organization_external_id") or "").strip()
        source_url = str(meeting.get("source_url") or "").strip()
        started_at = str(meeting.get("started_at") or "").strip()
        if not meeting_id or not org_external_id or not source_url or not started_at:
            raise PartnerAdapterError("SEEGOV_MEETING_REQUIRED_FIELDS")

        organization_links.setdefault(
            org_external_id,
            builder.link(
                entity_type="organization",
                external_id=org_external_id,
            ),
        )

        speakers_out: list[dict[str, Any]] = []
        for speaker in meeting.get("speakers", []):
            if not isinstance(speaker, Mapping):
                raise PartnerAdapterError("SEEGOV_SPEAKER_INVALID")
            person_external_id = str(speaker.get("person_external_id") or "").strip()
            display_name = str(speaker.get("display_name") or "").strip()
            if not person_external_id:
                raise PartnerAdapterError("SEEGOV_SPEAKER_EXTERNAL_ID_REQUIRED")

            person_links.setdefault(
                person_external_id,
                builder.link(
                    entity_type="person",
                    external_id=person_external_id,
                ),
            )

            observations = []
            for index, observation in enumerate(speaker.get("representation_observations", [])):
                if not isinstance(observation, Mapping):
                    raise PartnerAdapterError("SEEGOV_OBSERVATION_INVALID")
                observation_id = (
                    observation.get("observation_id")
                    or f"{meeting_id}:{person_external_id}:{index}"
                )
                assertion, hold = builder.observation(
                    observation_id=observation_id,
                    subject_type=observation.get("subject_type"),
                    field_path=observation.get("field_path"),
                    value=observation.get("value"),
                    asserted_at=observation.get("asserted_at") or captured_at,
                    evidence_locator=observation.get("evidence_locator") or source_url,
                    evidence_captured_at=observation.get("evidence_captured_at") or captured_at,
                    person_external_id=person_external_id,
                    organization_external_id=org_external_id,
                )
                if assertion is not None:
                    assertions.append(assertion)
                    observations.append(
                        {
                            "observation_id": str(observation_id),
                            "status": "PROPOSED_ASSERTION",
                            "assertion_id": assertion["assertion_id"],
                        }
                    )
                else:
                    assert hold is not None
                    held.append(hold)
                    observations.append(
                        {
                            "observation_id": str(observation_id),
                            "status": "HELD",
                            "reason": hold["reason"],
                        }
                    )

            speakers_out.append(
                {
                    "person_external_id": person_external_id,
                    "display_name": display_name or None,
                    "shared_identity_link": copy.deepcopy(person_links[person_external_id]),
                    "representation_observations": observations,
                }
            )

        meetings_out.append(
            {
                "meeting_id": meeting_id,
                "organization_external_id": org_external_id,
                "shared_organization_link": copy.deepcopy(
                    organization_links[org_external_id]
                ),
                "started_at": started_at,
                "source_url": source_url,
                "video_url": meeting.get("video_url"),
                "transcript_url": meeting.get("transcript_url"),
                "agenda_url": meeting.get("agenda_url"),
                "moments": copy.deepcopy(meeting.get("moments") or []),
                "vote_outcomes": copy.deepcopy(meeting.get("vote_outcomes") or []),
                "speakers": speakers_out,
            }
        )

    return {
        "adapter_version": "seegov-partner/0.1",
        "source_system": "seegov",
        "snapshot_id": snapshot_id,
        "captured_at": captured_at,
        "jurisdiction_ocdid": jurisdiction_ocdid,
        "organization_links": sorted(
            organization_links.values(),
            key=lambda row: str(row["external_id"]),
        ),
        "person_links": sorted(
            person_links.values(),
            key=lambda row: str(row["external_id"]),
        ),
        "product_objects": {
            "meetings": meetings_out,
        },
        "assertions": assertions,
        "held_observations": held,
        "canonical_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--identity-registry", type=Path, required=True)
    parser.add_argument("--base-snapshot-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    result = adapt_seegov_snapshot(
        json.loads(args.input.read_text(encoding="utf-8")),
        identity_registry=json.loads(
            args.identity_registry.read_text(encoding="utf-8")
        ),
        contract=json.loads(args.contract.read_text(encoding="utf-8")),
        base_snapshot_id=args.base_snapshot_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
