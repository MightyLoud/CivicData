# EV-KAUAI-PROD-ADAPTER-CANDIDATE-001

Kauaʻi's governed Mayor/Council package has no division rows. The original
production representation path requires a division and cannot consume that
package. The certified preview already implements its countywide semantics.
This candidate connects that validated projection to the actual catalog-facing
representation path, while keeping production activation explicitly disabled.

## Candidate contract

| Control | Bound value |
| --- | --- |
| Base `main` | `f88d804537aa39b00c1df0e90b9e04b0bfd13ef4` |
| Candidate entry | `candidate-hi-kauai-countywide-v0.1` |
| Package / Civic GPS jurisdiction | `jurisdiction-hi-kauai-county` / `jur-us-hi-kauai-county` |
| County GEOID | `15007` |
| Binding mode | `COUNTYWIDE_CANDIDATE` |
| Scope | Mayor and Council only; Prosecuting Attorney omitted |
| Office rows / current holders / leadership rows | 2 / 8 / 2 |
| SourceEvidence / SourceAssertions / QA checks | 4 / 8 / 14 |
| Archive SHA-256 | `fac5f85e589d237252f7067563f90f73c09f566237967201ef30c994d524081e` |
| Candidate only | `true` |
| Production eligible / publication eligible / complete jurisdiction | `false` / `false` / `false` |

The archive checksum is enforced by the candidate adapter and existing artifact
loader. All canonical Office, Person, RoleTerm, LeadershipRole, evidence,
assertion, and warning records remain intact. The Council is one unnumbered
seven-seat office. No package division, numbered Council seat, tenure date, or
new authoritative identity status is fabricated. The shared validator rejects
explicitly provisional identities and preserves legacy ACTIVE records.

## Integration

`candidates/ev/kauai_countywide.v0.1.json` is an inactive candidate spec.
`candidates/ev/kauai_catalog.v0.1.json` is its isolated one-entry catalog.
The two existing onboarding catalog builders preserve `countywide_binding` and
all four hold flags; acceptance checks that both builders reproduce the checked
candidate catalog exactly. Default production metadata stays unchanged.

`package_catalog.load_catalog` and both catalog representation entry points
accept `allow_candidate=True` as an explicit opt-in. Without it, a candidate
catalog fails with `COUNTYWIDE_CANDIDATE_NOT_ENABLED`. With it, the adapter
requires the exact candidate identity, bounded office contract, pinned archive,
and disabled production/publication flags. District bindings and the Texas
production profile cannot be combined with the countywide candidate. Full
Essentials has no candidate opt-in.

The adapter calls the certified countywide projection and adds catalog metadata
and candidate status. Its output remains `preview_only=true`,
`candidate_only=true`, `production_eligible=false`, and
`publication_eligible=false`. This PR provides production integration code for
review; it does not authorize this entry for production service.

The candidate runner verifies the existing `BASE-HI-KAUAI-COUNTY` routing record
by its canonical hash, compound state/county scope, retained `ROUTING_ONLY`
flag, and unchanged geography-only release. It generates a temporary candidate
catalog for acceptance and performs zero route writes. The generic production
onboarding runner and route materializer explicitly reject countywide candidate
specs. Existing proposal logic and all four Hawaiʻi REVIEW_REQUIRED holds remain
unchanged. Generic compound-route discovery is not broadened in this PR.

## Acceptance

The full path is exercised for every control:

`catalog loading → selection → archive reconstruction → countywide dispatch → governed projection`

| Control | Expected result |
| --- | --- |
| 4444 Rice Street, Lihue, HI 96766 | 2 offices / 8 current holders |
| 4396 Rice Street, Lihue, HI 96766 | Identical countywide roster |
| 25 Aupuni Street, Hilo, HI 96720 | Hawaiʻi County resolves; candidate selection rejects |

A geocoder error or unresolved negative address never counts as passing negative
evidence. Each positive also proves that the default catalog rejects Kauaʻi and
the candidate catalog rejects access without opt-in. Acceptance retains the
catalog and its checksum, package hash, roster/provenance output, source review,
route verification, production holds, and control results. CI records the exact
PR head, checks protected paths against its base, and reconstructs the unchanged
runtime SHA-256 `32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797`.

```sh
python tests/ev_kauai_adapter_candidate_test.py
python tests/ev_kauai_countywide_preview_test.py
python tools/ev_kauai_adapter_candidate.py --repo-root . --output artifacts/ev-kauai-adapter-candidate/live.json
```

Local unit evidence is labeled `SYNTHETIC_FIXTURE`. The CLI calls the live resolver
and labels completed live evidence `LIVE_CIVIC_GPS`. Adversarial controls cover
activation attempts, malformed/mixed bindings, geography errors, ambiguous
counties, poison Civic GPS facts, corrupted archives, holder/source/leadership
loss, identity drift, deterministic output, onboarding roundtrip, route drift,
and blocked production staging. Existing Tacoma, Akron, Fircrest, Texas profile,
preview, proposal, and materialization checks remain required.

## Coverage and future activation

The 2026-09-09 readiness assessment cross-checked the package roster against the
official [Mayor](https://elections.hawaii.gov/cok-mayor/) and
[Council](https://elections.hawaii.gov/cok-councilmembers/) lists. This review
does not change the package's 2026-08-23 observation date or create canonical
SourceEvidence/SourceAssertion records. A separate elected
[Prosecuting Attorney](https://elections.hawaii.gov/cok-prosecuting-attorney/)
is outside this package, so `complete_jurisdiction=false` is mandatory.

The [2026 proclamation](https://elections.hawaii.gov/2026-proclamation/) sets
the next Mayor/Council term transition at noon on December 1, 2026. The candidate
source review records revalidation before that transition. This metadata is not
a production freshness policy or an activation receipt.

Merge, activation, publication, and deployment require separate decisions.
Activation needs a reviewed production contract and current-source acceptance;
the candidate flags must not simply be flipped. This candidate changes no live
catalog, production onboarding spec, canonical archive, registry/release, core
runtime, hosted service, deployment configuration, or Kalawao scope. The Texas
Release and Railway deployment are outside this PR.
