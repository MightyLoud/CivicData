# Texas bounded Railway deployment v0.1

Status: `PROVIDER_SELECTED_RAILWAY__CONNECTION_REQUIRED`

This contract selects Railway as the first external HTTPS production target for the bounded Texas House 49 / Senate 14 hosted runtime. It does not activate the default Texas catalog/registry route, merge PR #48, or declare `hosted-runtime-route` PASS before an independently reachable production deployment is validated.

## Selected provider

Provider: Railway.

Source repository: `MightyLoud/CivicData`.

Source branch for the Day 12 deployment candidate: `agent/day12-tx-integration`.

Config-as-code: `/railway.toml`.

Dockerfile: `/services/texas_bounded_api/Dockerfile`.

Railway is selected because the service already has a Docker/OCI contract, requires outbound HTTPS access, and needs an independently reachable HTTPS domain plus deployment health gating. No database, volume, background worker, or additional stateful service is required for this bounded API.

## Railway configuration

`railway.toml` declares:

- Dockerfile builder;
- exact custom Dockerfile path;
- `/readyz` as the deployment healthcheck;
- 180-second healthcheck timeout;
- restart on failure with a bounded retry count.

The service listens on Railway's injected `PORT` variable. The HTTP service identity uses `CIVICDATA_SERVICE_HEAD_SHA` when explicitly provided and otherwise falls back to Railway's Git deployment variable `RAILWAY_GIT_COMMIT_SHA`.

## Required production variable

The Railway service must set:

`CIVICDATA_SERVICE_ENVIRONMENT=production`

No manual `CIVICDATA_SERVICE_HEAD_SHA` is required for a GitHub-triggered Railway deployment because the service reads the provider-supplied Git commit SHA. If an explicit head variable is supplied, it remains authoritative and must equal the deployed commit.

## Required deployment shape

The first production service must be a single web service with:

- public HTTPS domain generated or attached by Railway;
- one replica initially;
- no persistent volume;
- no database;
- outbound HTTPS access to the Civic GPS geocoder and governed Texas geometry sources;
- healthcheck `GET /readyz`;
- application process running as the non-root image user;
- exact repository/branch deployment provenance retained by Railway.

## Readiness behavior

A Railway deployment is not accepted merely because the container starts.

`/readyz` must return `200` only after:

- successor package reconstruction succeeds;
- both Person identities remain `AUTHORITATIVE`;
- package/receipt/runtime pins match;
- the default Texas catalog route remains inactive;
- the default Texas legislative registry overlay remains inactive;
- live Texas geometry governance preflight succeeds.

If any check fails, Railway's deployment healthcheck must fail and traffic must not move to that deployment.

## Hosted validation

After Railway provides the external HTTPS URL, run the existing governed validator:

```sh
python tools/texas_hosted_runtime_validation.py \
  --base-url https://<railway-public-domain> \
  --expected-head-sha <exact Railway Git commit SHA> \
  --audit-output artifacts/texas-hosted/railway-audit.json \
  --activation-evidence-output artifacts/texas-hosted/railway-activation-evidence.json
```

The validator must prove all seven deployment checks:

1. `geometry-governance-preflight`;
2. `package-profile-reconstruction`;
3. `positive-both-bindings`;
4. `outside-slice-negative`;
5. `no-partial-projection`;
6. `public-identity-gate`;
7. `hosted-runtime-route`.

Only an independently reachable HTTPS Railway deployment with `environment=production`, exact head identity, exact package/receipt/runtime pins, and all seven checks PASS can supply production deployment evidence to the activation-readiness contract.

## Current boundary

The repository-side Railway deployment contract is implemented. Provider-side creation is not yet executed because the Railway ChatGPT integration is not installed/connected in the current session.

Current disposition:

`RAILWAY_PROVIDER = SELECTED`

`RAILWAY_CONFIG_AS_CODE = IMPLEMENTED`

`RAILWAY_PROVIDER_CONNECTION = REQUIRED`

`PUBLIC_HTTPS_URL = NOT_YET_CREATED`

`HOSTED_RUNTIME_ROUTE = NOT_VALIDATED`

`REPOSITORY_ACTIVATION = NOT_ACTIVATED`
