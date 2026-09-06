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
# This invocation performs live geocoder and boundary requests.
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

## Source and vintage limits

| Chamber | Adapter | District field/key | Plan authority |
| --- | --- | --- | --- |
| House | `DIST-TX-HOUSE-H2316` | `DIST_NBR` / `49` | [TLC PLANH2316](https://data.capitol.texas.gov/dataset/planh2316) |
| Senate | `DIST-TX-SENATE-S2168` | `DIST_NBR` / `14` | [TLC PLANS2168](https://data.capitol.texas.gov/dataset/plans2168) |

The helper pins the inspected TxDOT ArcGIS layer URLs in `SOURCES`. Adapter
names identify the intended plans; they do not certify that live service geometry
is byte-for-byte equivalent to the TLC plan downloads. House geometry equivalence
is unpinned. The Senate service description refers to the 88th Legislature while
the layer name refers to the 89th. Both caveats are explicit in assignment
`source_vintage_status`, and every successful group retains a
`NOT_YET_RELEASED` gap. GIS representative-name attributes are ignored.

The one-meter probe depends on the ArcGIS service honoring distance queries.
Synthetic tests prove request/response handling, not live topology or service
semantics. Before release, verify the geometry vintage and intended runtime with
an in-slice address, an outside-district address, and actual boundary controls.
The prior recorded D417 geocode is historical evidence; this patch and its
offline tests do not repeat that address request.

## Verification

```sh
python tests/civic_gps_legislative_overlay_test.py
python tests/test_role_term_integration.py
```

The routing suite reconstructs and checks the pinned core ZIP, injects synthetic
responses, and covers one-geocode composition, atomic failures, boundary probes,
source errors, malformed results, provisional identities, source immutability,
concurrent calls, stable hashes, county preservation, and municipal coexistence.
Existing package and consumer regressions remain required for compatibility.

Extension edits activate the existing Civic GPS release gate. Its legislative
step is offline; its existing county/Tacoma live steps provide regression evidence
only. Neither substitutes for the Texas controls above. Packed runtime parts,
production registry/catalog entries, canonical data, and frozen proof hashes are
unchanged by this patch. Day 12 closeout, merge, and production activation require
their remaining acceptance decisions and evidence.
