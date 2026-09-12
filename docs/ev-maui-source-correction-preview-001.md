# EV-MAUI-PREVIEW-001 — held source correction and countywide preview

Maui's staged package records Kauanoe Batangan's current service as `ELECTED`.
Official appointment and seating notices establish `APPOINTED`. Separately, the
production representation consumer cannot express Maui's nine residency-qualified
Council offices as countywide seats. This candidate corrects the selection fact
in an isolated package revision and adds an explicit ten-office preview.

## Source correction

| Item | Result |
| --- | --- |
| Exact role | `role-hi-maui-kauanoe-batangan` |
| Office / person | `office-hi-maui-council-kahului` / `person-hi-maui-kauanoe-batangan` |
| Corrected field | RoleTerm `selection_type`: `ELECTED` → `APPOINTED` |
| Durable office method | `ELECTED`, preserved |
| New RAW observations / SourceEvidence / normalized assertions | 3 / 3 / 3 |
| Existing records changed in candidate | One RoleTerm: selection type, source IDs, assertion IDs, correction note |
| Exact service intervals added | 0 |
| JSON/CSV parity | All seven record tables checked |

The RAW observations are in `previews/ev/maui_source_correction.v0.1.json`:

- [Mayor's appointment announcement, December 16, 2025](https://www.mauicounty.gov/m/newsflash/home/detail/18065).
- [Council seating announcement, January 6, 2026](https://mauicounty.us/press-release/batangan-seated-as-councilmember-changes-to-committees-adopted/).
- [Hawaiʻi Office of Elections roster, Maui Council footnote](https://elections.hawaii.gov/resources/elected-officials/).

Official web text was reviewed September 12, 2026. The Mayor's notice described a
planned January 1 assumption; the Council reported the January 5 swearing-in.
Neither is silently converted to an exact tenure start. The old row timestamp,
other holders, leadership, residency areas, warnings, and historical package QA
remain unchanged. The correction receipt records the new review date explicitly.

The original governed archive remains at SHA-256
`9458ec4ce0498daf88bd6a55f88e48c15c95f48b9c1a97ae07b4ffb52acf2110`.
The held revision is stored only under `previews/ev/maui/`, outside package
discovery and production onboarding. Its SHA-256 is
`3ba797f102b18d7c560cd918f2eddb0ffeb406c850e7c1751d6ed7cd9222301a`.

`tools/ev_maui_source_correction.py` reconstructs the pinned original package,
applies the fixed one-role delta, adds three source/normalized assertion joins,
and uses the existing package builder to regenerate CSV, manifest, and checksums
in temporary storage. It verifies all CSV rows against JSON, reproduces the held
ZIP bytes, and checks that only `jurisdiction.json`, `role_terms.csv`,
`manifest.json`, and `SHA256SUMS.txt` differ inside the archives. The ZIP uses
stored entries with fixed timestamps and permissions for portable reproduction.
Its CLI only verifies; it cannot replace a governed package.

## Countywide contract

[Charter §3-1](https://www.mauicounty.gov/736/County-Charter) establishes nine Council
seats elected by all county voters, one for each residency area. The current
[Council roster](https://mauicounty.us/councilmembers/) and each member profile
were checked during the preceding review, together with the
[Mayor directory](https://www.mauicounty.gov/Directory.aspx?did=473).

| Field | Bound value |
| --- | --- |
| Package / Civic GPS jurisdiction | `jurisdiction-hi-maui-county` / `jur-us-hi-maui-county` |
| County GEOID | `15009` |
| Offices / unique current holders | 10 / 10 |
| Office capacities | One Mayor; nine distinct one-seat Council offices |
| Residency areas | All nine original `COUNCIL_RESIDENCY_AREA` records preserved |
| Leadership | Council Chair Alice Lee; Vice-Chair Yuki Lei Sugimura |
| Mode | `MAUI_COUNTYWIDE_RESIDENCY_PREVIEW` |
| Preview only / publication eligible / complete jurisdiction | true / false / false |

The new module is imported only by the new preview runner and its tests. It does
not register a production profile or modify the existing Kauaʻi preview. Every
valid Maui address receives the Mayor and all nine Council offices. Residency
metadata is retained on its corresponding office, with an explicit countywide
representation scope. A district assignment does not filter the office set.

The preview requires the exact office/person/leadership contracts, preserves
source evidence and assertions, and checks a digest of the complete corrected
package. It rejects the uncorrected Batangan selection, lost or duplicate holders,
incorrect residency semantics, missing evidence, provisional identities,
ambiguous county identity, and drift. Failures contain no applicable offices.

## Address controls and validation

| Control | Address | Required result |
| --- | --- | --- |
| Mayor office, Maui island | 200 South High Street, Wailuku, HI 96793 | All 10 offices / 10 holders |
| Council residency office, Lānaʻi island | 814 Fraser Avenue, Lanai City, HI 96763 | Same 10 offices / 10 holders |
| Existing out-of-county control | 25 Aupuni Street, Hilo, HI 96720 | Hawaiʻi County resolves; Maui preview rejects |

Street sources: Mayor directory above and
[Gabe Johnson's official Lānaʻi office contact](https://mauicounty.us/johnson/).
The runner verifies that both positives return identical office/holder records.
A geocoder error does not count as a successful negative control.

```sh
python tools/ev_maui_source_correction.py --repo-root .
python tests/ev_maui_countywide_preview_test.py
python tests/ev_kauai_countywide_preview_test.py
# Requires requests and the reconstructed Civic GPS runtime:
python tools/ev_maui_countywide_preview.py --repo-root . --output artifacts/ev-maui-preview/live.json
```

Twenty Maui unit tests passed locally, covering the correction and provenance
joins, deterministic replay, residency behavior, failure cases, production
isolation, and protected-file output rejection. The twenty existing Kauaʻi
preview tests also passed. Synthetic evidence is labeled `SYNTHETIC_FIXTURE`.
The local live run passed both Wailuku and Lānaʻi City controls with identical
10-office/10-holder results; Hilo successfully resolved to Hawaiʻi County and
was rejected by the Maui preview. Its report records zero canonical writes,
zero auto-promotions, and preservation of protected content.
The CLI emits `LIVE_CIVIC_GPS` only after the live resolver completes all controls.
The existing historical package QA is not relabeled as fresh address validation.

The new read-only CI workflow checks out the exact PR head, verifies the runtime
SHA-256, validates the correction and tests, runs live controls, and uploads the
preview report. Runtime SHA-256 remains
`32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797`.

## Boundaries

Maui remains `ROUTING_ONLY`; its unchanged proposal remains `REVIEW_REQUIRED`
with no production spec. The proposal check constructs an isolated tree containing
only the original Maui package. The runner checks absence of Maui production
catalog/spec entries and preserves the existing Kauaʻi installation. It snapshots
protected configuration and the original Maui package before and after execution.

All nine PR paths are additions. Existing canonical data, package archives,
production consumers/catalog/specs, routing releases, acceptance records, runtime,
Texas release, and Railway configuration remain unchanged. No release/tag write,
publication, deployment, or Kalawao work is included. The draft PR is a held
candidate; merge and any later production activation require separate decisions.
