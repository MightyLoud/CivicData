# Representation Contract v1

Status: **draft wire/integration contract**

## Semantic foundation

This wire contract implements the repository's frozen representation semantics in
`docs/contracts/representation-role-post-membership-v0.1.md`.

That semantic contract is authoritative for the meaning of Role, Post, Membership,
internal leadership titles, geographic versus non-geographic seat designations,
multi-seat posts, and vacancy calculation. Representation Contract v1 adds the
cross-system wire shape, evidence/assertion envelope, certification state, and
adapter boundaries; it does not redefine those semantics.

## Purpose

Provide one shared representation spine so Jurisdiction Factories, OpenStates `jurisdictions`, CivicPatch, SeeGov, Empowered Vote, and Civic Mirror can refer to the same governments, bodies, posts, people, and service relationships without merging product databases.

## Canonical graph

```text
Division (OCDID)
      |
Jurisdiction (OCDID)
      |
Organization -- Role
      |          |
      +-------> Post ------> representation Division
                    |
               Membership <------ Person
```

Evidence and assertions attach to canonical subjects. Certification governs whether a snapshot is publishable.

## Vocabulary

| Term | Meaning |
|---|---|
| `jurisdiction` | governing entity identified by `ocd-jurisdiction/...` |
| `organization` | council, board, commission, executive body, or other body inside a jurisdiction |
| `role` | normalized function such as `council-member` or `mayor` |
| `post` | role + organization + representation division; the canonical office/seat object |
| `person` | human identity |
| `membership` | one person's service in one post; repeated periods reuse the pair ID and differ by `opened_at` |
| `evidence` | append-only source artifact or source record |
| `assertion` | append-only proposition about a canonical subject supported by evidence |

## Identity ownership

### Shared Organization / Person identity

The repository's canonical cross-system Organization and Person identities are
governed by `docs/contracts/shared-identity-registry-v0.1.md`.

Contract object `id` values remain wire/projection identifiers. When a reviewed
registry mapping exists, `organization.shared_identity_id` carries the
`org-<uuidv4>` identity and `person.shared_identity_id` carries the
`per-<uuidv4>` identity.

A missing shared identity is represented by omission/null, not by name-derived
guessing. Product-native and Factory IDs remain in `identifiers` / registry
crosswalks.

- OpenStates/OCDID owns shared jurisdiction and division identity.
- CivicPatch's `organizations`, `roles`, `posts`, `memberships`, and `people` are the closest current implementation of the representation graph and should be adapted rather than replaced.
- Product-specific meeting, election, stance, finance, bill, and engagement objects stay in their own products.
- Cross-system IDs belong in explicit crosswalks; string matching is not an identity strategy.

## Post identity

A post is the stable tuple:

```text
(organization_id, role_id, division_ocdid)
```

Implementations should use a stable UUID such as UUIDv5 over that tuple. At-large posts use the jurisdiction's base division. Ward/district posts use a scoped division OCDID.

`post.label` is optional display metadata and is **not part of post identity**. It MUST NOT be used to distinguish two otherwise identical `(organization_id, role_id, division_ocdid)` tuples. Under the frozen semantic contract, a non-geographic `Seat`, `Place`, or `Position` designation belongs on Membership; a geographic district belongs in `division_ocdid`. Holder-specific titles such as `Mayor Pro Tem` also belong on Membership when they describe the occupant of another post rather than a distinct seat.

## Vacancy rule

Never create a fake person named `Vacant`.

For a tracked post:

```text
vacancy_count = meta_headcount - count(open memberships)
```

The omission is meaningful only when the roster/certification state is current enough to support it.

## Certification

Shared certification is:

```text
RAW evidence present
  -> normalized
  -> QA passed
  -> Parity_OK = TRUE
  -> certified
```

`tracker_synced` and the Factory's own `COMPLETE` state remain operational fields under `factory_extension`; they are not semantic civic facts.

CivicPatch publication/review status does **not** automatically satisfy Factory certification.

## Write boundaries

| Data | Authority |
|---|---|
| jurisdiction/division identity | OpenStates `jurisdictions` + approved OCDID rules |
| evidence collection | Factories, CivicPatch collectors, partner submissions |
| organization/post/person/membership snapshot | certified representation layer |
| meeting/transcript/moment | SeeGov |
| candidate/stance/finance/voter UX | Empowered Vote |
| accountability evidence/bills/events | Civic Mirror |
| review/promotion state | Factory/CivicPatch review workflow |

Partner systems may submit proposed evidence/assertions. They do not perform last-write-wins updates against certified representation data.

## Existing CivicData compatibility

`jurisdiction_package_v0.2` remains supported during rollout. `bodies -> organizations`, `offices -> posts`, and `role_terms -> memberships` are compatibility mappings, not an in-place schema replacement. Existing Empowered Vote consumers stay on the current package until parity tests prove the new projection.

See `docs/representation-compatibility-v1.md`.

## First implementation

1. `schemas/representation_contract_v1.schema.json` defines the wire contract.
2. `adapters/civicpatch/export_representation.py` performs a read-only CivicPatch export.
3. The exporter fails closed on missing references, source-less memberships, fake vacancy people, and impossible headcounts.
4. A real one-jurisdiction CivicPatch snapshot is the next input.
5. The same jurisdiction is projected from a Factory.
6. Reconciliation uses only:

```text
SAME
FACTORY_ONLY
CIVICPATCH_ONLY
FIELD_CONFLICT
IDENTITY_CONFLICT
BLOCKED
```

No write-back occurs until this diff is stable.


## Election / Contest / Candidacy extension

Representation-only snapshots remain valid without election objects.

When election data is present, the contract carries all four fields together:

```text
elections
contests
candidacies
election_certification
```

Partial presence fails closed.

### Election

```text
Election
  id
  jurisdiction_ocdid
  election_date
  name
  evidence_ids
  identifiers
```

An Election is the dated election event. It does not identify a seat by itself.

### Contest

```text
Election
   |
Contest --------> Post
```

A Contest is the race for one canonical Post in one Election. The Post link is the
bridge between elections and the representation spine; consumers do not recover
office identity by matching contest names.

### Candidacy

```text
Contest
   |
Candidacy ------> Person (optional by candidate kind)
```

A named `person` candidacy MUST resolve to a canonical Person before the
extension is eligible for public Full Essentials. A `write_in_bucket` MUST have
`person_id = null`; aggregate write-ins are not fake people.

Candidacy preserves the source candidate identifier, ballot/display name,
outcome, votes, vote share, evidence links, and external IDs.

### Separate election certification

Representation certification does not imply complete election coverage.

For Full Essentials, `election_certification` must satisfy:

```text
status           = certified
scope_complete   = true
qa_passed        = true
unexplained_loss = 0
```

This mirrors the governed Jurisdiction Package v0.2 gates. A snapshot may
therefore be safe for representative lookup while still failing closed for
election/candidate display.

### Tacoma acceptance case

The governed Tacoma v0.2 package is the first election-extension proof:

```text
complete Contract snapshot:
  2 elections
  9 contests
  26 candidacies
  17 named-person candidacies
  9 write-in buckets

747 Market Street / District 2:
  6 applicable offices
  5 applicable contests
  15 candidate rows
```

The Contract shadow is required to match the existing Empowered Vote governed
Full Essentials path before any routing change.


## Interoperable snapshot envelope

When a Contract v1 payload crosses a system boundary, it SHOULD be accompanied by
the repository's `Interoperable Snapshot Manifest v0.1` defined in:

```text
docs/contracts/interoperable-snapshot-manifest-v0.1.md
schemas/interoperable_snapshot_manifest_v0.1.schema.json
```

The manifest is the shared provenance/fingerprint envelope; this Contract remains
the semantic payload.

For a Representation Contract v1 export:

```text
manifest.schema_version = representation-contract/1.0.0-draft
manifest.scope.jurisdiction_ocdid = contract.jurisdiction.jurisdiction_ocdid
manifest.certification = contract.certification public fields
manifest.payload.content_sha256 = SHA256(exact Contract payload bytes)
```

`canonical_data_versions` SHOULD pin the OCDID source and shared identity-registry
version used by the adapter. Election certification remains inside the Contract
payload because it is a domain-specific completeness gate distinct from the
manifest's representation certification.

A matching payload hash alone does not establish the same governed snapshot; the
manifest fingerprint also incorporates producer/adapter version, pinned source
snapshots, scope, certification, and canonical reference versions.
