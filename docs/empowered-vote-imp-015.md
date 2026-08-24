# EV-IMP-015 — Explicit Merge Execution Gate

## Decision

Cross the EV-IMP-014 stop boundary only after a fresh, exact human authorization that is bound to the pull request number and its exact head SHA.

The required authorization text is:

`AUTHORIZE MERGE PR #<number> @ <40-character-head-sha>`

Anything else fails closed.

## Preconditions

Immediately before producing an executable merge request, EV-IMP-015 reruns EV-IMP-014 against fresh evidence. The PR must still be `MERGE_ELIGIBLE`, including the reviewed bundle binding, non-draft state, exact head, clean merge state, allowlisted onboarding diff, required exact-head CI success, no active `CHANGES_REQUESTED`, and explicit final merge-review acknowledgement.

## Authorized mutation

A passing request authorizes exactly one GitHub squash merge of the identified PR at the identified head SHA. The merge API call must supply that SHA as its expected head so head drift fails closed.

## Still prohibited

EV-IMP-015 does not authorize auto-merge, release creation, external publication, canonical CivicData writeback, or source/factory spreadsheet mutation. A merge authorization is one-shot and does not transfer to another PR or another commit.

## Acceptance

EV-IMP-015 passes when exact authorization yields deterministic one-shot squash-merge metadata; partial or stale authorization fails closed; non-eligible evidence fails closed; production NOOP remains NOOP; existing EV/Civic GPS gates remain green; and canonical writes remain zero.
