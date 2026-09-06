# Texas bounded legislative production deployment validation v0.1

Status: `EXACT_HEAD_VALIDATION_IMPLEMENTED_HOSTED_ROUTE_REQUIRED`

This gate executes the issued House 49 / Senate 14 successor package through the real production-bounded Civic GPS geography contract and the proposed governed production-profile route without activating the default catalog or registry.

## Purpose

The deployment-readiness contract requires seven exact-head checks:

1. `geometry-governance-preflight`;
2. `package-profile-reconstruction`;
3. `positive-both-bindings`;
4. `outside-slice-negative`;
5. `no-partial-projection`;
6. `public-identity-gate`;
7. `hosted-runtime-route`.

GitHub Actions can directly establish the first six against current code, current package bytes, current live geometry markers, and live address resolution. It cannot establish the seventh merely by executing a runner. An Actions runner is an ephemeral validation environment, not a hosted production route.

## Exact-head candidate execution

`tools/texas_production_deployment_validation.py` binds its report to the exact 40-character `GITHUB_SHA` and performs the following without changing defaults:

- reconstructs the committed successor archive from its base64 parts;
- verifies the archive and `jurisdiction.json` hashes;
- verifies the committed `texas-bounded-acceptance/0.1` successor receipt;
- loads the package through `tx_legislative_two_office_v0.1`;
- requires both Persons to remain explicit `AUTHORITATIVE`;
- builds the exact `PRODUCTION_BOUNDED` House/Senate geography group;
- loads the resolver, which runs the live Texas geometry-version governance preflight before geocoding;
- resolves the Texas Capitol at `1100 Congress Ave, Austin, TX 78701` and requires exactly two public bounded projections, two authoritative holders, `publication_eligible=true`, `complete_jurisdiction=false`, and zero canonical writes;
- resolves Round Rock City Hall at `221 E Main St, Round Rock, TX 78664` and requires fail-closed outside-slice behavior with zero partial projections.

The live addresses are controls for the bounded route. They do not change package coverage or establish statewide completeness.

## Hosted-route boundary

The connected Civic repositories currently contain no deployable HTTP service entry point, hosting configuration, production deployment workflow, or independently identifiable hosted Civic GPS endpoint for this route.

Therefore the validator must record:

`hosted-runtime-route = BLOCKED`

with blocker:

`NO_HOSTED_PRODUCTION_RUNTIME_TARGET_CONFIGURED`

when the six executable checks pass but no real production route exists.

The validator must not relabel GitHub Actions, a localhost server, a unit test, or a synthetic session as hosted production evidence.

## Disposition semantics

If any of the first six checks fails, the validation report is `FAIL` and CI fails.

If the first six checks pass and the hosted route is unavailable, the report is:

`BLOCKED_HOSTED_RUNTIME_ROUTE`

The workflow itself may complete successfully because it correctly enforced the expected fail-closed boundary. That workflow success is not production deployment success.

Only an independently deployed production route can support a future strict deployment evidence object with:

- `environment=production`;
- exact candidate `head_sha`;
- `status=PASS`;
- all seven required check IDs at `PASS`.

Only that strict object can satisfy `tools/texas_activation_readiness.py` and permit a `READY_TO_ACTIVATE` readiness receipt. Even then, activation remains a separate explicit decision.

## Artifact

The `Texas production deployment validation` workflow uploads the exact-head JSON report as a GitHub Actions artifact. The report carries:

- candidate head SHA;
- observation date;
- successor package and receipt pins;
- status for all seven deployment checks;
- per-check details;
- `activation_authorized=false`;
- `repository_activation=NOT_ACTIVATED`;
- `canonical_writes=0`;
- deterministic report SHA-256.

No default catalog entry, registry overlay, merge, release, publication, or deployment is created by this workflow.
