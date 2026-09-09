# EV-KAUAI-PUBLICATION-CANDIDATE-001

This draft prepares a metadata-only integration manifest for the already merged
Kauaʻi countywide Mayor/Council profile. It does not execute publication or deployment.
The candidate remains subject to separate exact-head merge approval.

## Immutable integration and scope

- Integration target: `a24dd03a9958ffe7bc7a5ba2d0808ef9d1d81eed` (PR #60).
- Integration tree: `71c9f04666fff5789d2d52f41a4284b9570a29bb`, identical to certified
  activation head `c277080bc401b07943d6833def9fb23ecab448ff`.
- Profile: `kauai_countywide_mayor_council_v0.1`; county GEOID `15007`.
- Scope: 2 office rows, 8 seats/current holders, 2 leadership overlays, no divisions.
- Mayor and an unnumbered seven-seat countywide Council only. Prosecuting Attorney,
  Full Essentials, election results, and complete-jurisdiction coverage are excluded.
- Legacy ACTIVE identities and both warnings (unnumbered Council and unresolved exact
  tenure intervals) are preserved. Explicit provisional identities fail closed.

The committed manifest identifies existing package, receipt, spec, catalog, route,
binding, and runtime hashes. It contains no officeholder records or raw package bytes.
Its schema fixes this version's complete metadata contract, including nested values;
adding payload fields or changing authorization flags fails validation.

## Candidate asset contract

| Field | Proposed value |
|---|---|
| Release tag | `kauai-mayor-council-integration-v0.1` |
| Release target | `a24dd03a9958ffe7bc7a5ba2d0808ef9d1d81eed` |
| Sole asset | `kauai-mayor-council-integration-manifest-v0.1.json` |
| Asset type | `application/json` |
| Tag reserved / release created | No |
| Merge / publication / deployment authorized | No / No / No |

The integration target is already known; the candidate's own head is written only
to CI's verification artifact. This avoids a commit containing its own SHA.
The proposed release assets directory contains exactly the manifest. Verification
reports and retained live evidence are not release assets. The manifest's status is
`CANDIDATE_PUBLICATION_HELD`; a later execution decision must explicitly decide the
approved release contract. Nothing in this draft makes a release executable.

## Retained live evidence

The original artifact from activation workflow run `34305859296`, job `102322283047`,
artifact `10086608935` is retained as base64 of its exact original ZIP under
`candidates/ev/kauai_publication.v0.1/evidence/`. Decoding produces 4,905 bytes with
SHA-256 `c3c5be135e146a3a066107b3d72f2c918286e6ac8b548cbd98367bb0653973ef`.
Its only member is `live.json` (65,052 bytes), with SHA-256
`c82480a4511922abfce54dfb0d9cb5804a72abee1731da123ec8aa112c3fec54`.
These bytes match the original GitHub artifact, whose hosted retention expires
October 9, 2026 at 03:07:09 UTC. The repository copy survives that expiry.

The evidence records two Lihue street controls returning the same 2-office/8-holder
projection and a Hilo negative control rejected outside Kauaʻi. Successful negative
geographic resolution and a matched address were asserted by the certified runner;
the artifact itself retains the rejected consumer result, not the raw negative
geography. The new validator checks the original bytes and records this limitation.
It does not relabel synthetic checks as live or claim a new live geocoder run.

## Freshness and delivery holds

Source review remains September 9, 2026 through November 30, 2026 UTC. Validation
fails closed on December 1 UTC, before the local term transition. Neither this
candidate nor artifact retention extends that review. Recheck official incumbency
immediately before any later release decision.

Production eligibility remains true; publication eligibility and complete jurisdiction
remain false. Hawaiʻi, Honolulu, and Maui production holds remain in force; Kalawao
work is excluded. No canonical records, catalog entries, production specs, receipt,
routes, core runtime, service, deployment config, or Texas artifacts are changed.

This is repository integration metadata. Hosted Kauaʻi delivery has not been certified.
The existing Texas container omits the Kauaʻi package/spec/receipt and does not establish
a public Kauaʻi endpoint. No hosted URL or deployment assertion is in the manifest.

## Verification

Run the offline rejection tests and build in a new directory:

```sh
python tests/ev_kauai_publication_candidate_test.py
python tools/ev_kauai_publication_candidate.py --repo-root . \
  --output-dir artifacts/ev-kauai-publication-candidate/local-build
```

The builder refuses existing destinations, canonical paths, traversal, or symlink
escapes. Its only writes are the new candidate artifact directory. Without a supplied
fresh destination snapshot it explicitly reports the remote collision check as
`NOT_REQUESTED`; offline success alone is not remote certification or publication authority.

The read-only PR workflow checks the actual head, the immutable base/tree, clean
tracked files, and the eight allowed candidate paths. It runs rejection controls,
reads the proposed tag and complete release inventory, and builds one manifest asset.
It has no push trigger, workflow dispatch, release mutation, deployment step, or
write permission. Other existing PR lanes retain their own live acceptance checks.
