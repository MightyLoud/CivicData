#!/usr/bin/env python3
"""Apply explicit reviewed CivicPatch identity reconciliation to a candidate bundle."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from consumers.civicpatch.adapter import (
    CivicPatchAdapterError,
    round_trip_semantic_projection,
    validate_civicpatch_officials,
)


class CivicPatchReconciliationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def validate_reconciliation_plan(
    plan: Mapping[str, Any],
    *,
    current_officials: Sequence[Mapping[str, Any]],
    candidate_bundle: Mapping[str, Any],
) -> list[str]:
    errors: set[str] = set()
    if not isinstance(plan, Mapping):
        return ["PLAN_INVALID"]

    required = {
        "contract_version",
        "jurisdiction_ocdid",
        "target",
        "reviewed_at",
        "reviewer",
        "evidence",
        "accepted_crosswalks",
        "additions",
        "omissions",
        "constraints",
    }
    if set(plan) != required:
        errors.add("PLAN_FIELDS_INVALID")
    if plan.get("contract_version") != "0.1":
        errors.add("PLAN_VERSION_INVALID")
    if not _clean(plan.get("reviewer")) or not _clean(plan.get("reviewed_at")):
        errors.add("PLAN_REVIEW_REQUIRED")

    target = plan.get("target")
    if not isinstance(target, Mapping):
        errors.add("TARGET_INVALID")
    elif not all(_clean(target.get(k)) for k in ("repository", "commit", "path")):
        errors.add("TARGET_INVALID")

    evidence = plan.get("evidence")
    evidence_ids: set[str] = set()
    if not isinstance(evidence, list) or not evidence:
        errors.add("EVIDENCE_REQUIRED")
    else:
        for row in evidence:
            if not isinstance(row, Mapping):
                errors.add("EVIDENCE_INVALID")
                continue
            evidence_id = _clean(row.get("evidence_id"))
            if not evidence_id or evidence_id in evidence_ids:
                errors.add("EVIDENCE_ID_INVALID")
            evidence_ids.add(evidence_id)
            if not _clean(row.get("authority")) or not _clean(row.get("url")) or not _clean(row.get("supports")):
                errors.add("EVIDENCE_INVALID")

    officials = candidate_bundle.get("officials")
    receipt = candidate_bundle.get("receipt")
    if not isinstance(officials, list) or not isinstance(receipt, Mapping):
        errors.add("CANDIDATE_BUNDLE_INVALID")
        return sorted(errors)

    person_xwalks = receipt.get("person_crosswalks")
    if not isinstance(person_xwalks, list):
        errors.add("CANDIDATE_CROSSWALKS_INVALID")
        return sorted(errors)
    candidate_by_core = {
        row.get("core_person_id"): row.get("candidate_civicpatch_id")
        for row in person_xwalks
        if isinstance(row, Mapping)
    }
    current_ids = {
        row.get("id") for row in current_officials
        if isinstance(row, Mapping) and row.get("id")
    }

    accepted = plan.get("accepted_crosswalks")
    additions = plan.get("additions")
    omissions = plan.get("omissions")
    if not isinstance(accepted, list) or not isinstance(additions, list) or not isinstance(omissions, list):
        errors.add("PLAN_ACTIONS_INVALID")
        return sorted(errors)

    accepted_core: set[str] = set()
    accepted_current: set[str] = set()
    for row in accepted:
        if not isinstance(row, Mapping):
            errors.add("ACCEPTED_CROSSWALK_INVALID")
            continue
        core_id = row.get("core_person_id")
        civicpatch_id = row.get("civicpatch_id")
        if core_id not in candidate_by_core:
            errors.add("ACCEPTED_CORE_PERSON_UNKNOWN")
        if civicpatch_id not in current_ids:
            errors.add("ACCEPTED_CIVICPATCH_ID_UNKNOWN")
        if core_id in accepted_core or civicpatch_id in accepted_current:
            errors.add("ACCEPTED_CROSSWALK_DUPLICATE")
        accepted_core.add(core_id)
        accepted_current.add(civicpatch_id)
        if row.get("review_status") != "ACCEPTED_FOR_PARTNER_PATCH":
            errors.add("ACCEPTED_REVIEW_STATUS_INVALID")
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or len(refs) < 2 or any(ref not in evidence_ids for ref in refs):
            errors.add("ACCEPTED_EVIDENCE_INVALID")
        if not _clean(row.get("rationale")) or not _clean(row.get("name")):
            errors.add("ACCEPTED_REVIEW_REQUIRED")

    addition_core: set[str] = set()
    for row in additions:
        if not isinstance(row, Mapping):
            errors.add("ADDITION_INVALID")
            continue
        core_id = row.get("core_person_id")
        if core_id not in candidate_by_core or core_id in accepted_core or core_id in addition_core:
            errors.add("ADDITION_CORE_PERSON_INVALID")
        addition_core.add(core_id)
        if row.get("status") != "NEW_PREVIEW_ID_PENDING_PARTNER_ACCEPTANCE":
            errors.add("ADDITION_STATUS_INVALID")
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or any(ref not in evidence_ids for ref in refs):
            errors.add("ADDITION_EVIDENCE_INVALID")

    omission_ids: set[str] = set()
    for row in omissions:
        if not isinstance(row, Mapping):
            errors.add("OMISSION_INVALID")
            continue
        civicpatch_id = row.get("civicpatch_id")
        if civicpatch_id not in current_ids or civicpatch_id in accepted_current or civicpatch_id in omission_ids:
            errors.add("OMISSION_CIVICPATCH_ID_INVALID")
        omission_ids.add(civicpatch_id)
        if row.get("status") != "STALE_ROSTER_OMISSION_NOT_IDENTITY_DELETE":
            errors.add("OMISSION_STATUS_INVALID")
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or any(ref not in evidence_ids for ref in refs):
            errors.add("OMISSION_EVIDENCE_INVALID")

    if set(candidate_by_core) != accepted_core | addition_core:
        errors.add("CANDIDATE_COVERAGE_INCOMPLETE")
    if current_ids != accepted_current | omission_ids:
        errors.add("CURRENT_COVERAGE_INCOMPLETE")

    constraints = plan.get("constraints")
    required_constraints = {
        "exact_name_matching_is_not_identity_authority": True,
        "upstream_write_authorized": False,
        "omitted_rows_are_identity_deletions": False,
        "preview_addition_ids_are_accepted_partner_ids": False,
    }
    if constraints != required_constraints:
        errors.add("CONSTRAINTS_INVALID")

    return sorted(errors)


def apply_reconciliation(
    candidate_bundle: Mapping[str, Any],
    current_officials: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    errors = validate_reconciliation_plan(
        plan,
        current_officials=current_officials,
        candidate_bundle=candidate_bundle,
    )
    if errors:
        raise CivicPatchReconciliationError("PLAN_INVALID:" + ",".join(errors))

    result = deepcopy(dict(candidate_bundle))
    officials = result["officials"]
    receipt = result["receipt"]
    people = receipt["person_crosswalks"]
    memberships = receipt["membership_crosswalks"]

    official_by_id = {row["id"]: row for row in officials}
    person_receipt_by_core = {row["core_person_id"]: row for row in people}

    actions: list[dict[str, Any]] = []
    for accepted in plan["accepted_crosswalks"]:
        core_id = accepted["core_person_id"]
        person_receipt = person_receipt_by_core[core_id]
        preview_id = person_receipt["candidate_civicpatch_id"]
        existing_id = accepted["civicpatch_id"]
        official = official_by_id.pop(preview_id)
        official["id"] = existing_id
        official_by_id[existing_id] = official

        person_receipt["candidate_civicpatch_id"] = existing_id
        person_receipt["preview_civicpatch_id"] = preview_id
        person_receipt["status"] = "REVIEWED_EXISTING_CIVICPATCH_ID_FOR_PARTNER_PATCH"
        person_receipt["review_evidence_ids"] = list(accepted["evidence_ids"])

        for membership in memberships:
            if membership["core_person_id"] == core_id:
                membership["candidate_official_id"] = existing_id

        actions.append(
            {
                "action": accepted["patch_action"],
                "core_person_id": core_id,
                "civicpatch_id": existing_id,
                "name": accepted["name"],
            }
        )

    additions = {row["core_person_id"]: row for row in plan["additions"]}
    for person_receipt in people:
        core_id = person_receipt["core_person_id"]
        if core_id in additions:
            person_receipt["status"] = "NEW_PREVIEW_ID_PENDING_PARTNER_ACCEPTANCE"
            person_receipt["review_evidence_ids"] = list(additions[core_id]["evidence_ids"])
            actions.append(
                {
                    "action": "ADD_PREVIEW_ID_PENDING_PARTNER_ACCEPTANCE",
                    "core_person_id": core_id,
                    "civicpatch_id": person_receipt["candidate_civicpatch_id"],
                    "name": additions[core_id]["name"],
                }
            )

    for omission in plan["omissions"]:
        actions.append(
            {
                "action": "OMIT_STALE_ROSTER_ROW_NOT_IDENTITY_DELETE",
                "core_person_id": None,
                "civicpatch_id": omission["civicpatch_id"],
                "name": omission["name"],
            }
        )

    result["officials"] = sorted(official_by_id.values(), key=lambda row: row["name"])
    result["reconciliation"] = {
        "plan_version": plan["contract_version"],
        "reviewed_at": plan["reviewed_at"],
        "reviewer": plan["reviewer"],
        "target": deepcopy(plan["target"]),
        "evidence": deepcopy(plan["evidence"]),
        "actions": sorted(actions, key=lambda row: (row["action"], row["name"])),
        "upstream_write_authorized": False,
    }

    official_errors = validate_civicpatch_officials(result["officials"])
    if official_errors:
        raise CivicPatchReconciliationError(
            "PATCH_OUTPUT_INVALID:" + ",".join(official_errors)
        )
    # The sidecar receipt must still make the candidate lossless for the
    # canonical representation facts after retained partner IDs are substituted.
    round_trip_semantic_projection(result)
    return result
