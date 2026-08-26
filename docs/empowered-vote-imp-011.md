# EV-IMP-011 — Reviewed Onboarding Promotion Gate

## Decision

Bind human review to an exact deterministic EV-IMP-010 staging bundle and permit that reviewed bundle to be applied to a local repository checkout only when the bundle SHA-256 still matches.

EV-IMP-011 closes the gap between a reviewed `ADD` materialization and the repository files that must change, while keeping branch push, pull-request creation, merge, publication, and CivicData writeback outside this gate.

## Flow

1. Regenerate the EV-IMP-010 materialization for a governed package.
2. Build a deterministic descriptor containing the package jurisdiction, entry ID, routing strategy, action count, allowed file paths, actions, and staged-file SHA-256 values.
3. Hash the descriptor to produce `bundle_sha256`.
4. Review the staging bundle and record that exact hash.
5. Apply only with `--apply --expected-bundle-sha256 <reviewed hash>`.
6. Regenerate immediately before application. Any hash drift fails closed.
7. Preflight all files.
8. Apply only `ADD` actions.
9. Re-run EV-IMP-010 and require every affected surface to become `NOOP`.
10. Roll back applied files if post-apply verification fails.

## Allowed repository surfaces

The promotion gate can touch only:

- `onboarding/ev/*.v0.1.json`;
- `consumers/empowered_vote/package_catalog.v0.1.json`;
- `civic_gps_extensions/registry_bundles.v0.1.json`.

Absolute paths, path traversal, duplicate paths, unexpected actions, or any other repository surface fail closed.

## Review binding

The approval token is not a package name or a branch name. It is the exact SHA-256 of the deterministic bundle descriptor.

If any staged file, action, routing strategy, package identity, catalog candidate, or registry candidate changes between review and application, the regenerated bundle hash changes and application stops.

## Existing production jurisdictions

Akron and Fircrest are already materialized, so their EV-IMP-011 plans must remain `NOOP`. This provides a production idempotence regression for both supported routing strategies.

## Authority boundaries

EV-IMP-011 does not:

- research or infer routing authority;
- promote an EV-IMP-009 `REVIEW_REQUIRED` proposal;
- create or alter governed civic facts;
- push a Git branch;
- open a pull request;
- merge code;
- publish externally;
- write back to canonical CivicData sources.

The result explicitly preserves:

- `canonical_writes: 0`;
- `branch_push_authorized: false`;
- `pull_request_authorized: false`;
- `merge_authorized: false`;
- `publication_authorized: false`.
