# Internal legislative geography routing

This extension adds an explicit internal preview for the Texas House 49 / Senate
14 slice. Civic GPS supplies geography; the caller's staged jurisdiction package
supplies all Persons, Offices, RoleTerms, dates, and provenance. No Texas group
is registered in the default extension configuration or production catalog.

## Invocation

Reconstruct the pinned Civic GPS runtime using the existing release workflow and
install `requirements-civic-gps.txt`. Run from an environment where the repository
root is on Python's import path:

```python
from civic_gps_extensions.texas_legislative import resolve_texas_internal_preview

# package, address, and both exact canonical division IDs come from the caller.
# The default live path verifies governed geometry-version markers before geocoding.
preview = resolve_texas_internal_preview(
    package,
    address,
    repo_root=repo_root,
    house_division_id=house_division_id,
    senate_division_id=senate_division_id,
)
```

For an offline configuration inspection, call
`build_texas_internal_configuration(package, house_division_id=...,
senate_division_id=...)`. It returns a geography group and two consumer bindings
without making requests. It requires the Texas state package, a valid identity
graph, explicit existing division IDs, and chamber/district labels consistent
with the bounded slice. Labels validate the supplied crosswalk; they never mint
or replace canonical IDs. No actual Person or RoleTerm records are embedded in
the helper or test fixtures.

The generic loader accepts explicit `legislative_overlays` and an optional
request-compatible `session` for controlled testing. Groups have strict field
validation and must declare `scope=INTERNAL_REVIEW` and
`publication_eligible=false`. The Texas helper is the reviewed two-chamber
configuration; custom groups need their own source and coverage review.

## Resolution contract

1. The core and all extensions reuse one validated geocoder response within the
   resolver call. Zero or multiple address matches, invalid coordinates, and
   malformed geography collections stop resolution. The cache is cleared when
   the call ends and is isolated between concurrent calls.
2. Exactly one state geography must identify Texas. Conflicting state fields or
   another state prevent legislative requests.
3. Separate House and Senate adapters request only `DIST_NBR` from the official
   polygon layers. Queries use the unfiltered layer (`where=1=1`) so a neighboring
   unsupported district cannot disappear behind a filter.
4. Each chamber requires one exact point intersection and one intersection from
   a one-meter distance probe, both returning the same positive district key.
   Multiple polygons, malformed/truncated results, source failures, and keys
   outside the configured slice stop the entire legislative group.
5. Both chambers must resolve before any legislative jurisdiction, division,
   assignment, or evidence is appended. Existing county/municipal facts remain
   available if the legislative group fails. Existing result IDs cannot be
   overwritten by a colliding extension ID.
6. Successful geography includes the explicit canonical jurisdiction and division
   IDs, four query evidence URLs, and `GEOGRAPHY_ONLY` coverage. It adds no
   Offices, officeholders, or actions. Consumer composition uses the two exact
   bindings and returns both projections or a failure without partial officials.

The top-level preview always reports `complete_jurisdiction=false`,
`publication_eligible=false`, and `canonical_writes=0`. A `PASS` means the bounded
internal preview resolved; it is not a package release result. The helper does
not pass the staged package through the production package loader or change its
blocking gaps/address-control results. Provisional Persons remain provisional
with visible warnings; the default representation consumer still rejects them.

## Source and version governance

| Chamber | Adapter | District field/key | Plan authority |
| --- | --- | --- | --- |
| House | `DIST-TX-HOUSE-H2316` | `DIST_NBR` / `49` | [TLC PLANH2316](https://data.capitol.texas.gov/dataset/planh2316) |
| Senate | `DIST-TX-SENATE-S2168` | `DIST_NBR` / `14` | [TLC PLANS2168](https://data.capitol.texas.gov/dataset/plans2168) |

Geometry-version governance for this bounded helper is defined by
[`texas-legislative-geometry-governance-v0.1.md`](texas-legislative-geometry-governance-v0.1.md).
The September 6, 2026 acceptance bound the captured House 49 and Senate 14 service
polygons to the official TLC plan snapshots and retained the acceptance archive
hash and candidate commit. The helper now pins the TLC resource/revision identities
and the mutable ArcGIS service item, layer name, schema/data edit markers, and
`DIST_NBR` type.

The default live `resolve_texas_internal_preview` path checks those live service
markers before any address geocode. Missing metadata, service failure, or any
marker drift returns `GEOMETRY_VERSION_DRIFT` and suppresses the entire Texas
legislative preview. A changed marker requires a new TLC/service comparison and
new acceptance; updating a timestamp alone is not an accepted remediation.

The Senate service description still refers to the 88th Legislature while the
accepted layer name refers to the 89th/2025-2027 layer. That discrepancy remains
explicit and is not normalized away. The captured District 14 polygon was accepted
only because its recorded geometry comparison agreed with the TLC `PLANS2168`
snapshot under the acceptance method.

An injected request-compatible `session` is a controlled-test path. It is labeled
`CONTROLLED_TEST_SESSION_NOT_LIVE_VERIFIED` and does not satisfy live geometry
governance or release evidence. Direct generic overlay use likewise does not
create Texas production authority.

## Verification

```sh
python tests/civic_gps_legislative_overlay_test.py
python tests/civic_gps_texas_geometry_governance_test.py
python tests/test_role_term_integration.py
python -m civic_gps_extensions.texas_geometry_governance  # live metadata preflight
```

The routing suite reconstructs and checks the pinned core ZIP, injects synthetic
responses, and covers one-geocode composition, atomic failures, boundary probes,
source errors, malformed results, provisional identities, source immutability,
concurrent calls, stable hashes, county preservation, and municipal coexistence.
The geometry-governance suite covers deterministic acceptance receipts and
fail-closed service-item, layer-name, schema/data-edit, and district-field drift.
Existing package and consumer regressions remain required for compatibility.

Extension edits activate the existing Civic GPS release gate. The separate
`Texas geometry governance` workflow runs the offline drift controls and the live
metadata preflight on relevant changes and weekly. Neither test path authorizes
publication, changes canonical data, or activates a production profile. Packed
runtime parts, production registry/catalog entries, canonical data, and frozen
proof hashes remain separately governed. Day 12 closeout, merge, and production
activation require their remaining acceptance decisions and evidence.
