# EV-KAUAI-PREVIEW-001 — bounded countywide preview

Kauaʻi's governed v0.1 package has no division rows. The production EV
representation consumer therefore returns `PACKAGE_REPRESENTATION_DIVISION_MISSING`
even when Civic GPS correctly routes an address to Kauaʻi. The package represents
the Mayor and a single seven-seat, unnumbered, countywide at-large Council office.

This candidate adds a separate explicit preview contract and runner. It consumes
the existing package without inventing a division or numbering the Council seats.
It does not change the production representation consumer or catalog selection.

## Bounded contract

| Field | Bound value |
| --- | --- |
| Package jurisdiction | `jurisdiction-hi-kauai-county` |
| Civic GPS jurisdiction | `jur-us-hi-kauai-county` |
| County GEOID | `15007` |
| Mode | `COUNTYWIDE_PREVIEW` |
| Mayor | `office-hi-kauai-mayor`, one holder |
| Council | `office-hi-kauai-council-member-multiseat`, seven holders |
| Office rows / unique current holders | 2 / 8 |
| Package archive SHA-256 | `fac5f85e589d237252f7067563f90f73c09f566237967201ef30c994d524081e` |
| `preview_only` | `true` |
| `publication_eligible` / `complete_jurisdiction` | `false` / `false` |

The preview binding is `previews/ev/kauai_countywide.v0.1.json`. Its roster pins
the existing package's eight person IDs and two leadership IDs. The existing
artifact loader verifies the archive checksum, package checksums, manifest, QA,
identity graph, and evidence contract. Package schema and jurisdiction must match.

The preview requires an active Kauaʻi Civic GPS route, rejects ambiguous county
results, and requires the exact two offices, constituency semantics, capacities,
and unique holder set. It retains the original Office, Person, RoleTerm and
LeadershipRole records, source evidence, source assertions, and warnings in its
output. Known RoleTerm aliases use the shared projection without changing source
records. Neither current-service dates nor a new identity authority status is
inferred. The source records' legacy `ACTIVE` person status is preserved; explicitly
provisional identities fail closed under the shared package contract.

Any binding, package, roster, source join, or geography failure returns
`FAIL-CLOSED` without applicable offices. Success is a bounded preview of the
package's recorded Mayor and Council, not certification of complete jurisdiction
coverage or new verification of current roster facts.

## Controls and evidence

The [Hawaiʻi Office of Elections proclamation](https://elections.hawaii.gov/2026-proclamation/)
describes seven Kauaʻi Councilmembers elected at large. The existing governed
package retains its [Council](https://www.kauai.gov/Government/Council) and
[Mayor](https://www.kauai.gov/Government/Office-of-the-Mayor) source links.

The preview runner resolves two distinct official street addresses using live
Civic GPS:

| Control | Address | Expected preview |
| --- | --- | --- |
| Mayor office | 4444 Rice Street, Lihue, HI 96766 | Same 2 offices / 8 holders |
| County directory / Council office | 4396 Rice Street, Lihue, HI 96766 | Same 2 offices / 8 holders |
| Outside county | 25 Aupuni Street, Hilo, HI 96720 | Hawaiʻi County resolves; Kauaʻi preview fails closed |

Positive address sources are the Mayor page and the official
[County Directory](https://www.kauai.gov/Home-M/County-Directory). The outside-county
address is the existing EV-IMP-019 Hawaiʻi routing control. A geocoder error is
never counted as a passing negative control.

The package's original QA includes a street address and a BAS point label. Those
are preserved unchanged; they are not reported as two live street-address tests.
Local unit tests label their evidence `SYNTHETIC_FIXTURE`. Only the CLI, after
calling the live resolver, emits `LIVE_CIVIC_GPS` evidence. CI checks out the exact
PR head and reconstructs the unchanged Civic GPS runtime with SHA-256
`32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797`.

```sh
python tests/ev_kauai_countywide_preview_test.py
python tools/ev_kauai_countywide_preview.py --repo-root . --output artifacts/ev-kauai-preview/live.json
```

The live command requires the reconstructed Civic GPS runtime and dependencies,
as shown in `.github/workflows/ev-kauai-countywide-preview.yml`. It checks that
both streets return identical countywide records and saves the full preview
evidence as a CI artifact. The 20 local tests cover roster and source preservation,
loss and duplicate rejection, identity and geography isolation, production
consumer behavior, and retained proposal holds.

## Production holds

Hawaiʻi County, Honolulu County, Kauaʻi County, and Maui County remain
`ROUTING_ONLY`, with proposals `REVIEW_REQUIRED` and `production_spec = null`.
The runner checks these four holds, absence of Hawaiʻi catalog entries and
production onboarding specs, and hashes protected repository content before and
after preview execution. The existing throughput lane continues to certify the
full staged inventory separately.

No canonical data, package archives, production consumers, routing releases,
catalog entries, onboarding specs, core runtime, or deployment configuration is
modified by this candidate. Kalawao is outside its binding, controls, and changed
paths. No publication or deployment is part of this preview. Draft PR review,
ready-for-review conversion, and merge remain separate lifecycle decisions.
