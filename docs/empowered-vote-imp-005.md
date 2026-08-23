# EV-IMP-005 — Second Real Jurisdiction

## Decision

Use Akron, Colorado as the second real governed jurisdiction proof.

Akron is an authorized D-328 package target and the governed `CO Jurisdiction Factory v0.1` records show normalization, geography authority, parity, replication, two address controls, zero QA failures, and zero blocking gaps all passing. Akron is townwide, so no municipal district adapter is required.

## Fail-closed scope finding

The factory governs current representation but does not contain Election, Contest, or Candidacy tables. The Town's current 2026 Election Information page establishes the April 7, 2026 election and the offices/terms on the ballot, but the governed factory contains no source assertions establishing candidate names or certified outcomes. Current roster term-expiration years must not be used to infer election winners.

Therefore EV-IMP-005 proceeds in two gates:

1. **Second real representation package** — materialize Akron Jurisdiction Package v0.1 from complete factory rows and prove live address → Civic GPS geography → catalog → governed Akron representation with zero canonical writes.
2. **Full Essentials upgrade** — remain fail-closed until authoritative candidate/result evidence is captured and governed, at which point Akron may be rematerialized as Package v0.2.

No civic facts may be reconstructed from summaries, no election outcome may be inferred from the current roster, and no publication/writeback is authorized.
