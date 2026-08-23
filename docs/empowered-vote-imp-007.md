# EV-IMP-007 — Third Real Jurisdiction: Fircrest, Washington

## Decision

Use Fircrest, Washington as the third real governed Empowered.Vote jurisdiction and the first jurisdiction after Tacoma to exercise Package v0.2 Full Essentials through the repeatable EV-IMP-006 onboarding pipeline.

## Source boundary

The governed `WA Jurisdiction Factory v0.1` establishes Fircrest's citywide division, seven elected council positions, seven current role terms, current leadership, identifiers, provenance, QA, and a City Hall routing control. Pierce County Auditor certified 2023 and 2025 final election reports establish the candidate fields, outcomes, and vote totals for all seven current council positions. A second official City of Fircrest facility address provides the second package routing control required by the v0.2 contract.

Election-only candidate identities are added only where the certified reports name a candidate who is not already a current official. Write-in totals remain non-person buckets. No winner, officeholder, term, or identity is inferred from currentness alone.

## Package

- Jurisdiction: `jurisdiction-wa-fircrest`
- GEOID: `5323970`
- Schema: `0.2`
- Package archive SHA-256: `5abb205fc316c6167a75c40b42875cf5a84681bd63b1e63af973103c0e4879ab`
- `jurisdiction.json` SHA-256: `a830d96a0b74aea9dd998153cefc418ffe71737e3ef90cf6c798689956a40a47`
- 1 division, 2 bodies, 7 offices, 12 people, 7 current role terms, 9 leadership roles
- 2 elections, 7 contests, 19 candidacies
- 12 named PERSON candidacies, 7 WRITE_IN_BUCKET candidacies
- 16 governed SourceEvidence records; compact package projection intentionally omits redundant SourceAssertion rows while retaining source references on governed facts
- QA failures: 0; blocking gaps: 0; parity: true; election scope complete: true; unexplained loss: 0
- Address controls: 115 Ramsdell Street and 555 Contra Costa Ave

## Runtime boundary and remediation

The first live attempt failed closed because the Census address response for Fircrest resolved Pierce County but did not expose an `Incorporated Places` row, so a simple place-GEOID bundle could not activate Fircrest. No city identity was inferred from the address text or ZIP code.

The remediation adds a generic `MUNICIPAL_BOUNDARY_OVERLAY` routing strategy. After the exact Civic GPS engine resolves the parent jurisdiction and geocoded point, the extension performs point-in-polygon against the Washington State Department of Transportation `City Limits` polygon layer. That layer is sourced from Washington State Office of Financial Management incorporated-municipality boundaries and exposes `CityFIPSLongPlaceCode`. Fircrest activates only when the point intersects the polygon filtered to `CityFIPSLongPlaceCode='5323970'`.

Civic GPS remains geography-only. The Fircrest release contains zero offices and zero officeholders, the boundary overlay contains no applicable-office or action rules, and the governed package owns representation, elections, candidates, provenance, QA, and warnings. Pierce County may independently contribute its own released facts; the Fircrest overlay contributes zero Fircrest civic-fact rows.

The new `full_essentials_catalog.py` consumer is jurisdiction-agnostic. Fircrest-specific information exists only in governed data, the onboarding spec, routing metadata, and tests. No Fircrest condition is added to consumer code.

## Acceptance

EV-IMP-007 passes only if both live official addresses resolve through the exact Civic GPS engine plus the authoritative boundary overlay to `jur-us-wa-fircrest`, the catalog selects the v0.2 Fircrest package, the consumer returns 7 applicable offices / 7 contests / 19 candidacies, write-in buckets remain non-person records, outputs are deterministic, the Fircrest routing layer contributes zero civic-fact rows, and canonical writes remain zero.

Publication and consumer writeback are not authorized by this implementation gate.
