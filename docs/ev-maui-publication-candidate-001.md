# EV-MAUI-PUBLICATION-CANDIDATE-001

This draft prepares one metadata-only integration manifest for the Maui
Mayor/Council profile merged in PR #65. It does not authorize or execute a release,
tag creation, publication, deployment, or changes to the production catalog.

## Immutable integration

| Contract | Value |
| --- | --- |
| Integration target | `2b3e8d5df11ed4f4b19f7579c9bd1663131070bf` |
| Integration tree | `f44d953d2e31d04cebce20368627b5938c83d140` |
| Certified activation head | `fe15b3c6a61a4f46851a52992369428ab9ef413b` |
| Integration PR | [#65](https://github.com/MightyLoud/CivicData/pull/65) |
| Profile | `maui_countywide_mayor_council_v0.1` |
| County GEOID | `15009` |
| Scope | 10 offices / 10 holders / 9 residency areas / 2 leadership roles |

The target tree is identical to the certified activation head's tree. The manifest
describes Mayor and all nine Council seats. Council seats apply countywide; their
residency qualifications do not filter voters or create separate governments.
The appointed holder selection and the office's ordinary elected selection method
remain distinct. Exact tenure intervals remain unresolved. Full Essentials,
election results, complete-jurisdiction coverage, and hosted delivery are not certified.

## Proposed asset

| Field | Value |
| --- | --- |
| Tag | `maui-mayor-council-integration-v0.1` |
| Target | Immutable integration commit above |
| Sole asset | `maui-mayor-council-integration-manifest-v0.1.json` |
| Asset size | 5,596 bytes |
| Asset SHA-256 | `eb577b26a899f5e03bb6450225438bcbebd0efb3b53993e14426eddb8506683a` |
| Tag reserved / release created | No / No |

The asset contains identifiers, hashes, scope, review dates, evidence references,
and explicit holds. It contains no raw package archive, officeholder records,
source excerpts, or public endpoint. The versioned schema fixes every nested
value and rejects extra payload fields. Verification reports and retained live
evidence sit outside `release-assets/` and are not proposed release assets.

The manifest retains `CANDIDATE_PUBLICATION_HELD`, with merge, publication, and
deployment authorization false. Preparation approval does not authorize execution.
A later release decision must bind the exact manifest bytes and target, recheck
source facts, and explicitly authorize the operation. The candidate's own head is
recorded in CI verification, avoiding a commit containing its own SHA.

## Retained acceptance evidence

The original artifact from [activation run 34717704026](https://github.com/MightyLoud/CivicData/actions/runs/34717704026),
job `103617800188`, artifact `10305356930`, is retained as exact base64 ZIP bytes
under `candidates/ev/maui_publication.v0.1/evidence/`.

| Evidence | Size | SHA-256 |
| --- | --- | --- |
| Original GitHub ZIP | 11,581 bytes | `96f16d92b8bbdabe13b12260d5de61183e63cf1771cc4c319fafe48ca0c175f1` |
| Sole member `live.json` | 137,349 bytes | `5fed9c6740d1fa9d3f76c86ab3d2a6fb8b7d35c8f4feba9336588a0d143f7a67` |

GitHub's artifact expires October 12, 2026 at 20:44:19 UTC. The repository copy
preserves the original evidence after that date. Retention does not extend source
acceptance or authorize publication.

The retained evidence contains Wailuku and Lānaʻi City positive controls with
identical 10-office/10-holder representations, 9 residency areas, and candidate
opt-in rejection. The Hilo control retains successful matched Hawaiʻi County
geography and the rejected consumer result. A geocoder failure cannot satisfy the
negative control. Seven correction JSON/CSV tables pass parity; onboarding replay
records exactly three NOOPs, zero writes, and zero automatic promotions.
This candidate validates retained live evidence; its offline build does not claim
a new geocoder run. Existing activation CI lanes continue their own live checks.

## Source freshness and boundaries

The unchanged [September 12 source review](../acceptance/ev/maui_source_review.v0.1.json)
retains 13 official observations and 25 normalized assertions. QA confirms
10 holder joins, 9 residency joins, 2 leadership joins, valid source joins, and
`parity_ok: true`. Its hash is pinned by the production consumer and manifest.
Three county-government pages returned HTTP 502; the review documents the
successful official alternatives supporting all required acceptance facts.

Validation fails closed from **October 12, 2026 UTC** onward. This is the existing
30-day revalidation policy, not an officeholder term end. A later publication
decision requires a fresh official-source recheck. No review dates are extended.

All six existing production catalog entries, all specs and receipts, original and
corrected package archives, inactive adapters, routes, runtime, hosted service,
deployment configuration, Texas release, and Kauaʻi release remain unchanged.
Hawaiʻi County and Honolulu remain held. No Kalawao work is included.
Production eligibility stays true; publication eligibility and complete-jurisdiction
status stay false. Repository integration does not certify a hosted Maui endpoint.

## Validation and CI compatibility

The candidate has exactly nine changed paths: eight new publication files and one
shared diff-guard update. The update recognizes only this fixed base/tree and exact
path set, requires the eight additions plus the guard edit, and validates all
manifest, schema, receipt, catalog, package, routing, runtime, and evidence hashes.
Every other tracked path must match the activation target. The original production
guard continues to apply to changes outside this metadata candidate.

The new PR-only workflow has `contents: read`. It checks the exact head and base,
runs 15 integrity and rejection tests, checks the complete release inventory and
proposed tag without reserving either, and builds exactly one asset. It has no
push trigger, manual execution trigger, release mutation, or deployment step.

```sh
python tests/ev_maui_publication_candidate_test.py
python tools/ev_maui_publication_candidate.py --repo-root . \
  --output-dir artifacts/ev-maui-publication-candidate/local-build
```

The builder refuses existing destinations, protected paths, traversal, and symlink
escapes. Without a fresh destination snapshot, it explicitly reports
`remote_collision_check: NOT_REQUESTED`. CI supplies and verifies that snapshot.
Offline success alone is neither remote certification nor publication authority.
