# Adapter Matrix — Representation Contract v1

| Contract | Jurisdiction Factory | OpenStates jurisdictions | CivicPatch | SeeGov | Empowered Vote | Civic Mirror |
|---|---|---|---|---|---|---|
| `jurisdiction_ocdid` | jurisdiction key | **canonical** | `jurisdictions.jurisdiction_ocdid` | government lookup | government/office lookup | office/government lookup |
| `division_ocdid` | boundary/district key | **canonical division** | `divisions.ocdid`, `posts.division_ocdid` | service area | address routing | office geography |
| `organization_id` | body key | not core today | `organizations.id` | meeting body | chamber/body | body/bill context |
| `role_id` | normalized role | not core today | `roles.id` | speaker role | office type | official role |
| `post_id` | normalized post | not core today | `posts.id` | participant context | representative/race target | official/office target |
| `person_id` | normalized person | separate people domain | `people.id` | speaker identity | politician identity | official identity |
| `membership_id` | occupant/service period | not core today | `memberships.id` | office-at-meeting-time | representation | official service |
| `evidence` | RAW source/evidence | source metadata | `source_records` / sources | source meeting/video | cited sources | uploaded evidence |
| `assertion` | RAW/normalized assertion | source-backed fields | claims/derivation | proposal only | proposal only | evidence submission |
| `certification` | **authoritative gate** | identity verification | review/publish state | consume | consume | consume |

## Factory → Contract

1. Preserve authoritative sources as `evidence`.
2. Convert field-level RAW facts into `assertions`.
3. Export canonical organization/post/person/membership only after normalization resolves identity.
4. `certified` requires RAW + normalized + QA + parity.
5. `tracker_synced` stays in `factory_extension`.
6. Blocked evidence never replaces the certified snapshot.

## CivicPatch ↔ Contract

```text
jurisdictions  -> jurisdiction
organizations  -> organizations
roles          -> roles
posts          -> posts
people         -> people
memberships    -> memberships
source_records -> evidence + assertions
claims         -> assertion/review history
```

Keep CivicPatch's product DB as-is initially. Add an export/import adapter before attempting schema convergence.

## SeeGov

- meeting body → `organization_id`
- identified official speaker → `person_id`
- office context at meeting date → membership period
- transcript, moment, agenda, vote outcome stay SeeGov-owned
- roster discrepancy → proposed assertion, never direct canonical edit

## Empowered Vote

- address → division(s) → posts → open memberships
- candidate/race targets post(s), not current membership
- candidate crosswalks to `person_id` after identity resolution
- stances, campaign finance, budgets stay Empowered Vote-owned
- corrections return as proposed assertions

## Civic Mirror

- official → person + membership
- office → post
- evidence → evidence + assertion links
- bills/events stay Civic Mirror-owned
- sponsors link by `person_id` / membership when resolvable

## Conflict rule

```text
partner observation
      ↓
proposed assertion
      ↓
Factory/CivicPatch review
      ↓
accepted/rejected
      ↓
new certified snapshot
```

No adapter may perform last-write-wins against canonical representation data.
