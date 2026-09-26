#!/usr/bin/env python3
"""Common read-only partner observation → governed assertion adapter helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from adapters.shared_identity import (
    SharedIdentityResolutionError,
    SharedIdentityResolver,
)
from tools.assertion_governance import validate_assertion

PARTNER_NAMESPACE = uuid5(
    NAMESPACE_URL, "https://civicdata.tech/partner-assertion-adapters/v0.1"
)


class PartnerAdapterError(ValueError):
    """Fail-closed partner adapter violation."""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _stable_id(prefix: str, *parts: Any) -> str:
    token = "|".join(_clean(part) for part in parts)
    return f"{prefix}-{uuid5(PARTNER_NAMESPACE, token)}"


@dataclass(frozen=True)
class ContractTarget:
    subject_type: str
    subject_id: str


def _external_identifier(row: Mapping[str, Any], scheme: str) -> str | None:
    for identifier in row.get("identifiers") or []:
        if (
            isinstance(identifier, Mapping)
            and identifier.get("scheme") == scheme
            and identifier.get("id") not in (None, "")
        ):
            return str(identifier["id"])
    return None


class ContractIdentityIndex:
    """Index Contract v1 by reviewed shared Organization/Person identity."""

    def __init__(self, contract: Mapping[str, Any]):
        if not isinstance(contract, Mapping):
            raise PartnerAdapterError("CONTRACT_INVALID")
        self.contract = contract
        self.organizations_by_shared: dict[str, list[Mapping[str, Any]]] = {}
        self.people_by_shared: dict[str, list[Mapping[str, Any]]] = {}
        self.memberships = [
            row
            for row in contract.get("memberships", [])
            if isinstance(row, Mapping)
        ]
        self.posts = {
            str(row["id"]): row
            for row in contract.get("posts", [])
            if isinstance(row, Mapping) and row.get("id")
        }

        for row in contract.get("organizations", []):
            if not isinstance(row, Mapping):
                continue
            shared = row.get("shared_identity_id")
            if shared:
                self.organizations_by_shared.setdefault(str(shared), []).append(row)

        for row in contract.get("people", []):
            if not isinstance(row, Mapping):
                continue
            shared = row.get("shared_identity_id")
            if shared:
                self.people_by_shared.setdefault(str(shared), []).append(row)

    @staticmethod
    def _unique(
        rows: list[Mapping[str, Any]],
        *,
        missing: str,
        ambiguous: str,
    ) -> Mapping[str, Any]:
        if not rows:
            raise PartnerAdapterError(missing)
        if len(rows) != 1:
            raise PartnerAdapterError(ambiguous)
        return rows[0]

    def organization(self, shared_identity_id: str) -> Mapping[str, Any]:
        return self._unique(
            self.organizations_by_shared.get(shared_identity_id, []),
            missing="ORGANIZATION_SHARED_ID_OUT_OF_SCOPE",
            ambiguous="ORGANIZATION_SHARED_ID_AMBIGUOUS",
        )

    def person(self, shared_identity_id: str) -> Mapping[str, Any]:
        return self._unique(
            self.people_by_shared.get(shared_identity_id, []),
            missing="PERSON_SHARED_ID_OUT_OF_SCOPE",
            ambiguous="PERSON_SHARED_ID_AMBIGUOUS",
        )

    def membership(
        self,
        *,
        person_shared_identity_id: str,
        organization_shared_identity_id: str,
    ) -> Mapping[str, Any]:
        person = self.person(person_shared_identity_id)
        organization = self.organization(organization_shared_identity_id)
        matches = [
            row
            for row in self.memberships
            if str(row.get("person_id")) == str(person.get("id"))
            and str(row.get("organization_id")) == str(organization.get("id"))
            and row.get("closed_at") is None
        ]
        return self._unique(
            matches,
            missing="OPEN_MEMBERSHIP_NOT_FOUND",
            ambiguous="OPEN_MEMBERSHIP_AMBIGUOUS",
        )

    def target(
        self,
        *,
        subject_type: str,
        person_shared_identity_id: str | None = None,
        organization_shared_identity_id: str | None = None,
    ) -> ContractTarget:
        subject = _clean(subject_type).lower()
        if subject == "person":
            if not person_shared_identity_id:
                raise PartnerAdapterError("PERSON_SHARED_ID_REQUIRED")
            row = self.person(person_shared_identity_id)
            canonical_id = _external_identifier(
                row, "civicdata_factory_person"
            )
            if canonical_id is None:
                raise PartnerAdapterError("CANONICAL_SUBJECT_ID_UNAVAILABLE")
            return ContractTarget("person", canonical_id)
        if subject == "organization":
            if not organization_shared_identity_id:
                raise PartnerAdapterError("ORGANIZATION_SHARED_ID_REQUIRED")
            row = self.organization(organization_shared_identity_id)
            canonical_id = _external_identifier(
                row, "civicdata_factory_body"
            )
            if canonical_id is None:
                raise PartnerAdapterError("CANONICAL_SUBJECT_ID_UNAVAILABLE")
            return ContractTarget("organization", canonical_id)
        if subject in {"membership", "post"}:
            if not person_shared_identity_id or not organization_shared_identity_id:
                raise PartnerAdapterError("PERSON_AND_ORGANIZATION_SHARED_IDS_REQUIRED")
            membership = self.membership(
                person_shared_identity_id=person_shared_identity_id,
                organization_shared_identity_id=organization_shared_identity_id,
            )
            if subject == "membership":
                canonical_id = _external_identifier(
                    membership, "civicdata_factory_role_term"
                )
                if canonical_id is None:
                    raise PartnerAdapterError("CANONICAL_SUBJECT_ID_UNAVAILABLE")
                return ContractTarget("membership", canonical_id)
            post_id = str(membership.get("post_id") or "")
            if not post_id or post_id not in self.posts:
                raise PartnerAdapterError("MEMBERSHIP_POST_NOT_FOUND")
            canonical_id = _external_identifier(
                self.posts[post_id], "civicdata_factory_office"
            )
            if canonical_id is None:
                raise PartnerAdapterError("CANONICAL_SUBJECT_ID_UNAVAILABLE")
            return ContractTarget("post", canonical_id)
        raise PartnerAdapterError("PARTNER_SUBJECT_TYPE_UNSUPPORTED")


class PartnerAssertionBuilder:
    """Resolve reviewed partner IDs and emit proposed assertions or held observations."""

    def __init__(
        self,
        *,
        source_system: str,
        identity_registry: Mapping[str, Any],
        contract: Mapping[str, Any],
        base_snapshot_id: str,
        snapshot_id: str,
        captured_at: str,
    ):
        self.source_system = _clean(source_system).lower()
        self.base_snapshot_id = _clean(base_snapshot_id)
        self.snapshot_id = _clean(snapshot_id)
        self.captured_at = _clean(captured_at)
        if not all(
            (
                self.source_system,
                self.base_snapshot_id,
                self.snapshot_id,
                self.captured_at,
            )
        ):
            raise PartnerAdapterError("PARTNER_BATCH_METADATA_REQUIRED")
        try:
            self.resolver = SharedIdentityResolver(identity_registry)
        except SharedIdentityResolutionError as exc:
            raise PartnerAdapterError(str(exc)) from exc
        if not self.resolver.enabled:
            raise PartnerAdapterError("IDENTITY_REGISTRY_REQUIRED")
        self.contract_index = ContractIdentityIndex(contract)

    def resolve_identity(
        self,
        *,
        entity_type: str,
        external_id: Any,
    ) -> str | None:
        external = _clean(external_id)
        if not external:
            return None
        try:
            return self.resolver.resolve(
                entity_type=entity_type,
                system=self.source_system,
                external_id=external,
            )
        except SharedIdentityResolutionError as exc:
            raise PartnerAdapterError(str(exc)) from exc

    def link(
        self,
        *,
        entity_type: str,
        external_id: Any,
    ) -> dict[str, Any]:
        external = _clean(external_id)
        shared = self.resolve_identity(
            entity_type=entity_type,
            external_id=external,
        )
        if shared is None:
            return {
                "external_id": external,
                "shared_identity_id": None,
                "status": "UNRESOLVED_REGISTRY",
            }
        try:
            if entity_type == "person":
                row = self.contract_index.person(shared)
            elif entity_type == "organization":
                row = self.contract_index.organization(shared)
            else:
                raise PartnerAdapterError("PARTNER_ENTITY_TYPE_UNSUPPORTED")
        except PartnerAdapterError as exc:
            return {
                "external_id": external,
                "shared_identity_id": shared,
                "status": "OUT_OF_SCOPE",
                "reason": str(exc),
            }
        return {
            "external_id": external,
            "shared_identity_id": shared,
            "contract_id": str(row["id"]),
            "status": "RESOLVED",
        }

    def observation(
        self,
        *,
        observation_id: Any,
        subject_type: Any,
        field_path: Any,
        value: Any,
        asserted_at: Any,
        evidence_locator: Any,
        evidence_captured_at: Any = None,
        person_external_id: Any = None,
        organization_external_id: Any = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        observation_key = _clean(observation_id)
        subject = _clean(subject_type).lower()
        field = _clean(field_path)
        asserted = _clean(asserted_at)
        locator = _clean(evidence_locator)
        evidence_time = _clean(evidence_captured_at) or self.captured_at
        if not all((observation_key, subject, field, asserted, locator, evidence_time)):
            raise PartnerAdapterError("PARTNER_OBSERVATION_REQUIRED_FIELDS")

        person_shared = self.resolve_identity(
            entity_type="person",
            external_id=person_external_id,
        ) if _clean(person_external_id) else None
        organization_shared = self.resolve_identity(
            entity_type="organization",
            external_id=organization_external_id,
        ) if _clean(organization_external_id) else None

        unresolved: list[str] = []
        if _clean(person_external_id) and person_shared is None:
            unresolved.append("PERSON_IDENTITY_UNRESOLVED")
        if _clean(organization_external_id) and organization_shared is None:
            unresolved.append("ORGANIZATION_IDENTITY_UNRESOLVED")
        if unresolved:
            return None, {
                "observation_id": observation_key,
                "status": "identity_conflict",
                "reason": ",".join(unresolved),
                "person_external_id": _clean(person_external_id) or None,
                "organization_external_id": _clean(organization_external_id) or None,
                "field_path": field,
                "value": value,
                "evidence_locator": locator,
            }

        try:
            target = self.contract_index.target(
                subject_type=subject,
                person_shared_identity_id=person_shared,
                organization_shared_identity_id=organization_shared,
            )
        except PartnerAdapterError as exc:
            reason = str(exc)
            held_status = (
                "identity_conflict"
                if "SHARED_ID" in reason or "MEMBERSHIP" in reason
                else "scope_conflict"
            )
            return None, {
                "observation_id": observation_key,
                "status": held_status,
                "reason": reason,
                "person_shared_identity_id": person_shared,
                "organization_shared_identity_id": organization_shared,
                "field_path": field,
                "value": value,
                "evidence_locator": locator,
            }

        evidence_id = _stable_id(
            f"evidence-{self.source_system}",
            self.snapshot_id,
            observation_key,
            locator,
        )
        assertion = {
            "assertion_id": _stable_id(
                f"assertion-{self.source_system}",
                self.snapshot_id,
                observation_key,
                target.subject_type,
                target.subject_id,
                field,
            ),
            "source_system": self.source_system,
            "subject_type": target.subject_type,
            "subject_id": target.subject_id,
            "field_path": field,
            "value": value,
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "locator": locator,
                    "captured_at": evidence_time,
                }
            ],
            "asserted_at": asserted,
            "base_snapshot_id": self.base_snapshot_id,
            "review_status": "proposed",
            "review_history": [],
        }
        errors = validate_assertion(assertion)
        if errors:
            raise PartnerAdapterError(
                "PARTNER_ASSERTION_INVALID:" + ",".join(errors)
            )
        return assertion, None
