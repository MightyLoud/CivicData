# Texas post-activation hosted runtime v0.2

Status: `IMPLEMENTED_PENDING_EXACT_HEAD_HOSTED_VALIDATION`

This phase replaces the historical pre-activation hosted proof runtime with a service that consumes the **activated default** Texas package catalog and Civic GPS legislative registry directly. It does not widen coverage, authorize release/publication, write canonical civic facts, or infer statewide completeness.

## Scope

Profile: `tx_legislative_two_office_v0.1`

Coverage remains exactly:

- Texas House District 49;
- Texas Senate District 14;
- both bindings required atomically;
- representation only;
- `complete_jurisdiction=false`;
- Full Essentials unsupported;
- election scope unsupported.

## Activated-default runtime

`services/texas_bounded_api/runtime_v0_2.py` requires the live repository defaults to contain exactly one certified Texas state-legislative catalog entry and exactly one certified Texas legislative geography group.

Required hashes:

- catalog entry: `1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189`;
- legislative group: `826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a`;
- activation receipt deterministic SHA-256: `8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166`.

The runtime reconstructs the package from the **default catalog**, validates both Persons as `AUTHORITATIVE`, derives the expected production-bounded geography configuration, requires the active default registry group to equal it byte-for-byte at the canonical JSON layer, and then loads Civic GPS with the default extension registry. It does not inject a private candidate catalog or a duplicate legislative overlay.

## Runtime metadata

The service reports:

- `repository_activation=ACTIVATED_BOUNDED`;
- `activation_authorized=true`;
- `release_authorized=false`;
- `publication_workflow_authorized=false`;
- exact package/archive/acceptance/runtime pins;
- exact catalog-entry, legislative-group, and activation-receipt hashes;
- `canonical_writes=0`.

A successful bounded representation may still return `publication_eligible=true` for the two-binding representation result. That field is the consumer's bounded representation eligibility and is **not** a repository release authorization or a publication-workflow authorization.

## Readiness

`GET /readyz` returns `200` only after all of the following are proven:

- activation receipt is valid;
- default activated catalog entry is exact;
- default activated registry group is exact;
- successor package reconstructs through the production profile;
- both Person identities remain authoritative;
- live Texas geometry version governance passes before geocoding.

## Hosted validation

`tools/texas_post_activation_hosted_validation.py` validates an independently reachable HTTPS deployment and requires ten checks:

1. `activation-receipt`;
2. `activated-default-catalog`;
3. `activated-default-registry`;
4. `geometry-governance-preflight`;
5. `package-profile-reconstruction`;
6. `positive-both-bindings`;
7. `outside-slice-negative`;
8. `no-partial-projection`;
9. `public-identity-gate`;
10. `hosted-runtime-route`.

The positive control remains Texas Capitol, `1100 Congress Ave, Austin, TX 78701`, requiring two projections and two authoritative holders. The negative control remains Round Rock City Hall, `221 E Main St, Round Rock, TX 78664`, requiring fail-closed behavior with zero partial projections.

The hosted evidence is schema `texas-post-activation-hosted-evidence/0.1`. It remains release-neutral: `release_authorized=false`, `publication_workflow_authorized=false`, and `canonical_writes=0`.

## Deployment boundary

The first v0.2 deployment is a governed validation deployment. Replacing the currently hosted pre-activation proof service is authorized only for this post-activation validation phase; it does not itself create a GitHub Release or authorize a publication workflow.

The exact deployed Git SHA must be preserved by Railway and independently rechecked through the public HTTPS route.
