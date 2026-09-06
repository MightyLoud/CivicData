# Texas bounded Railway deployment v0.1

Status: `DEPLOYED_AND_VALIDATED__FROZEN_PREACTIVATION_PROOF`

Railway is the governed external HTTPS production target used to validate the bounded Texas House District 49 / Senate District 14 hosted runtime. Provider connection, project creation, service creation, public HTTPS exposure, exact-head deployment, and hosted validation are complete.

## Railway resources

Project: `CivicData Texas Hosted Runtime`

Project ID: `0c9a13e7-cbac-4b2c-98e6-5e1167dd03e3`

Production environment ID: `d26e584b-b24b-4b03-ad26-e38d30e379c4`

API service ID: `a5af748d-d2f8-4e25-8d9b-fc2eea9f4c96`

Public domain:

`https://texas-bounded-api-production.up.railway.app`

Source repository: `MightyLoud/CivicData`.

Source branch: `agent/day12-tx-integration`.

Validated deployed commit:

`05e6ca3962c0eb3105e96ef4335423350ea9865b`

Successful Railway deployment ID:

`cbdbf58e-3a07-42e5-9ccf-387021a033b9`

## Deployment contract

The production service uses:

- Dockerfile `services/texas_bounded_api/Dockerfile`;
- Railway-injected `PORT`;
- Railway Git commit provenance;
- `CIVICDATA_SERVICE_ENVIRONMENT=production`;
- `/readyz` as the deployment health gate;
- a single initial replica;
- no database or persistent volume;
- outbound HTTPS access to governed Civic GPS/geometry sources.

The container runs as a non-root user.

## Hosted production validation

The public Railway route passed all seven required checks:

1. `geometry-governance-preflight`;
2. `package-profile-reconstruction`;
3. `positive-both-bindings`;
4. `outside-slice-negative`;
5. `no-partial-projection`;
6. `public-identity-gate`;
7. `hosted-runtime-route`.

Hosted-validation SHA-256:

`890073c847d9477c1a3c75d4228b5758d76a338954200d597577bc8a73396e37`

Activation-readiness receipt SHA-256:

`be8e3435dc07fd8918e80212e60758b08e45ee97bf981fad821d4f2f7d8019d8`

The Texas Capitol positive control returned exactly two projections / two AUTHORITATIVE holders. The Round Rock negative control remained fail-closed with zero projections.

## Post-activation boundary

Repository catalog + registry activation was subsequently authorized and executed on the Day 12 branch. The Railway service remains intentionally pinned to the validated pre-activation commit because that service's `/readyz` contract included proof that the default repository route was not yet active.

A post-activation Railway redeploy is **not** implied by repository activation and has not been authorized.

Current disposition:

`RAILWAY_PROVIDER = CONNECTED`

`PUBLIC_HTTPS_URL = LIVE`

`HOSTED_RUNTIME_ROUTE = PASS`

`REPOSITORY_ACTIVATION = ACTIVATED_BOUNDED`

`RAILWAY_REDEPLOY = NOT_AUTHORIZED`

`MERGE = NOT_AUTHORIZED`

`RELEASE = NOT_AUTHORIZED`
