# Civic GPS live-smoke release gate

## Purpose

The Civic GPS live-smoke workflow is the formal networked release and source-drift gate for the packaged Civic GPS resolver.

A Civic GPS runtime/configuration change is not release-ready until the workflow passes against the maintained real-address and boundary controls. The same workflow runs on a weekly schedule so upstream geography/API drift is detected after release as well as before it.

## Gate contract

The workflow must pass before a Civic GPS runtime/configuration change is promoted to `main`.

The runner reconstructs the exact packaged runtime from repository chunks and verifies its SHA-256 before unzipping or executing it. This prevents a partial or altered runtime from being mistaken for a successful release candidate.

Current pinned runtime SHA-256:

`66f876c59809849b36ab837e942ac2465e2c32936cf44f1cbe8aa65795ee04c7`

Current engine/contract set:

- Overlay Engine: `v0.6.0`
- Adapter registry artifact: `v0.5.0`
- Adapter registry schema: `civic-gps-adapter-registry/0.2.0`
- Consumer response schema: `civic-gps-response/0.3.0`

## Baseline live controls

1. **Tacoma/Pierce** — `747 Market Street, Tacoma, WA 98402`
   - Tacoma Council District 2
   - Pierce County Council District 4
   - 11 applicable offices

2. **Denver + RTD** — `1437 Bannock Street, Denver, CO 80202`
   - Denver Council District 10
   - RTD Director District A
   - 7 applicable offices
   - 23 actions

3. **Boulder + RTD** — `1777 Broadway, Boulder, CO 80302`
   - RTD Director District O
   - Denver must not activate
   - 1 applicable office

4. **Colorado Springs School District 11** — `1115 N El Paso St, Colorado Springs, CO 80903`
   - Census Unified School District GEOID `0803060`
   - 7 applicable at-large Board offices
   - 17 actions

5. **Harrison School District 2 negative control** — `2755 Janitell Road, Colorado Springs, CO 80906`
   - D11 must not activate
   - 0 D11 applicable offices
   - 0 D11 actions

## Denton County packaged controls

6. **Denton / Frisco** — `5533 FM 423, Frisco, TX 75036`
   - Commissioner Precinct 2
   - Justice of the Peace Precinct 2
   - Constable Precinct 2
   - 9 applicable Denton offices

7. **Denton / Flower Mound** — `6200 Canyon Falls Drive, Flower Mound, TX 76226`
   - Commissioner Precinct 4
   - Justice of the Peace Precinct 4
   - Constable Precinct 4
   - 9 applicable Denton offices

8. **Dallas outside-Denton negative** — `1500 Marilla Street, Dallas, TX 75201`
   - Denton must not activate
   - 0 Denton assignments, applicable offices, or actions

9. **Denton Commissioner boundary**
   - Exact current official shared boundary must return Commissioner `CONFLICT` and no Commissioner assignment.
   - Denton BASE plus the unambiguous JP/Constable assignments must survive.
   - Points on opposite sides must resolve to distinct Commissioner precincts.

10. **Denton JP / Constable shared boundary**
    - Exact current official shared boundary must return both JP and Constable `CONFLICT` with neither assignment guessed.
    - Denton BASE plus the unambiguous Commissioner assignment must survive.
    - Points on opposite sides must resolve to distinct JP/Constable precincts.

Denton action routing is not yet released. The runtime must expose that as `NOT_YET_RELEASED`; zero Denton action links are not interpreted as action-routing completeness.

## Triggers

The gate runs:

- on pull requests to `main` that change Civic GPS runtime, smoke-test, dependency, workflow, or gate-documentation paths;
- on relevant pushes to `main`;
- manually through `workflow_dispatch`;
- weekly on Wednesday at 15:23 UTC.

## Evidence

Every run uploads the live Civic GPS responses and summaries as a GitHub Actions artifact retained for 30 days. Failed runs still upload whatever evidence was produced before failure.

## Failure handling

A failed live control is a release blocker until classified. Do not silently change expected values to make the gate green.

Classify failures as one of:

- **UPSTREAM_DRIFT** — a source geography, roster, action route, or API response changed;
- **ENGINE_REGRESSION** — current upstream evidence is valid but resolver behavior changed incorrectly;
- **RUNTIME_INTEGRITY** — packaged runtime SHA or reconstruction failed;
- **TRANSIENT_UPSTREAM_FAILURE** — temporary network/provider failure, confirmed by a clean rerun without changing assertions.

For upstream drift, capture the live artifact, verify the authoritative source, update canonical release/configuration data deliberately, rerun regressions, then require this gate to pass again.

## Baselines

The first successful five-control networked baseline was GitHub Actions run `31224765817` on August 7, 2026.

Denton's pre-package promotion proof passed on run `31237951659`: two distinct interior controls, the Dallas outside-county negative, and both exact-boundary fail-closed controls passed while the original five controls remained green. The next required proof is the same Denton matrix executed against the packaged registry v0.5.0 runtime.
