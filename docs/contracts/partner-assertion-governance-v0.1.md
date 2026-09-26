# Partner Assertion Review and Certification Authority v0.1

Status: **Draft contract implementation for issue #75**

This contract defines how observations from Civic Mirror, SeeGov, Empowered Vote,
CivicPatch, the Jurisdiction Factory, or another partner enter the shared
representation layer without direct overwrite.

## Core rule

```text
partner observation
      ↓
PROPOSED assertion + evidence + base snapshot
      ↓
governed review
      ↓
ACCEPTED | REJECTED | NEEDS_EVIDENCE | IDENTITY_CONFLICT | SCOPE_CONFLICT
      ↓
accepted assertion may be promoted to a NEW snapshot
      ↓
new snapshot becomes UNCERTIFIED
      ↓
RAW → normalized → QA → Parity_OK
      ↓
CERTIFIED
```

There is no last-write-wins adapter.

## v0.1 authority matrix

The shared contract uses authority domains rather than individual names:

| Subject domain | Authority required to decide assertion |
|---|---|
| `jurisdiction` | `openstates_jurisdictions` |
| `division` | `openstates_jurisdictions` |
| `organization` | `civicdata_representation` |
| `post` | `civicdata_representation` |
| `person` | `civicdata_representation` |
| `membership` | `civicdata_representation` |
| `certification` | `civicdata_certification` |

Meaning:

- OpenStates/OCDID remains the canonical shared authority for jurisdiction/division identity.
- `civicdata_representation` is the shared representation review authority implemented in this repository for organization/post/person/membership promotion.
- `civicdata_certification` is the authority that may mark a shared snapshot certified after all gates pass.
- Product-native databases retain their own write ownership. This matrix governs only the shared representation contract.

A partner may submit evidence in any domain; submission does not imply acceptance authority.

## Assertion envelope

Required fields:

```text
assertion_id
source_system
subject_type
subject_id
field_path
value
evidence[]
asserted_at
base_snapshot_id
review_status
review_history[]
```

### Evidence

At least one evidence reference is required:

```json
{
  "evidence_id": "ev-civic-mirror-001",
  "locator": "https://...",
  "captured_at": "2026-09-25T23:00:00-06:00"
}
```

### Base snapshot

`base_snapshot_id` identifies the snapshot against which the assertion was made.
Promotion fails if that snapshot is no longer the current base. A reviewer must
reconcile stale assertions rather than silently applying them to newer state.

## Review states

### proposed

Default state. No canonical effect.

### accepted

Evidence and scope are sufficient, the reviewer holds the correct authority, and
the assertion may be promoted.

Acceptance still does **not** mutate the base snapshot.

### rejected

Assertion is not accepted. The assertion and review event remain in history.

### needs_evidence

The claim may be plausible but lacks sufficient evidence. It cannot be promoted.

### identity_conflict

The subject identity is unresolved or conflicts with the shared identity registry.
It remains fail-closed until identity resolution occurs.

### scope_conflict

The observation refers outside the governed subject/snapshot scope or cannot be
safely mapped into it.

## Promotion

Promotion is copy-on-write:

1. the accepted assertion is validated;
2. `base_snapshot_id` must equal the current snapshot;
3. the subject must resolve exactly once;
4. protected identity fields cannot be rewritten through this path;
5. a new snapshot ID is created;
6. the accepted value is applied;
7. a promotion-history event is appended;
8. certification is reset to `uncertified`.

The prior snapshot is never rewritten.

### Protected identity fields

The assertion path may not directly rewrite identifiers such as:

- `jurisdiction_id`
- `division_id`
- `organization_id`
- `post_id`
- `person_id`
- `membership_id`
- `role_id`
- `jurisdiction_ocdid`
- `division_ocdid`
- `canonical_id`

Identity/geography corrections use the identity registry and OCDID validation
contracts instead.

## Certification

After canonical state changes, certification must be re-established.

Shared certification gates are:

```text
raw_complete
normalized_complete
qa_passed
parity_ok
```

A snapshot may be marked `certified` only when all four are explicitly true and
the reviewer authority is `civicdata_certification`.

### Tracker synchronization

`tracker_synced` is intentionally outside shared certification.

The Factory may still require:

```text
tracker_synced = true
```

before its own operational `COMPLETE` state, but a public semantic certification
does not depend on the project tracker.

## End-date correction example

A Civic Mirror observation says a known membership ended on September 1, 2026.

1. Civic Mirror submits an assertion against `membership.end_date`.
2. The assertion is `proposed`.
3. `civicdata_representation` reviews and accepts it.
4. Promotion produces a new snapshot; the previous certified snapshot remains historical.
5. The new snapshot is `uncertified`.
6. Evidence/normalization/QA/parity are rerun.
7. `civicdata_certification` may certify the new snapshot when all gates pass.

At no point can the partner directly overwrite the certified record.

## Rejected/conflicted assertions

Rejected, needs-evidence, identity-conflict, and scope-conflict assertions remain
in the assertion ledger. They cannot be promoted.

New evidence should normally create a new assertion rather than deleting or
rewriting the prior reviewed assertion.

## Reference implementation

Schema:

```text
schemas/partner_assertion_v0.1.schema.json
```

Review/promotion helper:

```text
tools/assertion_governance.py
```

Acceptance fixture:

```text
acceptance/representation/partner_assertion_v0.1.json
```

Regression tests:

```text
tests/test_assertion_governance.py
```

## Boundary

This contract governs shared representation assertions only. It does not grant
write authority inside CivicPatch, Civic Mirror, SeeGov, Empowered Vote, or
OpenStates. It does not infer missing evidence, identity, term dates, or scope.
