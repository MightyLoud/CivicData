# EV-MAUI-PROD-ACTIVATION-CANDIDATE-001

This draft proposes installing Maui's bounded Mayor/Council representation in the
default catalog after the inactive adapter merged in PR #64. Preparation base:
`d2004dc3cd4828bfef28b05f5ee061d80d9c7d57`. Main activation requires approval of the
certified PR head and merge. This draft does not publish or deploy anything.

## Proposed behavior

The default representation catalog returns the Mayor and all nine Council seats
for any valid Maui County address, without candidate opt-in. Each Council seat
retains its residency qualification; those qualifications do not filter voters.
The output preserves 10 office rows, 10 current holders, 9 residency areas, and
2 leadership roles. Full Essentials remains unsupported.

| Contract | Value |
| --- | --- |
| Entry | `hi-maui-countywide-representation-v0.1` |
| Profile | `maui_countywide_mayor_council_v0.1` |
| Binding mode | `MAUI_COUNTYWIDE_RESIDENCY_REPRESENTATION` |
| GEOID | `15009` |
| Candidate only / production eligible | false / true |
| Publication eligible / complete jurisdiction | false / false |
| Production spec | `onboarding/ev/maui-county.v0.1.json` |
| Acceptance receipt | `acceptance/ev/maui_countywide.v0.1.json` |
| Fresh review | `acceptance/ev/maui_source_review.v0.1.json` |

The receipt SHA-256 is
`7b5e0ba92020b59bacb3959b17fa7735e62d92c9b75f5f697ea4406e598ba8c8`.
It binds the source review, existing correction receipt, complete corrected
package, production binding, existing route, and exact address controls. The
consumer requires a matching installed spec before serving the production entry.

This installation reads the unchanged corrected archive already stored under
`previews/ev/maui/`, at SHA-256
`3ba797f102b18d7c560cd918f2eddb0ffeb406c850e7c1751d6ed7cd9222301a`.
The complete package JSON remains
`7ddaf33b2184f9a465128cac581e75b5b6a3a5601ca052d5ff9403b2ffc006e3`.
The original governed archive is not replaced. The corrected Batangan RoleTerm
retains `APPOINTED`; the office's ordinary selection method remains `ELECTED`.
No Office, Person, RoleTerm, LeadershipRole, residency, or package provenance
record changes in this PR.

## Fresh official-source acceptance

The September 12 review retains 13 official source observations with exact text
excerpts, retrieval timestamps, response hashes, and excerpt hashes. Its 25
normalized assertions cover 10 holders, 9 residency qualifications, 2 leadership
roles, the appointment, countywide electorate, and 2 address controls. Source
joins and holder/residency/leadership parity pass. These are acceptance evidence;
they do not overwrite historical canonical package observations or QA.

The official [State Elections list](https://elections.hawaii.gov/resources/elected-officials/)
confirms Mayor Richard Bissen, all nine Council incumbents and residency areas,
and Batangan's appointment. The current [Council roster](https://mauicounty.us/councilmembers/)
and all nine linked member profiles confirm the roster, Chair Alice Lee, and
Vice-Chair Yuki Lei Sugimura. Tasha Kama is labeled In Memoriam and is excluded
from the current roster.

The [Council FAQ](https://mauicounty.us/frequently-asked-questions/) explicitly
states that all county voters may vote in Council elections for all nine
residency areas and that Councilmembers are elected at large despite their
residency requirements. It also confirms the Wailuku street control. The
[Johnson profile](https://mauicounty.us/johnson/) confirms the Lānaʻi control.
The [Council seating notice](https://mauicounty.us/press-release/batangan-seated-as-councilmember-changes-to-committees-adopted/)
confirms the appointed Kahului vacancy fill. Appointment announcement and
swearing-in dates are not silently converted into exact canonical tenure dates.

Three county-government pages returned HTTP 502 during the fresh review: the
Mayor directory, Charter landing page, and Mayor appointment announcement. The
successful current official sources above establish the required acceptance
facts; the review records those retrieval limitations explicitly.

Fresh-review SHA-256:
`b85827b4056d70e70ebb8e1e69bb02a60da3009854d5d80840a2edfe00c4b6b2`.
The production consumer fails closed before September 12 and from **October 12,
2026 UTC** onward. This is a conservative 30-day revalidation policy, not a claim
that the term expires then. Renewal requires reviewed sources and a contract
update; changing receipt flags cannot silently extend freshness or publication.

## Routing, onboarding, and compatibility

The existing `BASE-HI-MAUI-COUNTY` compound state/county route and geography-only
release are verified by their existing hashes and reused without edits. The
release still contains zero offices and zero officeholders. Core runtime SHA-256
remains `32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797`.

Only the validated catalog/spec/receipt combination makes Maui `READY`. With the
explicit installation removed, its original-package proposal remains
`REVIEW_REQUIRED`; route existence never auto-promotes it. In the candidate,
Kauaʻi and Maui are explicitly installed while Hawaiʻi County and Honolulu
County remain held. Kalawao behavior and data remain unchanged.

Maui onboarding replay produces three NOOPs and zero writes. Existing Kauaʻi,
Tacoma, Akron, Fircrest, and Texas catalog entries and all prior production specs
and acceptance receipts are preserved. Compatibility checks now recognize the
two explicitly installed counties and still reject every unreviewed promotion.
Maui preview and candidate entry points preserve their original scopes and
candidate opt-in; the new production profile is a separate validated contract.

## Validation and diff controls

The new activation tests cover source/receipt/spec tampering, expiry and future
dates, attempted publication, mixed profiles, archive drift, correction drift,
missing installation, absence of route-based promotion, county ambiguity,
residency semantics, full-Essentials rejection, and idempotent materialization.
All 137 local unit tests across the new and existing Maui/Kauaʻi/Texas suites
passed, together with seven catalog/onboarding script suites.

The live default-catalog controls passed:

| Address | Result |
| --- | --- |
| 200 South High Street, Wailuku, HI 96793 | 10 offices / 10 holders / 9 residency areas |
| 814 Fraser Avenue, Lanai City, HI 96763 | Identical office and holder records |
| 25 Aupuni Street, Hilo, HI 96720 | Hawaiʻi County resolved; default catalog rejected |

A failed geocoder response cannot satisfy the negative. The activation runner
replays all seven JSON/CSV parity tables and preserves protected content before
and after acceptance. Synthetic and live evidence are labeled separately.
The prerequisite PR #64 artifact is referenced in the receipt; this PR's own
live evidence is attached to its exact head to avoid circular commit references.

```sh
python tests/ev_maui_production_activation_test.py
python tools/ev_maui_production_activation.py --repo-root . --output artifacts/ev-maui-production-activation/live.json
```

The shared activation diff check requires the exact checkout, preserves every
non-Maui catalog entry, and allows only the new Maui spec and two acceptance
records under production configuration. It rejects changes to canonical data,
previews, inactive candidate contracts, routing, core runtime, hosted service,
and deployment configuration. The existing Kauaʻi activation and Maui candidate
workflows use this check while continuing their full regression tests; the new
Maui workflow repeats it and runs default-catalog live acceptance. All three
workflows have read-only repository permissions and pull-request triggers.

The proposed scope is 26 paths: 9 additions and 17 compatibility/configuration
edits. No canonical package replacement, release/tag publication, external
publication, deployment/redeployment, or Kalawao work is authorized by this draft.
