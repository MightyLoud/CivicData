# Texas bounded hosted runtime v0.1

Status: `DEPLOYABLE_SERVICE_IMPLEMENTED_NOT_HOSTED`

This contract adds a deployable HTTP service for the bounded Texas House 49 / Senate 14 representation profile. It does not add the Texas profile to the default package catalog or Civic GPS registry, deploy to a public URL, merge PR #48, or authorize activation.

## Service surface

Service ID: `civicdata-tx-legislative-two-office-v0.1`

Profile: `tx_legislative_two_office_v0.1`

Routes:

- `GET /healthz` — process/configuration liveness; does not perform a live geography request.
- `GET /readyz` — reconstructs the exact successor package, verifies the authoritative Person identity state, proves the default Texas route is still inactive, and performs the production-bounded Texas geometry-governance preflight before returning ready.
- `GET /v1/representation?address=...` — resolves the address through the production-bounded Texas geography group and then routes both House 49 and Senate 14 through the governed bounded package/profile. The two bindings remain atomic; an outside-slice or incomplete geography result returns fail-closed with no partial projection.

The service returns deployment provenance with each readiness/representation response, including the deployed Git head, profile ID, successor package/archive/receipt hashes, Civic GPS runtime hash, production geography-group hash, activation state, and canonical-write count.

## Canonical package pins

The service contract is pinned to the already issued successor artifact:

- `jurisdiction.json`: `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`;
- package archive: `7b6abf28e0535041797b180488cb98ebf223b844b3081e7386ccbd63c85762b1`;
- acceptance receipt file: `3b204dc1d7c4c9442bf61fe422f3de907dfed0bd567ae15ffa6e853ab5399f96`;
- acceptance deterministic digest: `f58251a3a127841ec1773a342336d01145aca47d61957ea4bfd1e81121266483`;
- Civic GPS runtime: `1969e0e6760bdf4e479bd01fa6976f2ea25dd5fdc14e53d0f4b861cde97549ba`.

The service refuses to become ready if these pins drift or if either default repository route has already been activated unexpectedly.

## Container contract

`services/texas_bounded_api/Dockerfile` builds an OCI-compatible image from the repository root. The image:

- uses Python 3.12;
- reconstructs the exact pinned Civic GPS runtime during build and checks its SHA-256;
- installs the bounded service dependencies;
- copies only the governed runtime/package code and data needed by the service;
- runs as a non-root user;
- exposes port `8080`;
- includes a liveness health check.

Production deployment must set:

- `CIVICDATA_SERVICE_HEAD_SHA` to the exact 40-character Git commit deployed;
- `CIVICDATA_SERVICE_ENVIRONMENT=production`.

A hosted base URL is intentionally not committed because the repository currently has no governed production target/account. A real deployment target must supply TLS and outbound HTTPS access for the Civic GPS geocoder and governed Texas geometry sources.

## Candidate vs production

A container running in CI is a deployment candidate, not a hosted production service. Container smoke tests may use `CIVICDATA_SERVICE_ENVIRONMENT=container-ci`, but that can never satisfy `hosted-runtime-route`.

Production evidence requires an independently reachable **HTTPS** base URL whose service metadata reports:

- `environment=production`;
- the exact expected deployed head SHA;
- the pinned successor package/archive/receipt/runtime hashes;
- `repository_activation=NOT_ACTIVATED`;
- `activation_authorized=false`;
- `canonical_writes=0`.

The hosted validator rejects HTTP, localhost, loopback, private, link-local, and reserved literal IP targets.

## Hosted validation

After an image is deployed to an independently hosted HTTPS endpoint, run:

```sh
python tools/texas_hosted_runtime_validation.py \
  --base-url https://<host> \
  --expected-head-sha <exact-deployed-40-char-sha> \
  --audit-output artifacts/texas-hosted/audit.json \
  --activation-evidence-output artifacts/texas-hosted/activation-evidence.json
```

The validator performs all seven activation-readiness deployment checks:

1. `geometry-governance-preflight`;
2. `package-profile-reconstruction`;
3. `positive-both-bindings`;
4. `outside-slice-negative`;
5. `no-partial-projection`;
6. `public-identity-gate`;
7. `hosted-runtime-route`.

The positive live control is the Texas Capitol. It must return exactly two bounded projections, two AUTHORITATIVE holders, current-service start `2025-01-14`, unknown actual ends, `publication_eligible=true`, `complete_jurisdiction=false`, and zero canonical writes.

The negative live control is Round Rock City Hall. It must fail closed and return no `projections` field.

A successful hosted validator writes the exact minimal deployment-evidence object already required by `tools/texas_activation_readiness.py`: `environment=production`, exact head SHA, `status=PASS`, the bounded profile ID, and all seven checks PASS.

## Activation boundary

This service implementation is not default-route activation. Current governed state remains:

`HOSTED_SERVICE_IMPLEMENTATION = COMPLETE`

`HOSTED_PRODUCTION_URL = NOT_CONFIGURED`

`HOSTED_RUNTIME_ROUTE = NOT_VALIDATED`

`ACTIVATION_READINESS = BLOCKED_HOSTED_RUNTIME_ROUTE`

`REPOSITORY_ACTIVATION = NOT_ACTIVATED`

A later production deployment must be independently hosted and validated before a `READY_TO_ACTIVATE` receipt can be issued. Catalog/registry activation and merge/release remain separate explicit decisions.
