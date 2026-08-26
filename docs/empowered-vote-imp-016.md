# EV-IMP-016 — Post-Merge Verification and Closure

EV-IMP-016 verifies the final repository state after an EV-IMP-015 authorized merge. It does not mutate GitHub, publish externally, or write canonical CivicData.

A closure may be `CLOSED_PASS` only when the exact authorized PR is closed and merged from the authorized head SHA; the reported squash merge commit is proven reachable from `main`; required post-merge checks pass; production onboarding materialization remains idempotent `NOOP`; canonical writes remain zero; and publication remains false.

The verifier emits deterministic closure evidence with a SHA-256 digest. Head drift, missing main reachability, failed post-merge checks, non-idempotent production materialization, canonical writes, or publication all fail closed.
