# EV-IMP-013 — CI-Bound Draft PR Readiness Gate

## Decision

Add a narrow readiness gate after EV-IMP-012. The gate decides whether an onboarding **draft** pull request is eligible to be marked ready for review.

It does not merge, enable auto-merge, publish, mutate canonical CivicData, or change source/factory spreadsheets.

## Required evidence

The decision is bound to:

- the exact EV-IMP-012 reviewed bundle SHA-256;
- the deterministic onboarding branch from EV-IMP-012;
- one exact 40-character pull-request head commit SHA;
- the live pull-request state and changed-file list;
- exact-head GitHub Actions evidence.

## Hard readiness conditions

The PR must be:

- `OPEN`;
- still a draft;
- based on `main`;
- on the exact deterministic EV-IMP-012 branch;
- at the exact expected head SHA;
- using the deterministic EV-IMP-012 title;
- carrying the reviewed bundle SHA-256 in its body;
- in merge state `CLEAN`.

Changed files are restricted to:

- `onboarding/ev/*.v0.1.json`;
- `consumers/empowered_vote/package_catalog.v0.1.json`;
- `civic_gps_extensions/registry_bundles.v0.1.json`.

## Required exact-head CI

All of these workflows must have a completed successful run for the exact PR head SHA:

- `Empowered.Vote Essentials consumer`;
- `Civic GPS live smoke`;
- `EV onboarding live batch`.

Missing, pending, cancelled, or failed exact-head evidence fails closed.

## Output

The gate returns `READY_TO_MARK_READY` only after every condition passes. The output explicitly preserves:

- `merge_authorized: false`;
- `auto_merge_authorized: false`;
- `publication_authorized: false`;
- `canonical_writes: 0`.

Already-materialized production jurisdictions remain `NOOP`.

## Promotion boundary

EV-IMP-013 authorizes only a readiness **decision**. A caller may use a separate explicit GitHub mutation to mark the draft PR ready after this decision. Automatic merge, auto-merge, releases, publication, and canonical writeback remain out of scope.
