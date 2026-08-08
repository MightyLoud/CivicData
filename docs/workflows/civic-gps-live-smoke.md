# Civic GPS live-smoke release gate

## Purpose

The Civic GPS live-smoke workflow is the formal release and source-drift gate for Civic GPS. It now protects both the packaged resolver and the deterministic County Onboarding Pipeline. A relevant change is not release-ready until the offline onboarding fixtures pass **and** the maintained real-address, negative, action-selection, and exact-boundary controls pass. The same workflow runs weekly so upstream drift is detected after release as well as before it.

## Gate contract

The workflow must pass before a Civic GPS runtime/configuration or county-onboarding automation change is promoted to `main`.

The runner reconstructs the exact packaged runtime from repository chunks and verifies its SHA-256 before execution.

Current pinned runtime SHA-256:

`567c809839a2bcbafff7da432e28bf7e6fa23e5c2dff9639cf11ad4f87759d60`

Current contract set:

- Overlay Engine: `v0.6.1`
- Adapter registry artifact: `v0.5.5`
- Adapter registry schema: `civic-gps-adapter-registry/0.2.0`
- Consumer response schema: `civic-gps-response/0.3.0`
- County onboarding frozen-spec schema: `civic-gps-county-onboarding/0.1.0`

## Deterministic county-onboarding controls

Before any networked smoke tests, the gate runs the offline County Onboarding Pipeline fixtures:

- Williamson County must classify `SUPPORTED_V0_1 / NONE`, produce deterministic builder/release/bundle previews, and preserve `ADAPTER` failure scope, `CANONICAL_RELEASE_ONLY` identity, and the fail-closed boundary policy.
- Hays County must classify `MULTI_OFFICE_PER_DISTRICT` and must not emit a builder spec, release preview, or bundle preview.
- All seven named STOP classes must have executable deterministic detectors.
- Running the same frozen Williamson spec twice must produce byte-identical JSON outputs.

These tests are intentionally offline. They validate the frozen-spec contract; later CG gates validate live sources.

## Maintained network controls

### Baseline

1. Tacoma/Pierce — `747 Market Street, Tacoma, WA 98402`: Tacoma Council 2 + Pierce Council 4; 11 applicable offices.
2. Denver + RTD — `1437 Bannock Street, Denver, CO 80202`: Denver Council 10 + RTD A; 7 offices; 23 actions.
3. Boulder + RTD — `1777 Broadway, Boulder, CO 80302`: RTD O only; 1 office.
4. Colorado Springs D11 — `1115 N El Paso St, Colorado Springs, CO 80903`: 7 at-large Board offices; 17 actions.
5. Harrison outside-D11 — `2755 Janitell Road, Colorado Springs, CO 80906`: 0 D11 offices/actions.

### Denton County

Denton remains release-backed for geography, office applicability, and action routing. Two real interiors, a Dallas outside negative, Commissioner boundary, shared JP/Constable boundary, and the deterministic 27-route action-selection contract must all pass. Normal Denton interiors return 9 applicable offices and 14 Denton action links. Boundary conflicts suppress only ambiguous district routes/offices and never tie-break.

### Collin County

Collin is the first production output of `TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1`. Three interiors, a Dallas outside negative, Commissioner boundary, and shared JP/Constable boundary must pass. Normal interiors return 9 offices = 6 countywide + Commissioner + JP + Constable. Collin actions remain `NOT_YET_RELEASED`.

### Travis County

Travis is the second production output of the county archetype. Five interiors cover all four Commissioner precincts and all five shared JP/Constable precincts, plus a Dallas outside negative and both boundary classes. Normal interiors return 9 offices. Additional countywide offices remain `BOUNDED_V0_1_SCOPE`; Travis actions remain `NOT_YET_RELEASED`.

### Williamson County

Williamson is the third production output of the county archetype and the first county completed through County Onboarding Pipeline v0.1.

Required packaged controls:

- P1 — `1801 E Old Settlers Boulevard, Round Rock, TX 78664` → Commissioner/JP/Constable 1.
- P2 — `350 Discovery Boulevard, Cedar Park, TX 78613` → Commissioner/JP/Constable 2.
- P3 — `405 Martin Luther King Street, Georgetown, TX 78626` → Commissioner/JP/Constable 3.
- P4 — `3001 Joe DiMaggio Boulevard, Round Rock, TX 78665` → Commissioner/JP/Constable 4.
- Outside negative — `700 Lavaca Street, Austin, TX 78701` must activate Travis normally while contributing 0 Williamson jurisdiction, assignments, offices, actions, or coverage.
- Shared exact boundary — live official Williamson County geometry must produce multiple `PCT_NUMBER` intersections; Commissioner, JP, and Constable assignments must all suppress together at the exact point, preserving only the 6 countywide Williamson offices. Points immediately on opposite sides must each resolve all three district families to one precinct and restore 9 offices.

Williamson release scope is 18 offices = 6 deliberately bounded countywide + 4 Commissioner + 4 JP + 4 Constable. Williamson action routing remains `NOT_YET_RELEASED`; additional countywide elected offices remain `BOUNDED_V0_1_SCOPE`.

### Tarrant County

Tarrant is the fourth production output of the county archetype and the second county completed through County Onboarding Pipeline v0.1.

Required packaged controls:

- Eight permanent interiors cover JP/Constable keys 1–8 and all Commissioner keys 1–4; each returns 9 offices = 6 countywide + Commissioner + JP + Constable.
- Outside negative — `700 Lavaca Street, Austin, TX 78701` must activate Travis normally while contributing 0 Tarrant jurisdiction, assignments, offices, actions, or coverage.
- Commissioner exact boundary — live official geometry must suppress only Commissioner while preserving the independently resolved JP and Constable assignments; both sides restore 9 offices.
- Shared JP/Constable exact boundary — live official geometry must suppress JP and Constable together while preserving the independently resolved Commissioner assignment; both sides restore 9 offices.

Tarrant release scope is 26 offices / 26 holders = 6 deliberately bounded countywide + 4 Commissioner + 8 JP + 8 Constable. Tarrant action routing remains `NOT_YET_RELEASED`; additional countywide elected offices remain `BOUNDED_V0_1_SCOPE`. Boundary conflicts remain `MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK`.

## Triggers

The gate runs:

- on pull requests to `main` that change Civic GPS runtime, maintained tests, onboarding tool/schema/fixtures, dependencies, workflow, or gate documentation;
- on relevant pushes to `main`;
- manually through `workflow_dispatch`;
- weekly on Wednesday at 15:23 UTC.

The required status context is exactly `Civic GPS release gate`.

## Evidence

Every run uploads deterministic county-onboarding outputs plus generated live-response evidence for the baseline and county-specific proof directories. Failed runs still upload whatever evidence was produced before failure.

## Failure handling

A failed control is a release blocker until classified. Do not silently change expected values to make the gate green.

Classify failures as one of:

- **UPSTREAM_DRIFT** — source geography, roster, action route, or API response changed;
- **ENGINE_REGRESSION** — upstream evidence is valid but resolver behavior changed incorrectly;
- **RUNTIME_INTEGRITY** — packaged runtime SHA or reconstruction failed;
- **TRANSIENT_UPSTREAM_FAILURE** — temporary network/provider failure, confirmed by an unchanged clean rerun.

For upstream drift, capture the artifact, verify the authoritative source, update canonical release/config deliberately, rerun regressions, and require this gate to pass again.

For an onboarding-fixture failure, fix the frozen-spec/tool contract. Do not loosen a STOP condition merely to make the fixture green.

## Promotion history

- Initial five-control network baseline: run `31224765817`.
- Denton geography/office release: PR #5; post-merge run `31240231410`.
- Denton action routing: PR #6; post-merge run `31241061355`.
- Collin reusable-archetype release: PR #7.
- Travis reusable-archetype release: PR #8; post-merge run `31243494442`.
- Williamson release: PR #10; protected PR run `31246989220`; post-merge run `31247035390`; runtime SHA `52e60a83b42c65cd03bf81c3169c54c86d8c7750686d5d827838ec636b4e26de`.
- Tarrant pre-promotion package: run `31274189655`; full packaged regression: run `31274416507`; candidate runtime SHA `567c809839a2bcbafff7da432e28bf7e6fa23e5c2dff9639cf11ad4f87759d60`.
