# CivicData hosting recovery assessment — 2026-10-09

Disposition: **preserve the currently offline configuration; no billable recovery or migration executed**.

## Verified state

- Repository main inspected at `6477c83484702c8f703ee1dee53bd4bea414cb0e`.
- Railway project `0c9a13e7-cbac-4b2c-98e6-5e1167dd03e3`, production environment `d26e584b-b24b-4b03-ad26-e38d30e379c4`.
- `environment-status` reports `texas-bounded-api`, `texas-hosted-validator`, and `atlas-address-resolver` offline, with no active deployments and no staged/applying work. No volumes or buckets exist in this environment.
- Direct HTTPS GETs to `https://texas-bounded-api-production.up.railway.app/healthz` and `/readyz` returned HTTP 404 with Railway edge body `Application not found`. The Atlas domain's `/healthz` probe returned the same response. These are edge failures, not the application's fail-closed HTTP 503 response.
- API deployment `92d0ec2f-948c-46bd-9c6d-83f9ac7cdf55`, source SHA `bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67`, passed its `/readyz` build gate on September 6. Logs record `Stopping Container` at `2026-10-07T21:04:41.695465359Z` followed by orderly Uvicorn shutdown. Deployment history marks it `REMOVED`.
- The October 7 expiration email (`1a11838602c26e94`) is timestamped `21:04:39Z`. The timing strongly supports trial-related removal; an explicit billing/removal reason was not available.
- The inventory's `latestDeployment` points to an older September 6 failed build. It is misleading as a standalone current-state indicator: use deployment history plus runtime status and public probes.
- The API source config remains pinned to branch `agent/day12-tx-post-activation-runtime-v0.2` and the SHA above. It differs from current main. Existing config has `/readyz`, a 300-second window and one replica; repository config specifies 180 seconds and ten failure restarts. Preserve the readiness gate and inspect effective config before recovery.
- Current paid plan, card state, balance, and any subsequent upgrade are **unverified**. Available Railway connector tools do not expose billing. The browser project page requires login. No login, upgrade, redeploy or variable-value retrieval was performed.
- No alternate host was found in the inspected repository deployment documents. That does not exclude an undocumented host.
- The Travis County smoke failure is a separate upstream GIS timeout; no causal link to Railway has been established.

## Deployment and dependency contract

Use the repository root as Docker context, with `services/texas_bounded_api/Dockerfile`. Python 3.12, FastAPI, Uvicorn and requests are used. The service runs as non-root, binds `0.0.0.0`, honors `PORT`, and starts one worker. Runtime parts are SHA-256 verified during build; package, catalog, registry, acceptance and activation pins remain mandatory at readiness.

`/healthz` checks service metadata, including a valid 40-character Git SHA. `/readyz` builds the governed runtime on its first call and caches that runtime; it is not proof that every upstream is continuously reachable. Representation requests still enforce fail-closed behavior. Readiness startup can involve outbound governed geometry checks; do not replace it with liveness to force a deployment through.

Outbound HTTPS is required for geocoding and ArcGIS district data, including Texas House and Senate FeatureServer layers in `civic_gps_extensions/texas_geometry_governance.py`. Upstream availability remains an independent risk on every host. No database or persistent disk is required by this bounded container. Do not assume the separate Atlas image-based service is reproducible from this Dockerfile or required by it; inventory its source and consumer dependencies before restoring it.

Required non-secret environment metadata: `CIVICDATA_SERVICE_ENVIRONMENT=production` and an exact SHA from `RAILWAY_GIT_COMMIT_SHA` or explicit `CIVICDATA_SERVICE_HEAD_SHA`. A different provider must supply the explicit SHA matching its built code. Do not set a fixed SHA that survives later source changes. Store any future API keys only in provider secret variables; do not copy secrets into source, build arguments, audit output or reports. `.dockerignore` now excludes common local environment files, credential directories and development state without excluding governed package inputs; it is not a complete secret scanner.

## Options

| Option | Recurring cost | Complexity and compatibility | Main risk / roadmap effect |
| --- | --- | --- | --- |
| Preserve offline setup now | No new hosting spend authorized or initiated; existing billing obligations remain unverified | Lowest immediate complexity; retain domains, exact source SHA, config and receipts | Live consumers and public HTTPS validation remain blocked; dataset normalization, QA and deterministic API development can continue |
| Restore on Railway | Hobby minimum $5/month includes $5 resource usage; usage above it is extra. Free plan advertises $1 monthly credit, but account eligibility and adequacy are unverified | Lowest restoration complexity; existing URL, Docker contract, variables and history remain | Spend needs approval and a hard usage limit; rebuild required for this API because rollback is unavailable; do not blindly deploy main |
| Move to Render | Free web service available with quota limits; paid compute and bandwidth separately priced, verify selected current tier before purchase | Existing Dockerfile is portable; new provider setup, explicit SHA metadata, secret inventory, new URL and validation required | Free service sleeps after 15 idle minutes and cold starts can take about a minute. HTTP probes require response within 5 seconds: first-call readiness latency needs testing. Migration does not solve GIS timeouts |

Pricing and provider references checked October 9:

- https://docs.railway.com/pricing/plans
- https://docs.railway.com/pricing/free-trial (current docs describe automatic reversion to Free; this does not prove the account's current plan)
- https://docs.railway.com/pricing/cost-control
- https://render.com/docs/free
- https://render.com/docs/web-services
- https://render.com/docs/health-checks
- https://render.com/docs/rollbacks

## Recommended recovery sequence

1. Keep the current offline resources intact. Do not delete domains, services, source branches or historic receipts. Correct current-status documentation without rewriting historical validation evidence.
2. Verify the Railway workspace's current subscription and billing outside this unauthenticated browser session. Obtain a spending ceiling before any paid upgrade or rebuild. Confirm Free-plan egress and memory suitability if considering zero-cost recovery; the advertised credit is not an always-on guarantee.
3. Before rebuilding, verify the retained source commit is fetchable, retain config and environment-variable names without exposing values, and run the existing container and deterministic gates on the proposed exact commit. Treat current main as a new candidate requiring fresh validation.
4. Restore only the bounded API first if no confirmed consumer requires Atlas. Run the validator as a one-shot local/CI task rather than an always-on service where its actual role supports that. Do not delete either auxiliary service based on its name alone.
5. On Railway, preserve `/readyz`, non-root execution, single-worker behavior, hash pins and failure restarts. Require matching deployed SHA and production metadata from public `/healthz` and `/readyz` responses.
6. Execute the existing independent hosted validation:

```sh
python tools/texas_post_activation_hosted_validation.py \
  --base-url https://texas-bounded-api-production.up.railway.app \
  --expected-head-sha <EXACT_DEPLOYED_SHA> \
  --audit-output artifacts/texas-post-activation/audit.json \
  --release-evidence-output artifacts/texas-post-activation/release-evidence.json
```

Require all ten checks, Texas Capitol's two authoritative projections, and Round Rock's fail-closed negative result. Updating a health probe alone is not completion. Do not widen bounded Texas coverage or authorize publication through hosting recovery.

7. Rollback plan: API history reports `canRollback=false`, `canRedeploy=true`; preserve the exact source and rebuild recipe rather than promising instant rollback from an expired image. The older pre-activation proof commit is a distinct contract, not an interchangeable v0.2 fallback. Keep external access paused if validation fails.
8. If migration becomes necessary, deploy to a new candidate URL, preserve Railway resources, validate the exact image/SHA and both controls, then update consumer base URLs only after acceptance. Revert those URLs if a regression occurs. Confirm Render's probe latency and memory limits first.

The national dataset roadmap should separate hosting readiness from data completion. This deployment proves only the bounded House 49 / Senate 14 profile; it does not expose nationwide coverage or Full Essentials. Keep RAW, normalized data, QA, parity and tracker completion independent of public-host restoration.

## Changes and validation

This draft adds a Docker build-context safeguard and marks the historical Railway document as historical/offline. No live Railway configuration, billing, secrets, deployment safeguards or source pin was changed. Existing Railway contract tests passed (2/2). Docker is unavailable in the execution environment, so image build, startup, upstream readiness and independent hosted validation have not been run. They remain mandatory before restoration.
