# Texas bounded legislative production deployment validation v0.1

Status: `HOSTED_VALIDATION_COMPLETE__PROOF_FROZEN_AFTER_ACTIVATION`

This gate established the production deployment evidence required for the bounded Texas House District 49 / Senate District 14 representation profile before repository activation.

## Required checks

The deployment-readiness contract requires:

1. `geometry-governance-preflight`;
2. `package-profile-reconstruction`;
3. `positive-both-bindings`;
4. `outside-slice-negative`;
5. `no-partial-projection`;
6. `public-identity-gate`;
7. `hosted-runtime-route`.

The first six were initially exercised in GitHub Actions. The seventh required a genuinely external HTTPS deployment and could not be satisfied by an Actions runner or localhost process.

## Final hosted proof

Provider: Railway.

Endpoint:

`https://texas-bounded-api-production.up.railway.app`

Validated deployed head:

`05e6ca3962c0eb3105e96ef4335423350ea9865b`

Hosted-validation deterministic SHA-256:

`890073c847d9477c1a3c75d4228b5758d76a338954200d597577bc8a73396e37`

All seven required checks passed. The Texas Capitol returned exactly two bounded projections / two AUTHORITATIVE holders. Round Rock City Hall failed closed with zero projections.

The strict deployment evidence object reported:

- `environment=production`;
- `head_sha=05e6ca3962c0eb3105e96ef4335423350ea9865b`;
- `status=PASS`;
- `profile_id=tx_legislative_two_office_v0.1`;
- all seven check IDs at `PASS`.

Deployment-evidence SHA-256:

`226d4649391d8c6c4e7609f541c6e4c5e547e2cdc22d497ca8adca15bf108fca`

That evidence produced readiness receipt SHA-256:

`be8e3435dc07fd8918e80212e60758b08e45ee97bf981fad821d4f2f7d8019d8`

## Post-activation transition

Repository activation was subsequently authorized and executed. The deployment-validation workflow now detects the activated state and verifies `tests/test_texas_activation_execution.py` instead of trying to re-run the old pre-activation candidate gate against a head whose defaults are intentionally active.

The already validated Railway deployment remains pinned to the pre-activation proof head. No Railway redeploy was authorized as part of catalog/registry activation.

Current disposition:

`PRODUCTION_DEPLOYMENT_VALIDATION = PASS_7_OF_7`

`REPOSITORY_ACTIVATION = ACTIVATED_BOUNDED`

`RAILWAY_REDEPLOY = NOT_AUTHORIZED`

`MERGE = NOT_AUTHORIZED`

`RELEASE = NOT_AUTHORIZED`

`CANONICAL_WRITES = 0`
