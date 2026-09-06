# Texas bounded repository activation v0.1

Status: `ACTIVATED_BOUNDED__MERGE_RELEASE_NOT_AUTHORIZED`

The bounded Texas House District 49 + Senate District 14 representation route is activated in the Day 12 branch default package catalog and Civic GPS legislative registry. This activation does not merge PR #48, run a release/publication workflow, widen the Texas scope, or write canonical civic facts.

## Authorized activation

Activation commit: `2d56d3ee1247be470c066df4b4321fd8e4679698`.

Activated package-catalog entry:

- entry: `tx-legislative-two-office-v0.1-hosted-candidate`;
- profile: `state_legislative_representation`;
- production profile: `tx_legislative_two_office_v0.1`;
- catalog-entry SHA-256: `1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189`.

Activated legislative group:

- group: `GEO-TX-LEGISLATIVE-TWO-DISTRICTS`;
- scope: `PRODUCTION_BOUNDED`;
- House binding: `DIST-TX-HOUSE-H2316` / District 49 / `PLANH2316`;
- Senate binding: `DIST-TX-SENATE-S2168` / District 14 / `PLANS2168`;
- geometry policy: `texas-legislative-geometry-governance/0.1`;
- legislative-group SHA-256: `826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a`.

Both default mutations are atomic at the governed state level: partial catalog-only or registry-only activation is invalid and fails CI.

## Production proof used for authorization

The independently hosted Railway service remains pinned to the pre-activation validation head:

`05e6ca3962c0eb3105e96ef4335423350ea9865b`

Public HTTPS endpoint:

`https://texas-bounded-api-production.up.railway.app`

Hosted validation: **7/7 PASS**.

- hosted validation SHA-256: `890073c847d9477c1a3c75d4228b5758d76a338954200d597577bc8a73396e37`;
- readiness receipt SHA-256: `be8e3435dc07fd8918e80212e60758b08e45ee97bf981fad821d4f2f7d8019d8`;
- deployment evidence SHA-256: `226d4649391d8c6c4e7609f541c6e4c5e547e2cdc22d497ca8adca15bf108fca`.

The hosted positive control returned exactly two projections / two AUTHORITATIVE holders for the Texas Capitol. The Round Rock control remained fail-closed with zero projections.

## Package pins

- package JSON: `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`;
- archive: `7b6abf28e0535041797b180488cb98ebf223b844b3081e7386ccbd63c85762b1`;
- acceptance receipt file: `3b204dc1d7c4c9442bf61fe422f3de907dfed0bd567ae15ffa6e853ab5399f96`;
- acceptance deterministic digest: `f58251a3a127841ec1773a342336d01145aca47d61957ea4bfd1e81121266483`.

## Activation receipt

`data/packages/tx/legislative/activation-v0.1.json`

Deterministic SHA-256:

`8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166`

The receipt records `activation_authorized=true` and `repository_activation=ACTIVATED_BOUNDED`, while preserving:

- `merge_authorized=false`;
- `release_authorized=false`;
- `publication_workflow_authorized=false`;
- `railway_redeploy_authorized=false`;
- `canonical_writes=0`.

## Post-activation verification

`tests/test_texas_activation_execution.py` requires the live default catalog entry and registry group to equal the certified objects exactly and verifies their hashes, package reconstruction, authoritative identities, and activation receipt.

Pre-activation readiness tests now use an explicit synthetic inactive-default view. They continue to prove the readiness contract without falsely requiring the live repository to remain inactive after authorization.

The hosted/deployment CI workflows preserve the validated Railway deployment as frozen pre-activation evidence after repository activation; they do not silently redeploy or reinterpret the activated branch as a new hosted candidate.
