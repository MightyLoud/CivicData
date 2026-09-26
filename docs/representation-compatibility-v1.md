# Representation Contract v1 — CivicData compatibility

The new representation graph is additive. `jurisdiction_package_v0.2` remains valid for existing Empowered Vote consumers while adapters migrate.

| Existing CivicData package | Representation Contract v1 | Migration rule |
|---|---|---|
| `records.divisions` | `division_ocdid` references | retain existing IDs; crosswalk to OCDID before promotion |
| `records.bodies` | `organizations` | preserve body identity; do not remint on rename |
| `records.offices` | `posts` | map office/seat to `(organization, role, division)` |
| `records.people` | `people` | preserve canonical person ID where identity is resolved |
| `records.role_terms` | `memberships` | preserve source dates and evidence; currentness becomes open/closed service state |
| `records.leadership_roles` | Membership-level label/title | preserve the formal Post; do not mint a new Post unless authoritative law establishes a distinct office |
| `provenance.source_evidence` | `evidence` | preserve source ID + URL |
| `provenance.source_assertions` | `assertions` | preserve field-level provenance |
| package QA | `certification` | only promote when RAW + normalized + QA + parity are satisfied |

## Non-breaking rule

Do not replace `jurisdiction_package_v0.2` in-place. During v1 rollout, generate both representations from the same certified source package and parity-test them.

## Reconciliation vocabulary

Every compared entity/field ends in exactly one state:

```text
SAME
FACTORY_ONLY
CIVICPATCH_ONLY
FIELD_CONFLICT
IDENTITY_CONFLICT
BLOCKED
```

No conflict is resolved by last-write-wins.
