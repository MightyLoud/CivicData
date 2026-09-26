# OpenStates / CivicPatch OCDID Validation Contract v0.1

Status: **Draft contract implementation for issue #73**

This contract defines the fail-closed path for validating CivicPatch jurisdiction and division identifiers against the governed OpenStates/OCDID registry without requiring CivicPatch or OpenStates to adopt the same database.

## Authority boundary

For this contract:

- **OpenStates/OCDID** is the shared authority for canonical division identity.
- CivicPatch may keep product-native IDs, but shared exports MUST NOT treat a product-local identifier as a replacement for an OCDID.
- A `jurisdiction_ocdid` is valid only when its base division resolves to a canonical OpenStates/OCDID division.
- A `division_ocdid` is valid only when it resolves to a canonical OpenStates/OCDID division.
- Missing, malformed, or ambiguous identifiers fail closed.
- Reviewed temporary mappings may normalize legacy product IDs, but the canonical target MUST itself exist in the registry.

This validator does not mint new OCDIDs.

## Registry lookup path

The pinned OpenStates repository provides two relevant layers:

### 1. Master OCD division registry

```text
data/parquet/master_ocdids/state=<state>/data_0.parquet
```

The current manifest at OpenStates commit
`2301513c99d275cca23cbcdf04aba09dbced3247`
was generated at `2026-09-25T17:53:17.100791+00:00` and contains
`master_ocdids` partitions for all states represented in the source registry,
including Massachusetts and Texas.

The master registry is sufficient to answer:

> Does this canonical division ID exist?

### 2. OpenStates matched/published lookup

```text
data/ocdid_uuid_lookup.csv
data/parquet/ocdid_uuid_lookup/state=<state>/data_0.parquet
```

At the pinned commit, the local matched lookup covers the currently processed
states:

```text
ak, al, az, oh, tx, wa
```

When an exact division is present here, the validator marks it
`PUBLISHED_LOOKUP`.

When a division exists in the master registry but is not yet present in the
matched lookup, the validator may accept it as
`MASTER_REGISTRY_COMPATIBILITY`. This is the temporary compatibility path for
states whose local jurisdiction generation has not yet run.

That compatibility status does **not** claim that an OpenStates jurisdiction
object has already been published for that government.

## Jurisdiction validation

A jurisdiction OCDID is converted to its base division deterministically:

```text
ocd-jurisdiction/country:us/state:ma/place:millbury/government
            ↓
ocd-division/country:us/state:ma/place:millbury
```

The base division MUST exist in the master OCD registry.

The validator does not create a new jurisdiction identity from a display name,
GEOID, FIPS code, URL, or source filename.

## Post / representation division validation

A CivicPatch post or membership may carry a more specific
`division_ocdid`, for example:

```text
ocd-division/country:us/state:tx/place:arlington/council_district:5
```

The exact division MUST exist in the registry after any explicitly reviewed
legacy mapping is applied.

It must also be either:

- the jurisdiction base division; or
- a descendant of that base division.

Cross-state or unrelated divisions fail closed.

## Reviewed compatibility mappings

A legacy source ID may be mapped only through an explicit reviewed record:

```json
{
  "entity_type": "division",
  "source_id": "ocd-division/...legacy...",
  "canonical_id": "ocd-division/...canonical...",
  "review_status": "accepted",
  "reviewed_at": "2026-09-25",
  "reviewer": "...",
  "evidence": "..."
}
```

Rules:

1. Only `review_status = accepted` mappings are usable.
2. The canonical target MUST exist in the registry.
3. Two accepted canonical targets for the same source ID are ambiguous and fail closed.
4. A mapping is normalization/provenance, not a new canonical identifier.
5. Product-native IDs may be retained separately in an identifier crosswalk.

## Massachusetts regression case

CivicMirror issue #80 documented a historical CivicPatch failure mode where
some Massachusetts town divisions were emitted with an inserted county segment,
for example conceptually:

```text
ocd-division/country:us/state:ma/county:worcester/place:millbury
```

The canonical town division is:

```text
ocd-division/country:us/state:ma/place:millbury
```

Current CivicPatch main
`69331c2b0d97e13695dab07ec1d6a969c99a3e4d`
now emits the clean Millbury jurisdiction/division shape.

The regression contract remains necessary so the malformed form cannot silently
re-enter a shared export.

Behavior:

- malformed legacy ID with no reviewed mapping → **reject**
- malformed legacy ID with one accepted mapping to canonical Millbury → **normalize**
- conflicting accepted mappings → **reject as ambiguous**

## Texas positive case

Current CivicPatch emits Arlington council district identifiers such as:

```text
ocd-division/country:us/state:tx/place:arlington/council_district:5
```

The pinned OpenStates lookup contains that exact district ID. It is therefore a
positive `PUBLISHED_LOOKUP` interoperability fixture.

## Fail-closed error classes

The reference validator may emit:

- `OCDID_FORMAT_INVALID`
- `JURISDICTION_BASE_DIVISION_NOT_IN_REGISTRY`
- `DIVISION_NOT_IN_REGISTRY`
- `DIVISION_OUTSIDE_JURISDICTION`
- `STATE_MISMATCH`
- `REVIEWED_MAPPING_AMBIGUOUS`
- `REVIEWED_MAPPING_TARGET_INVALID`
- `REVIEWED_MAPPING_INVALID`

No error class authorizes inferred minting.

## Implementation

Reference implementation:

```text
tools/ocdid_registry_validation.py
```

Acceptance subset:

```text
acceptance/representation/ocdid_registry_v0.1.json
```

Regression tests:

```text
tests/test_ocdid_registry_validation.py
```

## Boundary

This contract validates interoperability payloads only. It does not write to
CivicPatch, OpenStates, Civic Mirror, or the official OCD division registry.
