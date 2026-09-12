# EV-MAUI-PROD-ADAPTER-CANDIDATE-001

The merged Maui preview validates a corrected Mayor/Council package, but the
catalog representation path cannot yet select and dispatch that preview. This
inactive adapter connects the certified projection to the existing catalog
candidate opt-in. It does not activate Maui in the production catalog.

Base `main`: `a6261b5baf9d95a16fa84e39f4f64fb6e50337d7` (PR #63).

## Contract

| Control | Bound value |
| --- | --- |
| Candidate entry | `candidate-hi-maui-countywide-v0.1` |
| Package / Civic GPS jurisdiction | `jurisdiction-hi-maui-county` / `jur-us-hi-maui-county` |
| County GEOID | `15009` |
| Binding mode | `MAUI_COUNTYWIDE_RESIDENCY_CANDIDATE` |
| Scope | Mayor and Council only |
| Offices / current holders / residency areas / leadership roles | 10 / 10 / 9 / 2 |
| SourceEvidence / SourceAssertions | 8 / 13 |
| Candidate only / preview only | true / true |
| Production eligible / publication eligible / complete jurisdiction | false / false / false |

The held corrected archive remains in `previews/ev/maui/` at SHA-256
`3ba797f102b18d7c560cd918f2eddb0ffeb406c850e7c1751d6ed7cd9222301a`.
Its complete package JSON digest remains
`7ddaf33b2184f9a465128cac581e75b5b6a3a5601ca052d5ff9403b2ffc006e3`.
Both the artifact location and all digests are pinned; the original governed
archive and the held archive are unchanged by this candidate.

The source correction still affects one RoleTerm, preserving Batangan's current
service as `APPOINTED` and the office's ordinary selection method as `ELECTED`.
It retains three source observations, three evidence records, and three normalized
assertions added by PR #63. The candidate runner replays the existing correction
and verifies all seven JSON/CSV tables before acceptance. No new tenure date or
source observation is created here.

## Catalog integration

The only existing file changed is `consumers/empowered_vote/countywide_candidate.py`.
It dispatches the exact Maui candidate entry to a new bounded adapter. Existing
Kauaʻi behavior and the catalog loaders, selectors, and production consumer
implementations remain intact.

`candidates/ev/maui_countywide.v0.1.json` is the inactive spec;
`candidates/ev/maui_catalog.v0.1.json` is its isolated catalog. The two existing
onboarding catalog builders reproduce that catalog without modification. The
normal production onboarding runner and route materializer reject this spec.

Both representation entry points require `allow_candidate=True` to load the
candidate catalog. Full Essentials has no candidate opt-in. Loading the candidate
without opt-in fails closed, and the default catalog continues to reject Maui
even when candidate opt-in is supplied. No candidate row is added to the default
catalog. Production and publication flags cannot be enabled by editing the
candidate contract; mixed district, Kauaʻi production, or Texas profile bindings
are rejected.

The adapter calls the unchanged certified Maui projection. All county addresses
receive the Mayor and all nine Council offices. The nine residency areas remain
qualification metadata; district assignments never filter the returned offices.
All Office, Person, RoleTerm, LeadershipRole, provenance, and warning records are
preserved. The complete corrected package digest rejects unreviewed data changes.

## Acceptance evidence

Each control exercises catalog loading, selection, archive reconstruction, and
adapter dispatch. The live-address convenience API is also tested.

| Control | Required result |
| --- | --- |
| 200 South High Street, Wailuku, HI 96793 | 10 offices / 10 holders / 9 residency areas |
| 814 Fraser Avenue, Lanai City, HI 96763 | Identical countywide office and holder records |
| 25 Aupuni Street, Hilo, HI 96720 | Successful Hawaiʻi County resolution; no catalog match |

Each positive also verifies default-catalog rejection, rejection without opt-in,
and rejection by full Essentials. A failed geocoder response cannot satisfy the
negative control. The report retains the catalog and checksum, corrected-source
parity report, package counts, complete projections, control rejections, and
existing-route verification. Synthetic evidence is labeled `SYNTHETIC_FIXTURE`;
the CLI uses the live resolver and emits `LIVE_CIVIC_GPS` only after all controls
complete. CI binds its evidence to the exact checked-out PR head.

Local validation passed all 22 new adapter tests, 20 Maui preview tests, 21 Kauaʻi
adapter tests, 20 Kauaʻi preview tests, 20 Kauaʻi activation tests, and 7 Texas
profile tests. The existing catalog, second-jurisdiction, and third-jurisdiction
script suites also passed. Live Wailuku and Lānaʻi City controls returned identical
10-office/10-holder results; Hilo resolved outside Maui and was rejected.

```sh
python tests/ev_maui_adapter_candidate_test.py
python tests/ev_maui_countywide_preview_test.py
python tools/ev_maui_adapter_candidate.py --repo-root . --output artifacts/ev-maui-adapter-candidate/live.json
```

The new CI workflow has read-only repository permissions and runs only on pull
requests. It verifies checkout identity, rejects changes to protected canonical,
preview, routing, production, and deployment paths, reconstructs the unchanged
core runtime, and runs the adapter tests and live controls. Existing workflows
provide the Kauaʻi, general onboarding/catalog, and Texas regression gates.

## Retained holds and later decisions

This candidate reuses the 2026-09-12 source review recorded by the merged preview;
it does not claim a new roster review or fresh historical package QA. The source
URLs, appointment evidence, and tenure limitations remain documented in
[the preview record](ev-maui-source-correction-preview-001.md). Production
activation will require its own reviewed contract and current-source acceptance.

Maui remains `ROUTING_ONLY` and its original-package proposal remains
`REVIEW_REQUIRED`, with no production spec. The runner checks the existing
compound county route and geography-only release against their pinned hashes.
It performs the proposal check on an isolated copy of the original Maui package.
No Kalawao package is discovered or read by the new runner. Existing Kauaʻi
installation and protected content are checked before and after execution.

Core runtime SHA-256 remains
`32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797`.
There is no canonical replacement, catalog promotion, publication, release/tag
creation, deployment, or Kalawao work. Preparing this draft does not authorize
its merge or a later production activation.
