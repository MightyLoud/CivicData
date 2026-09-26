# Canonical Representation Core v0.1

Status: **Issue #1 closeout candidate**

This document is the single core schema map for jurisdiction, office/post,
officeholder/membership, geography, provenance, QA, review, and certification.

It consolidates the model already implemented by the Jurisdiction Package and
the interoperability contracts without replacing those artifacts.

## Canonical graph

```text
Division
   |
   v
Jurisdiction
   |
   v
Organization
   |
   +--> Role
   |      |
   |      v
   +----> Post ----> Division
              |
              v
          Membership <---- Person

Evidence --> Assertion --> canonical entity

Review / QA / Parity
          |
          v
    Certification
```

## Primary keys

| Entity | Primary key |
|---|---|
| Snapshot | `snapshot_id` |
| Jurisdiction | `jurisdiction_ocdid` |
| Division | `division_ocdid` |
| Organization | `organization_id` |
| Role | `role_id` |
| Post / Office | `post_id` |
| Person | `person_id` |
| Membership / Officeholder period | `membership_id` |
| Evidence / Source | `evidence_id` |
| Assertion | `assertion_id` |

Display names are never primary keys.

## Required schema collections

A core snapshot contains:

```text
schema_version
snapshot_id
jurisdictions[]
divisions[]
organizations[]
roles[]
posts[]
people[]
memberships[]
evidence[]
assertions[]
review
certification
extensions?    # optional product/ops metadata
```

The JSON Schema is:

```text
schemas/canonical_representation_core_v0.1.schema.json
```

The deterministic validator and Jurisdiction Package adapter are:

```text
tools/canonical_representation_core.py
```

## Jurisdiction

Required:

- `jurisdiction_ocdid`
- `division_ocdid`
- `name`
- `level`
- `record_status`
- `source_ids[]`

Optional:

- `parent_jurisdiction_ocdid`

Allowed `level` values:

- `FEDERAL`
- `STATE`
- `COUNTY`
- `MUNICIPAL`
- `OTHER`

A jurisdiction references its base Division. Parent jurisdiction relationships
are explicit and never inferred from display names.

## Division

Required:

- `division_ocdid`
- `name`
- `division_type`
- `record_status`
- `source_ids[]`

Optional:

- `parent_division_ocdid`

Allowed `division_type` values:

- `COUNTRY`
- `STATE`
- `COUNTY`
- `MUNICIPALITY`
- `CONGRESSIONAL_DISTRICT`
- `STATE_LEGISLATIVE_DISTRICT`
- `LOCAL_DISTRICT`
- `OTHER`

This is intentionally jurisdiction-neutral. No state-specific ward, place,
position, or chamber field is part of the canonical core.

## Organization

Required:

- `organization_id`
- `jurisdiction_ocdid`
- `name`
- `organization_type`
- `record_status`
- `source_ids[]`

Optional:

- `parent_organization_id`

Allowed `organization_type` values:

- `EXECUTIVE`
- `LEGISLATURE`
- `COUNCIL`
- `BOARD`
- `COMMISSION`
- `OTHER`

Cross-system organization identity may additionally resolve through the shared
identity registry defined in
`docs/contracts/shared-identity-registry-v0.1.md`.

## Role

Required:

- `role_id`
- `label`
- `record_status`
- `source_ids[]`

Optional:

- `aliases[]`

A Role is the normalized formal function, such as `mayor`,
`council-member`, or `state-representative`.

## Post / Office

Required:

- `post_id`
- `organization_id`
- `role_id`
- `division_ocdid`
- `seats`
- `selection_method`
- `record_status`
- `source_ids[]`

Allowed `selection_method` values:

- `ELECTED`
- `APPOINTED`
- `EX_OFFICIO`
- `OTHER`
- `UNKNOWN`

Post semantics, non-geographic seat labels, and internal leadership titles are
governed by
`docs/contracts/representation-role-post-membership-v0.1.md`.

## Person

Required:

- `person_id`
- `name`
- `record_status`
- `source_ids[]`

Names are display facts, not identity keys. Cross-system Person identity uses
the shared identity registry where required.

## Membership / Officeholder

Required:

- `membership_id`
- `person_id`
- `post_id`
- `membership_status`
- `source_ids[]`
- `confidence`

Optional:

- `start_date`
- `end_date`
- `label`
- `designations[]`

Allowed `membership_status` values:

- `CURRENT`
- `FORMER`
- `UNKNOWN`

Allowed `confidence` values:

- `HIGH`
- `MEDIUM`
- `LOW`

## Evidence / Source

Required:

- `evidence_id`
- `source_url`
- `source_class`
- `source_type`
- `retrieved_at`
- `confidence`

Allowed `source_class` values:

- `OFFICIAL`
- `PARTNER`
- `INTERNAL`
- `OTHER`

The raw product/source-specific `source_type` is retained as a string rather
than forcing local source taxonomies into the shared schema.

## Assertion

Required:

- `assertion_id`
- `subject_type`
- `subject_id`
- `field_path`
- `value`
- `evidence_ids[]`
- `normalization_status`
- `review_status`
- `confidence`

Allowed `normalization_status` values:

- `RAW`
- `NORMALIZED`

Allowed `review_status` values:

- `UNREVIEWED`
- `ACCEPTED`
- `REJECTED`
- `NEEDS_EVIDENCE`
- `IDENTITY_CONFLICT`
- `SCOPE_CONFLICT`

Partner writeback uses the stricter append-only assertion contract in
`docs/contracts/partner-assertion-governance-v0.1.md`.

## Record review / QA

Every snapshot has:

```text
review.status
review.reviewer
review.reviewed_at
review.qa_result
review.parity_ok
```

Allowed values:

- `review.status`: `DRAFT | REVIEW | READY | BLOCKED`
- `review.qa_result`: `PASS | FAIL | NOT_RUN`

This makes reviewer, QA result, and `Parity_OK` explicit rather than inferred
from downstream status text.

## Certification

Every snapshot has:

```text
certification.status
certification.raw_complete
certification.normalized_complete
certification.qa_passed
certification.parity_ok
certification.reviewer
certification.verified_at
```

`certified` is valid only when:

```text
raw_complete        = true
normalized_complete = true
qa_passed           = true
parity_ok            = true
```

Factory `tracker_synced` remains an optional operations extension and is not a
public semantic certification gate.

## Raw → normalized → QA → parity workflow

```text
Evidence captured
      ↓
RAW assertions
      ↓
NORMALIZED assertions + canonical records
      ↓
QA result = PASS
      ↓
Parity_OK = true
      ↓
CERTIFIED
```

Unsupported or conflicting records remain fail-closed.

## Generic level examples

Machine-checkable synthetic examples live at:

```text
acceptance/representation/canonical_core/
  municipality.json
  county.json
  state_legislative.json
  congressional.json
```

They prove the same schema can model:

- a municipality with state/county parent jurisdictions;
- a county government;
- a state legislative district;
- a congressional district.

No state-specific schema branch is used.

## Existing pilot compatibility

The regression suite also converts the existing Akron Jurisdiction Package on
`main` into this core model and validates it. The adapter preserves the existing
package IDs as stable native canonical IDs; cross-system shared identity remains
a separate crosswalk layer.

This closes Issue #1 without forcing a destructive migration of already released
Jurisdiction Package artifacts.
