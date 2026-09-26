# Interoperable Snapshot Manifest v0.1

Status: **Draft contract implementation for issue #74**

This contract defines the smallest shared manifest that accompanies a representation
snapshot when data crosses a system boundary.

It does **not** replace existing package or release manifests. Existing CivicData
jurisdiction manifests, Kauai/Maui publication manifests, CivicPatch manifests,
or partner-native manifests may remain richer. This envelope provides one common
fingerprint/provenance surface across them.

## Required envelope

Every shared representation export must include:

```text
manifest_version
schema_version
generated_at
producer
source_snapshots[]
scope
certification
canonical_data_versions
payload
manifest_sha256
```

### manifest_version

Version of this manifest contract.

v0.1 value:

```text
0.1
```

### schema_version

The semantic schema of the payload itself.

Examples:

```text
representation-contract/1.0.0-draft
civicpatch-representation/2026-09-25
```

This is intentionally distinct from `manifest_version`.

### generated_at

UTC/offset-aware timestamp when the export was generated.

This is an observation/export timestamp. It is **not** a substitute for source-stated
term dates, appointment dates, election dates, or other civic facts.

### producer

```json
{
  "system": "jurisdiction_factory",
  "adapter_version": "factory-representation/0.1"
}
```

Both fields are required. Adapter-version changes must be visible even when the
payload schema is unchanged.

### source_snapshots

At least one pinned source snapshot:

```json
{
  "system": "civicpatch",
  "snapshot_id": "<commit/version/run>",
  "locator": "<repo/path/url>"
}
```

The `snapshot_id` must be a durable commit, version, run, release, or other
producer-defined snapshot identifier. "latest" by itself is not sufficient.

### scope

```json
{
  "jurisdiction_ocdid": "ocd-jurisdiction/...",
  "division_ocdids": ["ocd-division/..."],
  "complete_jurisdiction": false
}
```

The manifest must state whether the payload is complete for the jurisdiction or
is a bounded/partial slice.

### certification

Shared certification fields:

```text
status
raw_complete
normalized_complete
qa_passed
parity_ok
verified_at
```

Allowed `status` values:

- `uncertified`
- `evidence_review`
- `external_blocker`
- `rule_fix`
- `certified`

`certified` requires all four boolean gates to be true.

Factory-specific `tracker_synced` remains an operations extension and is not
required by this public manifest.

### canonical_data_versions

A string map of governed reference versions used by the adapter when available.

Example:

```json
{
  "ocdid": "openstates/jurisdictions@2301513c99d275cca23cbcdf04aba09dbced3247",
  "identity_registry": "shared-identity/0.1"
}
```

The object is required so consumers do not have to infer whether reference
versions were omitted accidentally. It may be empty only when the producer truly
used no governed external reference data.

### payload

```text
media_type
locator
bytes
content_sha256
```

`content_sha256` is computed over the exact exported payload bytes.

For JSON built through the reference helper, bytes are canonical UTF-8 JSON:

- keys sorted;
- compact separators;
- Unicode preserved;
- one trailing newline.

### manifest_sha256

The SHA-256 of the canonical manifest JSON **excluding** the
`manifest_sha256` field itself.

This fingerprint changes when governed metadata changes, including:

- payload content;
- payload schema version;
- adapter version;
- source snapshot;
- scope;
- certification state;
- canonical reference versions.

## Snapshot equivalence

Two manifests describe the same governed snapshot only when both
`manifest_sha256` values match after validation.

A matching payload hash alone is not enough. The same bytes generated under a
different adapter version or source snapshot are intentionally a different
governed snapshot.

## Existing-manifest compatibility

### CivicData jurisdiction package

Existing `manifest.json` files remain package-local inventories. A package
exported to a partner adds this interoperable envelope beside the package; it
does not rewrite historical package manifests.

### CivicData publication manifests

Kauai/Maui manifests already contain rich release hashes, target commits, scope,
and holds. They remain authoritative for those releases. A cross-system
representation payload may reference the release/package as a
`source_snapshots[]` entry and use this common envelope.

### CivicPatch

CivicPatch may preserve its native output shape. The adapter generates this
manifest over the exported payload bytes and pins the CivicPatch source
commit/snapshot.

## Reference implementation

Schema:

```text
schemas/interoperable_snapshot_manifest_v0.1.schema.json
```

Builder/validator:

```text
tools/snapshot_manifest.py
```

Acceptance examples:

```text
acceptance/representation/snapshot_manifest/
  factory-example.json
  factory-example.manifest.json
  civicpatch-example.json
  civicpatch-example.manifest.json
```

Tests:

```text
tests/test_snapshot_manifest.py
```

## Fail-closed behavior

The manifest is invalid when:

- any required field is missing;
- hashes are not lowercase SHA-256 values;
- producer or adapter version is missing;
- no source snapshot is pinned;
- jurisdiction scope is missing;
- a division ID is malformed;
- `certified` is asserted while any certification gate is false;
- payload bytes/hash do not match;
- manifest fingerprint does not match;
- timestamps are not offset-aware ISO 8601 values.

No missing metadata is inferred from product-internal state.

## Boundary

This contract records provenance and reproducibility. It does not itself certify
underlying civic facts, infer term dates, publish a release, or authorize partner
writeback.
