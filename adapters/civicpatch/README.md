# CivicPatch → Representation Contract v1

This adapter is intentionally **read-only**. It converts a CivicPatch canonical snapshot into the shared Representation Contract without changing CivicPatch or CivicData canonical state.

## Production source

The authoritative integration source is CivicPatch's current Postgres representation graph, not the rendered open-data YAML.

`extract_snapshot.sql` reads one jurisdiction in a **read-only, repeatable-read transaction** and returns the tables required by the exporter:

```text
jurisdictions
organizations
roles + active role_aliases
posts
people
memberships
source_records
```

## Extract

```bash
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
  -v jurisdiction_ocdid='ocd-jurisdiction/country:us/state:co/place:akron/government' \
  -Atf adapters/civicpatch/extract_snapshot.sql \
  > civicpatch-snapshot.json
```

This command performs **zero writes**.

## Export

```bash
python adapters/civicpatch/export_representation.py \
  civicpatch-snapshot.json \
  --output civicpatch-representation.json \
  --generated-at 2026-09-25T00:00:00Z
```

## Reconcile against a Factory package

```bash
python adapters/factory/export_representation.py \
  data/normalized/co/jurisdiction-co-akron/jurisdiction.json \
  --output factory-representation.json \
  --generated-at 2026-09-25T00:00:00Z

python tools/reconcile_representation.py \
  factory-representation.json \
  civicpatch-representation.json \
  --output reconciliation.json
```

Every reconciliation item ends as one of:

```text
SAME
FACTORY_ONLY
CIVICPATCH_ONLY
FIELD_CONFLICT
IDENTITY_CONFLICT
BLOCKED
```

Crosswalk candidates are emitted separately as `PROPOSED`; the reconciler performs no canonical writes.

## Rendered open-data migration path

`rendered_open_data.py` can project a public rendered roster for historical or migration comparison. It is **always uncertified**. It must not replace the Postgres snapshot path because the rendered form loses body/post/membership semantics.

## Fail-closed rules

The canonical exporter rejects rather than guesses when:

- IDs are malformed or foreign keys do not resolve;
- a post or organization belongs to another jurisdiction;
- a membership has no source URL;
- an open roster exceeds `post.meta_headcount`;
- one person has multiple open posts in the same organization;
- a fake `Vacant`/`Vacancy` person is present;
- `certified` is requested without RAW + normalized + QA + parity gates.

## Certification boundary

CivicPatch publication/review state is **not** automatically equivalent to Jurisdiction Factory certification. The exporter therefore emits `uncertified` unless an orchestration layer explicitly supplies certification evidence.

## Write-back boundary

Do not add partner-to-canonical write-back until reconciliation is stable and crosswalk decisions have a reviewed promotion path.


## Shared identity registry

An optional reviewed shared identity registry can be supplied to the exporter:

```bash
python adapters/civicpatch/export_representation.py \
  civicpatch-snapshot.json \
  --identity-registry reviewed-shared-identity-registry.json \
  --output civicpatch-representation.json
```

The adapter resolves only ACTIVE registry crosswalks using exact CivicPatch
`organizations.id` and `people.id` UUIDs with `system = civicpatch`.

A missing crosswalk emits `shared_identity_id: null`. The exporter never uses
names to infer shared identity and never mutates the registry.

See `docs/shared-identity-adapter-integration-v1.md`.
