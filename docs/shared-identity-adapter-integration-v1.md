# Shared Identity Registry ↔ Representation Contract v1

Status: **read-only adapter integration; no identity writes**

## Purpose

Carry reviewed shared Organization and Person identities through the existing
Factory and CivicPatch representation adapters without changing either source
system's native IDs.

The canonical identity registry remains:

```text
docs/contracts/shared-identity-registry-v0.1.md
tools/shared_identity_registry.py
```

Representation adapters are **registry consumers only**.

## Data flow

```text
Shared Identity Registry
     | reviewed ACTIVE crosswalks only
     |
     +-------------------------+
     |                         |
     v                         v
Jurisdiction Factory       CivicPatch
body_id / person_id        organization UUID / person UUID
     |                         |
     v                         v
Factory adapter            CivicPatch adapter
     |                         |
     +------------+------------+
                  |
                  v
       Representation Contract v1
       organization.shared_identity_id
       person.shared_identity_id
                  |
                  v
         reconciliation / consumers
```

## Exact crosswalk keys

Factory adapters query the registry using:

```text
entity_type = organization
system      = jurisdiction_factory
external_id = <Factory body_id>
```

and:

```text
entity_type = person
system      = jurisdiction_factory
external_id = <Factory person_id>
```

CivicPatch adapters query:

```text
entity_type = organization
system      = civicpatch
external_id = <CivicPatch organizations.id UUID>
```

and:

```text
entity_type = person
system      = civicpatch
external_id = <CivicPatch people.id UUID>
```

External IDs are exact registry keys. Display names, emails, titles, URLs, and
fuzzy similarity are never lookup keys.

## Missing crosswalk

A valid registry with no matching ACTIVE crosswalk produces:

```json
"shared_identity_id": null
```

The adapter does not mint an identity and does not fail simply because a reviewed
crosswalk does not yet exist.

## Fail-closed cases

The adapters reject:

- an invalid registry;
- ambiguous ACTIVE external-ID mappings;
- crosswalk/entity type mismatch;
- an ACTIVE crosswalk pointing to a non-ACTIVE canonical entity;
- malformed registry identity state.

This is intentionally stricter than name matching.

## Reconciliation behavior

### Same reviewed identity

```text
Factory per-123...
CivicPatch per-123...
        ↓
SAME / SHARED_IDENTITY
```

No additional crosswalk proposal is produced.

### Different reviewed identities

```text
Factory per-123...
CivicPatch per-456...
same display name
        ↓
IDENTITY_CONFLICT / REVIEWED_SHARED_IDENTITY_MISMATCH
```

The reconciler does **not** emit a new name-based proposal over a reviewed
registry disagreement. The registry must be reviewed/corrected.

### No reviewed identity

An exact unique normalized-name overlap may still be emitted as a **PROPOSED**
crosswalk candidate. It is never auto-promoted.

## CLI

Factory:

```bash
python adapters/factory/export_representation.py \
  jurisdiction.json \
  --identity-registry reviewed-shared-identity-registry.json \
  --output representation.json
```

CivicPatch:

```bash
python adapters/civicpatch/export_representation.py \
  civicpatch-snapshot.json \
  --identity-registry reviewed-shared-identity-registry.json \
  --output representation.json
```

Both commands read the registry and source snapshot only.

## Empowered Vote shadow

The Contract v1 consumer exposes reviewed identities as:

```text
applicable_offices[].shared_organization_id
applicable_offices[].holders[].shared_person_id
recent_certified_contests[].candidates[].shared_person_id
```

Legacy product-native IDs remain present for compatibility.

## Write boundary

```text
registry writes          = 0
Factory writes           = 0
CivicPatch writes        = 0
Empowered Vote writes    = 0
canonical_writes         = 0
```

Mints, merges, splits, renames, and rollbacks remain explicit reviewed actions in
the shared identity registry workflow. Adapters never perform them.
