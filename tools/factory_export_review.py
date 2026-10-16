"""Prepare draft Factory exports and apply separately approved, hash-bound reviews.

A bounded evidence/title review cannot certify an entire runtime contract. These
helpers do not publish, mutate source packages or change the legacy exporter.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.contract_v1 import validate_contract
from tools.assertion_governance import certify_snapshot
from tools.jurisdiction_package_strict import validate

GATES = ('raw_complete', 'normalized_complete', 'qa_passed', 'parity_ok')


class ExportReviewError(ValueError):
    pass


def fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode() + b'\n'
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ExportReviewError(code)


def _timestamp(value: Any) -> bool:
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        return False


def prepare_review(package: Mapping[str, Any], prior_contract: Mapping[str, Any], *, generated_at: str) -> dict:
    """Preserve prior assertion metadata; new assertions acquire no review date."""
    _require(_timestamp(generated_at), 'GENERATION_TIMESTAMP_INVALID')
    _require(not validate(package), 'SOURCE_PACKAGE_INVALID')
    _require(not validate_contract(prior_contract, require_certified=False), 'PRIOR_CONTRACT_INVALID')
    draft = export_factory_package(package, generated_at=generated_at, governed_package=True)
    _require(draft['jurisdiction'] == prior_contract['jurisdiction'], 'PRIOR_JURISDICTION_MISMATCH')
    inherited = deepcopy(draft['certification'])
    draft['certification']['status'] = 'draft'
    # The inherited verification time describes the old source gates, not this review.
    draft['certification']['verified_at'] = None
    prior = {row['id']: row for row in prior_contract['assertions']}
    for row in draft['assertions']:
        old = prior.get(row['id'])
        if old:
            current = {k: v for k, v in row.items() if k not in ('asserted_at', 'reviewed_at')}
            previous = {k: v for k, v in old.items() if k not in ('asserted_at', 'reviewed_at')}
            _require(current == previous, 'EXISTING_ASSERTION_CHANGED_REVIEW_REQUIRED')
            row['asserted_at'] = old.get('asserted_at')
            row['reviewed_at'] = old.get('reviewed_at')
        else:
            # Export generation is neither the original assertion nor its review.
            row['asserted_at'] = None
            row['reviewed_at'] = None
    _require(not validate_contract(draft, require_certified=False), 'DRAFT_CONTRACT_INVALID')
    return {
        'status': 'DRAFT_REVIEW_REQUIRED',
        'source_sha256': fingerprint(package),
        'prior_contract_sha256': fingerprint(prior_contract),
        'draft_sha256': fingerprint(draft),
        'inherited_certification': inherited,
        'contract': draft,
    }


def apply_certification(review: Mapping[str, Any], decision: Mapping[str, Any], *, source_package: Mapping[str, Any], history: list | None = None) -> dict:
    """Apply explicit full-contract approval. Callers retain the returned audit sidecar.

    Authority is supplied by the trusted review caller, not authenticated here.
    Approval of one source observation must use a different scope and is rejected.
    No certification decision is inferred from historical gates or a source merge.
    """
    _require(not validate(source_package), 'SOURCE_PACKAGE_INVALID')
    _require(review.get('source_sha256') == fingerprint(source_package), 'SOURCE_FINGERPRINT_MISMATCH')
    draft = review.get('contract')
    _require(isinstance(draft, Mapping), 'DRAFT_MISSING')
    _require(review.get('status') == 'DRAFT_REVIEW_REQUIRED', 'REVIEW_STATUS_INVALID')
    _require(review.get('draft_sha256') == fingerprint(draft), 'DRAFT_FINGERPRINT_MISMATCH')
    _require(draft.get('certification', {}).get('status') == 'draft', 'DRAFT_STATUS_REQUIRED')
    _require(not validate_contract(draft, require_certified=False), 'DRAFT_CONTRACT_INVALID')
    _require(decision.get('scope') == 'FULL_RUNTIME_CONTRACT', 'FULL_CONTRACT_REVIEW_REQUIRED')
    _require(decision.get('approved') is True, 'EXPLICIT_CERTIFICATION_APPROVAL_REQUIRED')
    for key in ('source_sha256', 'prior_contract_sha256', 'draft_sha256'):
        _require(isinstance(review.get(key), str) and len(review[key]) == 64 and decision.get(key) == review[key], 'DECISION_FINGERPRINT_MISMATCH')
    _require(decision.get('reviewer_authority') == 'civicdata_certification', 'CERTIFICATION_AUTHORITY_MISMATCH')
    _require(isinstance(decision.get('reviewer'), str) and bool(decision['reviewer'].strip()), 'REVIEWER_REQUIRED')
    _require(isinstance(decision.get('reason'), str) and bool(decision['reason'].strip()), 'REVIEW_REASON_REQUIRED')
    _require(_timestamp(decision.get('verified_at')), 'REVIEW_TIMESTAMP_INVALID')
    _require(isinstance(decision.get('gates'), Mapping) and set(decision['gates']) == set(GATES), 'CERTIFICATION_GATES_INVALID')
    _require(all(decision['gates'][gate] is True for gate in GATES), 'CERTIFICATION_GATES_INCOMPLETE')
    _require(isinstance(decision.get('evidence_refs'), list) and bool(decision['evidence_refs']) and all(isinstance(v, str) and v.strip() for v in decision['evidence_refs']), 'GATE_EVIDENCE_REQUIRED')
    _require(history is None or isinstance(history, list), 'HISTORY_INVALID')
    # Reuse the existing shared authority/gate implementation, keeping its history
    # outside the runtime payload so the runtime schema stays unchanged.
    result = certify_snapshot(draft, **decision['gates'], verified_at=decision['verified_at'], reviewer=decision['reviewer'], reviewer_authority=decision['reviewer_authority'], reason=decision['reason'])
    result.pop('certification_history', None)
    _require(not validate_contract(result), 'CERTIFIED_CONTRACT_INVALID')
    audit = deepcopy(history or [])
    audit.append({
        'source_sha256': review['source_sha256'],
        'prior_contract_sha256': review['prior_contract_sha256'],
        'draft_sha256': review['draft_sha256'],
        'certified_contract_sha256': fingerprint(result),
        'decision': deepcopy(dict(decision)),
        'runtime_publication_granted': False,
        'activation_granted': False,
    })
    return {'contract': result, 'certification_history': audit, 'runtime_publication_granted': False, 'activation_granted': False}
