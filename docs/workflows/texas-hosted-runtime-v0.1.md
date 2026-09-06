# Texas bounded hosted runtime v0.1

Status: `HOSTED_PROOF_VALIDATED__REPOSITORY_ACTIVATED_BOUNDED`

This contract defines the deployable HTTP service used to validate the bounded Texas House District 49 / Senate District 14 representation profile. The hosted service supplied the independent production proof required before repository activation. Repository activation is now complete on the Day 12 branch; merge and release remain separate.

## Service surface

Service ID: `civicdata-tx-legislative-two-office-v0.1`

Profile: `tx_legislative_two_office_v0.1`

Routes:

- `GET /healthz` — liveness and deployed-head metadata.
- `GET /readyz` — successor-package reconstruction, authoritative identity checks, package/receipt/runtime pins, and Texas geometry-governance preflight.
- `GET /v1/representation?address=...` — atomic House 49 + Senate 14 bounded representation. Outside-slice or incomplete geography fails closed without a partial projection.

## Validated production deployment

Provider: Railway.

Public HTTPS endpoint:

`https://texas-bounded-api-production.up.railway.app`

The independent production proof is intentionally frozen at the pre-activation deployed head:

`05e6ca3962c0eb3105e96ef4335423350ea9865b`

That deployment passed all seven governed checks:

1. `geometry-governance-preflight`;
2. `package-profile-reconstruction`;
3. `positive-both-bindings`;
4. `outside-slice-negative`;
5. `no-partial-projection`;
6. `public-identity-gate`;
7. `hosted-runtime-route`.

Hosted-validation deterministic SHA-256:

`890073c847d9477c1a3c75d4228b5758d76a338954200d597577bc8a73396e37`

The Texas Capitol returned exactly two bounded projections / two AUTHORITATIVE holders. Round Rock City Hall failed closed with zero projections.

## Canonical package pins

- `jurisdiction.json`: `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`;
- package archive: `7b6abf28e0535041797b180488cb98ebf223b844b3081e7386ccbd63c85762b1`;
- acceptance receipt file: `3b204dc1d7c4c9442bf61fe422f3de907dfed0bd567ae15ffa6e853ab5399f96`;
- acceptance deterministic digest: `f58251a3a127841ec1773a342336d01145aca47d61957ea4bfd1e81121266483`;
- Civic GPS runtime: `1969e0e6760bdf4e479bd01fa6976f2ea25dd5fdc14e53d0f4b861cde97549ba`.

## Activation transition

The hosted service was designed as a pre-activation proof environment and therefore treated the default Texas catalog/registry being inactive as a readiness invariant. After the explicit repository-activation decision, the Railway deployment remains pinned to the validated pre-activation commit and is not silently redeployed from the activated branch.

Post-activation repository state is governed separately by `tests/test_texas_activation_execution.py` and `docs/workflows/texas-activation-execution-v0.1.md`.

Current disposition:

`HOSTED_PRODUCTION_DEPLOYMENT = VALIDATED_7_OF_7`

`HOSTED_PROOF_HEAD = 05e6ca3962c0eb3105e96ef4335423350ea9865b`

`REPOSITORY_ACTIVATION = ACTIVATED_BOUNDED`

`RAILWAY_REDEPLOY = NOT_AUTHORIZED`

`MERGE = NOT_AUTHORIZED`

`RELEASE = NOT_AUTHORIZED`

`CANONICAL_WRITES = 0`
