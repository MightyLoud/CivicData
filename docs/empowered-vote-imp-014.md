# EV-IMP-014 — Final Merge Eligibility Decision

## Decision

Add a final fail-closed decision gate between an EV-IMP-013 ready-for-review onboarding pull request and any actual GitHub merge.

EV-IMP-014 may return `MERGE_ELIGIBLE`. It **does not merge** the pull request and explicitly records `merge_authorized: false`. The actual merge remains a separate, explicit authorization and GitHub mutation.

## Required evidence

The gate requires all of the following to remain true at the same exact pull-request head SHA:

- the EV-IMP-012 reviewed bundle SHA-256 still regenerates to the same deterministic request;
- the pull request is `OPEN` and no longer draft;
- base branch is `main`;
- head branch matches the deterministic reviewed onboarding branch;
- head SHA exactly matches the requested merge-eligibility SHA;
- pull-request title and reviewed bundle identity have not drifted;
- GitHub reports the pull request as mergeable;
- merge state is `CLEAN`;
- every changed file is on the governed onboarding allowlist;
- all three exact-head workflows are completed successfully:
  - `Empowered.Vote Essentials consumer`;
  - `Civic GPS live smoke`;
  - `EV onboarding live batch`;
- there is no active latest `CHANGES_REQUESTED` review state;
- an explicit final merge-review acknowledgement is present in the evidence.

Any failed condition returns a hard failure rather than a weaker eligibility state.

## Allowed changed files

The merge-eligibility decision recognizes only:

- `onboarding/ev/*.v0.1.json`;
- `consumers/empowered_vote/package_catalog.v0.1.json`;
- `civic_gps_extensions/registry_bundles.v0.1.json`.

A pull request containing any other changed path is not merge eligible.

## Review semantics

Review evidence is reduced to the latest submitted state per actor. An active latest `CHANGES_REQUESTED` state blocks eligibility. `APPROVED`, `COMMENTED`, `DISMISSED`, and `PENDING` review records are preserved in the decision evidence but do not themselves grant merge authority.

The separate `merge_review_acknowledged: true` input is intentional. It represents the final human acknowledgement that the exact PR state being evaluated is the state intended for the merge decision.

## Output

A passing result records:

- `status: MERGE_ELIGIBLE`;
- reviewed bundle SHA-256;
- pull-request number;
- exact head branch and SHA;
- changed-file list;
- required and successful workflow lists;
- latest review states;
- `merge_review_acknowledged: true`;
- `merge_action_required: true`;
- `merge_authorized: false`;
- `auto_merge_authorized: false`;
- `publication_authorized: false`;
- `canonical_writes: 0`.

## Authority boundary

EV-IMP-014 does not authorize or perform:

- pull-request merge;
- auto-merge;
- release creation;
- external publication;
- canonical CivicData writeback;
- source or factory spreadsheet mutation.

The next action after `MERGE_ELIGIBLE` must therefore be a separately authorized merge using the exact eligible head SHA.
