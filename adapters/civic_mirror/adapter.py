#!/usr/bin/env python3
"""Civic Mirror → shared civic spine read-only adapter.

Evidence, bills, events, and editorial tags remain Civic Mirror-owned. Only
explicit representation observations are translated into governed assertions.
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


def adapt_civic_mirror_snapshot(
    snapshot: Mapping[str, Any],
    *,
    identity_registry: Mapping[str, Any],
    contract: Mapping[str, Any],
    base_snapshot_id: str,
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise PartnerAdapterError("CIVIC_MIRROR_SNAPSHOT_INVALID")
    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    captured_at = str(snapshot.get("captured_at") or "").strip()
    jurisdiction_ocdid = str(snapshot.get("jurisdiction_ocdid") or "").strip()
    if not snapshot_id or not captured_at or not jurisdiction_ocdid.startswith("ocd-jurisdiction/"):
        raise PartnerAdapterError("CIVIC_MIRROR_SNAPSHOT_METADATA_INVALID")

    builder = PartnerAssertionBuilder(
        source_system="civic_mirror",
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
    evidence_out: list[dict[str, Any]] = []

    for item in snapshot.get("evidence", []):
        if not isinstance(item, Mapping):
            raise PartnerAdapterError("CIVIC_MIRROR_EVIDENCE_INVALID")
        evidence_external_id = str(item.get("evidence_external_id") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        if not evidence_external_id or not source_url:
            raise PartnerAdapterError("CIVIC_MIRROR_EVIDENCE_REQUIRED_FIELDS")

        person_external_id = str(item.get("person_external_id") or "").strip()
        organization_external_id = str(
            item.get("organization_external_id") or ""
        ).strip()

        if person_external_id:
            person_links.setdefault(
                person_external_id,
                builder.link(
                    entity_type="person",
                    external_id=person_external_id,
                ),
            )
        if organization_external_id:
            organization_links.setdefault(
                organization_external_id,
                builder.link(
                    entity_type="organization",
                    external_id=organization_external_id,
                ),
            )

        observations_out: list[dict[str, Any]] = []
        for index, observation in enumerate(
            item.get("representation_observations", [])
        ):
            if not isinstance(observation, Mapping):
                raise PartnerAdapterError("CIVIC_MIRROR_OBSERVATION_INVALID")
            observation_id = (
                observation.get("observation_id")
                or f"{evidence_external_id}:{index}"
            )
            assertion, hold = builder.observation(
                observation_id=observation_id,
                subject_type=observation.get("subject_type"),
                field_path=observation.get("field_path"),
                value=observation.get("value"),
                asserted_at=observation.get("asserted_at") or captured_at,
                evidence_locator=observation.get("evidence_locator") or source_url,
                evidence_captured_at=(
                    observation.get("evidence_captured_at")
                    or item.get("captured_at")
                    or captured_at
                ),
                person_external_id=person_external_id or None,
                organization_external_id=organization_external_id or None,
            )
            if assertion is not None:
                assertions.append(assertion)
                observations_out.append(
                    {
                        "observation_id": str(observation_id),
                        "status": "PROPOSED_ASSERTION",
                        "assertion_id": assertion["assertion_id"],
                    }
                )
            else:
                assert hold is not None
                held.append(hold)
                observations_out.append(
                    {
                        "observation_id": str(observation_id),
                        "status": "HELD",
                        "reason": hold["reason"],
                    }
                )

        evidence_out.append(
            {
                "evidence_external_id": evidence_external_id,
                "source_url": source_url,
                "captured_at": item.get("captured_at") or captured_at,
                "title": item.get("title"),
                "editorial_tag": item.get("editorial_tag"),
                "kind": item.get("kind"),
                "person_external_id": person_external_id or None,
                "organization_external_id": organization_external_id or None,
                "shared_person_link": (
                    copy.deepcopy(person_links[person_external_id])
                    if person_external_id
                    else None
                ),
                "shared_organization_link": (
                    copy.deepcopy(organization_links[organization_external_id])
                    if organization_external_id
                    else None
                ),
                "representation_observations": observations_out,
            }
        )

    return {
        "adapter_version": "civic-mirror-partner/0.1",
        "source_system": "civic_mirror",
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
            "evidence": evidence_out,
            "bills": copy.deepcopy(snapshot.get("bills") or []),
            "events": copy.deepcopy(snapshot.get("events") or []),
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

    result = adapt_civic_mirror_snapshot(
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
