# EV-KAUAI-PROD-ACTIVATION-CANDIDATE-001

This draft proposes an explicit default-catalog installation of Kauaʻi's bounded
Mayor/Council representation after the adapter candidate merged in PR #59.
Preparation base: `d2c0fbafaff4bb541676e963eb102f751f5f61c2`.
Main activation requires separate approval of the certified PR head and merge.
Publication and deployment remain held.

## Proposed behavior

The default representation catalog returns one countywide Mayor office and one
unnumbered seven-seat Council office, with eight current holders and two leadership
overlays. No candidate opt-in is required for this explicit production profile.
The original preview and candidate contracts retain their opt-in and scope limits.

The new entry `hi-kauai-countywide-representation-v0.1` is paired with
`onboarding/ev/kauai-county.v0.1.json` and the hash-bound acceptance receipt
`acceptance/ev/kauai_countywide.v0.1.json`. Its flags are `candidate_only=false`,
`production_eligible=true`, `publication_eligible=false`, and
`complete_jurisdiction=false`. Full Essentials remains unsupported.

The package archive remains pinned to
`fac5f85e589d237252f7067563f90f73c09f566237967201ef30c994d524081e`.
Existing records, source joins, legacy ACTIVE identities, and unresolved tenure
intervals are preserved. Explicit provisional identities remain rejected. No seat
numbers, package divisions, officeholders, or tenure dates are invented.
The elected Prosecuting Attorney is outside this Mayor/Council scope.

## Source review and fail-closed expiry

The September 9, 2026 review confirms the package roster and leadership against
the official [Mayor](https://elections.hawaii.gov/cok-mayor/),
[Council incumbents](https://elections.hawaii.gov/cok-councilmembers/), and
[County Council roster and leadership](https://www.kauai.gov/Government/Council/Councilmembers-2024-2026)
pages. The [Prosecuting Attorney page](https://elections.hawaii.gov/cok-prosecuting-attorney/)
confirms the omitted office, and the
[2026 election proclamation](https://elections.hawaii.gov/2026-proclamation/)
provides the next term transition.

The production consumer fails closed before the review date and from
December 1, 2026 UTC onward. A future review requires a separately reviewed receipt
and any necessary contract update; the consumer never silently extends freshness.
Receipt SHA-256:
`19813da27e25d3bc1e3792c1e73e81ac9b6b2f58be98a3535b664cb26787062e`.
The receipt records package/source acceptance, not approval to merge or publish.
It also records the prerequisite PR #59 live evidence; this PR's own live evidence
is separately attached to its exact head to avoid a circular commit/hash reference.

## Routing and onboarding boundaries

The existing `BASE-HI-KAUAI-COUNTY` route and its GEOID `15007` compound state/county
scope are verified by hash and reused without edits. Its routing release continues
to contain zero offices and zero officeholders. Runtime SHA-256 remains
`32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797`.

Only a valid, explicitly installed catalog/spec/receipt combination makes Kauaʻi
READY. Route existence alone still produces REVIEW_REQUIRED. Materialization of
the proposed installation produces three NOOPs and zero canonical writes.
Hawaiʻi County, Honolulu County, and Maui County retain their production holds;
Kalawao is excluded from this change. The expected candidate inventory is
`3 READY / 5 REVIEW_REQUIRED / 1 BLOCKED`; the preparation base remains `2 / 6 / 1`.
The four pre-existing catalog entries and other onboarding specs are unchanged.

## Acceptance

The activation workflow checks the exact PR head, protected diff, receipt integrity,
expiry, package and route hashes, production scope, candidate compatibility,
existing consumer/onboarding regressions, and retained county holds. It runs two
live positives (`4444 Rice Street` and `4396 Rice Street`, Lihue HI 96766) through
the default catalog, and a successfully resolved Hilo address as a rejected
outside-county negative. Evidence includes the exact source commit and full
projections. Synthetic test fixtures are labeled separately.

This candidate does not authorize a GitHub Release mutation, external publication,
Railway deployment/redeployment, canonical data changes, or additional counties.
