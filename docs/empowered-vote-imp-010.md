# EV-IMP-010 — Deterministic Onboarding Materialization

## Decision

Convert an EV-IMP-009 `READY` proposal into a deterministic staging bundle for the three repository surfaces required by governed onboarding:

- `onboarding/ev/<jurisdiction>.v0.1.json`;
- `consumers/empowered_vote/package_catalog.v0.1.json`;
- `civic_gps_extensions/registry_bundles.v0.1.json`.

The tool does **not** edit those repository files in place. It emits candidate file contents plus a manifest describing `ADD` or `NOOP` actions. Conflicting existing identities fail closed.

## Authority boundary

EV-IMP-010 cannot upgrade a `REVIEW_REQUIRED` EV-IMP-009 proposal. Routing authority must already be governed. The materializer never researches, infers, or manufactures geography authority.

It also does not create jurisdiction packages, civic facts, offices, officials, election facts, candidates, or source assertions.

## Idempotence

Existing production jurisdictions must materialize entirely as `NOOP`:

- Akron — `CENSUS_GEOID`;
- Fircrest — `MUNICIPAL_BOUNDARY_OVERLAY`.

Any drift between a generated candidate and an existing onboarding spec, catalog entry, or routing identity is a hard failure rather than an overwrite.

## Output

For one jurisdiction the tool writes a staging directory containing candidate versions of each affected repository file and `materialization-manifest.json`.

The manifest records:

- package jurisdiction ID;
- catalog entry ID;
- routing strategy;
- per-file action (`ADD` or `NOOP`);
- number of changes required;
- conflicts;
- `repository_mutated: false`;
- `canonical_writes: 0`;
- `publication_authorized: false`.

`--verify-production` regenerates every production jurisdiction and requires `changes_required = 0` for all of them.

## Promotion boundary

The staging bundle is review evidence, not an automatic repository mutation. A future gate may apply an `ADD` bundle to a branch after review, but publication, external distribution, canonical CivicData writeback, and automatic merge remain separately authorized operations.
