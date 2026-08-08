# Civic GPS live-smoke release gate

## Purpose

The Civic GPS live-smoke workflow is the formal networked release and source-drift gate for the packaged Civic GPS resolver.

A Civic GPS runtime/configuration change is not release-ready until the workflow passes against the maintained real-address and boundary controls. The same workflow runs on a weekly schedule so upstream geography/API drift is detected after release as well as before it.

## Gate contract

The workflow must pass before a Civic GPS runtime/configuration change is promoted to `main`.

The runner reconstructs the exact packaged runtime from repository chunks and verifies its SHA-256 before unzipping or executing it. This prevents a partial or altered runtime from being mistaken for a successful release candidate.

Current pinned runtime SHA-256:

`c8b16090b044463379a9ca179ca1196af20c82d47f7d25c84056e4b2bcb9ab39`

Current engine/contract set:

- Overlay Engine: `v0.6.1`
- Adapter registry artifact: `v0.5.2`
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
   - 14 Denton action links

7. **Denton / Flower Mound** — `6200 Canyon Falls Drive, Flower Mound, TX 76226`
   - Commissioner Precinct 4
   - Justice of the Peace Precinct 4
   - Constable Precinct 4
   - 9 applicable Denton offices
   - 14 Denton action links

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

Denton action routing v0.1 is release-backed with 27 verified routes: five Commissioners Court participation/records routes, six countywide elected-office contacts, four Commissioner contacts, six Justice of the Peace court contacts, and six Constable contacts. A normal resolved Denton address returns 14 Denton action links: 11 countywide/body routes plus exactly three precinct-specific routes. Exact boundary conflicts suppress only the ambiguous precinct-specific route or routes while preserving all unambiguous Denton actions.

## Collin County reusable-archetype controls

11. **Collin / Frisco** — `6101 Frisco Square Boulevard, Frisco, TX 75034`
    - Commissioner Precinct 1
    - Justice of the Peace Precinct 4
    - Constable Precinct 4
    - 9 applicable Collin offices

12. **Collin / Plano** — `1520 K Avenue, Plano, TX 75074`
    - Commissioner Precinct 2
    - Justice of the Peace Precinct 3
    - Constable Precinct 3
    - 9 applicable Collin offices

13. **Collin / McKinney** — `2300 Bloomdale Road, McKinney, TX 75071`
    - Commissioner Precinct 3
    - Justice of the Peace Precinct 1
    - Constable Precinct 1
    - 9 applicable Collin offices

14. **Dallas outside-Collin negative** — `1500 Marilla Street, Dallas, TX 75201`
    - Collin must not activate
    - 0 Collin assignments, applicable offices, or actions

15. **Collin Commissioner boundary**
    - Exact current official shared boundary must return Commissioner `CONFLICT` and no Commissioner assignment.
    - Collin BASE plus the unambiguous JP/Constable assignments must survive.
    - Points on opposite sides must resolve to distinct Commissioner precincts.

16. **Collin JP / Constable shared boundary**
    - Exact current official shared boundary must return both JP and Constable `CONFLICT` with neither assignment guessed.
    - Collin BASE plus the unambiguous Commissioner assignment must survive.
    - Points on opposite sides must resolve to distinct JP/Constable precincts.

Collin is the first production county generated with `TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1`: a parameterized build helper that emits the existing Civic GPS BASE registry/release contract rather than a parallel resolver. The release contains 18 offices: six countywide plus four each for Commissioner, Justice of the Peace, and Constable. Collin civic-action routing is explicitly `NOT_YET_RELEASED` in this batch.

Overlay Engine v0.6.1 keeps the resolver logic unchanged and adds an explicit default `CivicGPS` HTTP User-Agent. This is a generic interoperability hardening discovered during Collin proof: Collin's public ArcGIS service rejected the anonymous/default `python-requests` identity but passed the unchanged control matrix when the client identified itself.

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

Denton geography/office applicability was promoted through PR #5 and post-merge main run `31240231410`. Denton action routing v0.1 was promoted through PR #6 and post-merge main run `31241061355`. Collin County then proved the reusable Texas county precinct archetype on isolated run `31241712240` before packaging. Registry v0.5.2 / engine v0.6.1 promotion requires the full baseline + Denton + Collin interior/negative/boundary matrix to pass against the exact packaged runtime.
