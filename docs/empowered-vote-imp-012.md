# EV-IMP-012 — Reviewed Onboarding Draft PR Gate

## Decision

Convert an exact EV-IMP-011 reviewed onboarding bundle into a GitHub review branch and **draft** pull request, while continuing to prohibit automatic merge and external publication.

The gate is split in two:

1. `tools/ev_onboarding_pr_request.py` deterministically derives branch/commit/PR metadata from the reviewed EV-IMP-011 bundle hash.
2. `.github/workflows/ev-onboarding-reviewed-pr.yml` is a manual `workflow_dispatch` action that regenerates the exact reviewed bundle, applies it locally, enforces the onboarding-path allowlist, creates a branch/commit, pushes that branch, and opens a draft PR.

## Review binding

The workflow requires:

- `package_jurisdiction_id`;
- the exact 64-character `reviewed_bundle_sha256` produced by EV-IMP-011.

The request generator regenerates EV-IMP-011 immediately. If the regenerated bundle SHA differs, the request fails closed before any branch is created.

## Allowed repository mutation

The reviewed local apply remains restricted to:

- `onboarding/ev/*.v0.1.json`;
- `consumers/empowered_vote/package_catalog.v0.1.json`;
- `civic_gps_extensions/registry_bundles.v0.1.json`.

The workflow checks `git diff --name-only` before commit and aborts if any other path is present.

## GitHub mutation boundary

EV-IMP-012 authorizes only these GitHub mutations after an explicit manual workflow dispatch with an exact reviewed bundle hash:

- create one deterministic onboarding branch;
- create one commit containing the reviewed onboarding files;
- push that branch;
- open one **draft** pull request to `main`.

The gate does **not** authorize:

- marking the PR ready for review automatically;
- merging the PR;
- enabling auto-merge;
- release creation;
- external publication;
- canonical CivicData writeback;
- source/factory spreadsheet mutation.

## Deterministic request metadata

For a non-NOOP reviewed bundle, the request records:

- package jurisdiction ID;
- reviewed bundle SHA-256;
- deterministic branch name using the first 12 hash characters;
- base branch `main`;
- deterministic commit message;
- draft PR title/body;
- `merge_authorized: false`;
- `publication_authorized: false`;
- `canonical_writes: 0`.

Already-materialized jurisdictions remain `NOOP`: no branch and no PR are created.

## Acceptance

EV-IMP-012 passes when:

- production NOOP remains NOOP;
- stale or malformed review hashes fail closed;
- a synthetic READY bundle yields deterministic draft-PR metadata;
- CI compiles and tests the new request gate;
- Civic GPS regressions stay green;
- no automatic merge or publication authority is introduced.
