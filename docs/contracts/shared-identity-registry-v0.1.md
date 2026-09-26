# Shared Organization and Person Identity Registry v0.1

Status: **Draft contract implementation for issue #71**

This contract defines the shared identity layer used when CivicData, CivicPatch,
SeeGov, Civic Mirror, Empowered Vote, and other consumers need to refer to the
same government body or human without joining on names.

It is deliberately additive. Existing product/package IDs remain valid inside
their owning systems and are preserved through crosswalks.

## v0.1 registry steward

For v0.1, the shared registry is stewarded in:

```text
MightyLoud/CivicData
```

Repository maintainers are the minting/review authority for shared
`organization_id` and `person_id` values until a successor governance
decision explicitly transfers that authority.

This does not transfer ownership of CivicPatch, SeeGov, Civic Mirror, Empowered
Vote, OpenStates, or their product-native identifiers.

## Canonical IDs

Shared IDs are opaque UUIDv4 values with an entity prefix:

```text
organization_id = org-<uuidv4>
person_id       = per-<uuidv4>
```

Examples:

```text
org-11111111-1111-4111-8111-111111111111
per-22222222-2222-4222-8222-222222222222
```

### Why UUIDv4

The shared ID MUST NOT be derived from:

- organization name;
- person name;
- office title;
- jurisdiction display name;
- email;
- URL;
- any other mutable display fact.

A rename therefore cannot re-key identity.

UUIDv5/name-derived IDs may remain inside a product that already uses them, but
they are product-native identifiers and map through the shared crosswalk.

## Entity model

### Organization

An Organization is a continuing government body such as a council, board,
commission, or executive body.

Minimum registry fields:

```text
canonical_id
entity_type = organization
display_name
status
created_at
superseded_by
```

A display-name change does not change `canonical_id`.

Create a new Organization only when the represented institutional entity itself
changes rather than merely its label.

### Person

A Person is a human identity.

Minimum registry fields are the same shape with:

```text
entity_type = person
```

Names and contact details are evidence/display facts, never identity keys.

## Crosswalk model

Each product-native identifier is retained in a crosswalk:

```text
crosswalk_id
entity_type
canonical_id
system
external_id
external_url
status
verified_at
source
```

The active key is:

```text
(entity_type, system, external_id)
```

That key may resolve to **at most one active canonical identity**.

Examples of `system`:

- `civicpatch`
- `civic_mirror`
- `seegov`
- `empowered_vote`
- `jurisdiction_factory`
- `openstates`

Consumers join through canonical IDs or reviewed crosswalks, never display
names.

## Relationship to existing CivicData package IDs

Existing package identifiers such as:

```text
body-co-akron-board-of-trustees
person-co-akron-jared-jefferson
```

are not rewritten by this contract.

They can be retained as `system = jurisdiction_factory` crosswalk identifiers
and mapped to shared `org-...` / `per-...` values when cross-system identity
resolution is needed.

The existing Texas identity workflow already establishes the key principle:
new evidence may upgrade a Person from provisional to authoritative while
preserving the same canonical Person identity.

## Rename rule

A rename changes only `display_name`.

Example:

```text
org-...  "Example Board"
    ↓ rename
org-...  "Example Select Board"
```

The canonical ID and every external crosswalk remain unchanged.

The rename is recorded as an append-only registry event.

## Merge rule

A Person merge is a reviewed assertion that two existing canonical Person
records represent the same human.

Requirements:

1. source and target are the same entity type;
2. all records being merged are active;
3. reviewer, review time, reason, and evidence are present;
4. crosswalks moved by the merge are recorded in the event;
5. source canonical records are retained with `status = MERGED`;
6. `superseded_by` points to the retained target identity;
7. the merge event stores enough prior state to reverse the merge.

A name match by itself is never sufficient to merge.

Organization merges follow the same mechanics but require institutional
continuity evidence.

## Mistaken-merge rollback

Rollback does not erase the merge event.

Instead it:

1. restores the source canonical identities to `ACTIVE`;
2. restores only the crosswalk assignments moved by that merge;
3. appends a `ROLLBACK_MERGE` event pointing to the original merge event.

If a moved crosswalk has since been reassigned elsewhere, rollback fails closed
for manual review rather than overwriting newer state.

## Split rule

A split is used when evidence shows one canonical identity had incorrectly
combined multiple real identities.

A reviewed split:

1. creates a new opaque canonical ID;
2. moves an explicit list of crosswalks to the new identity;
3. records the move in an append-only `SPLIT` event;
4. does not infer which external IDs move based on names.

Rollback of a split restores only the explicitly moved crosswalks and retires
the split-created identity; history remains queryable.

## Event model

Registry changes that affect identity meaning are append-only events:

- `RENAME`
- `MERGE`
- `ROLLBACK_MERGE`
- `SPLIT`
- `ROLLBACK_SPLIT`

Every event requires:

```text
event_id
event_type
entity_type
reviewed_at
reviewer
reason
evidence
details
```

## Fail-closed rules

The registry rejects:

- malformed shared IDs;
- duplicate canonical IDs;
- duplicate active external-key mappings;
- crosswalks pointing to missing canonical IDs;
- crosswalk entity type mismatches;
- merges across entity types;
- merge/split actions without review metadata;
- ambiguous external-ID resolution;
- rollback when the recorded prior state can no longer be restored safely.

## Reference implementation

Schema:

```text
schemas/shared_identity_registry_v0.1.schema.json
```

Deterministic helper:

```text
tools/shared_identity_registry.py
```

Acceptance fixture:

```text
acceptance/representation/shared_identity_registry_v0.1.json
```

Regression tests:

```text
tests/test_shared_identity_registry.py
```

## Boundary

This contract establishes shared identity semantics and registry mechanics only.
It does not write into partner systems and does not authorize automatic identity
merges from names, fuzzy matching, or model confidence.
