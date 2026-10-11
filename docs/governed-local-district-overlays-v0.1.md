# Governed Local District Overlays v0.1

This extension wires committed local electoral-district polygons into the
reconstructed Civic GPS runtime without modifying the packed runtime bytes.

## Runtime flow

```text
address
  → Civic GPS core geocoder
  → Census place BASE activation
  → governed local district snapshot
  → point-in-polygon
  → district assignment
  → Contract v1 / package-governed civic facts
```

## Current jurisdictions

### Alamosa, Colorado

BASE activation:

```text
Census place GEOID 0801090
jurisdiction jur-us-co-alamosa
```

Local adapter:

```text
DIST-CO-ALAMOSA-WARD
keys 1..4
```

Geometry comes only from the registry-approved snapshot:

```text
data/reference/co/geometry/alamosa_wards_2023_v0.1.json
```

### Arvada, Colorado

BASE activation:

```text
Census place GEOID 0803455
jurisdiction jur-us-co-arvada
```

Local adapter:

```text
DIST-CO-ARVADA-COUNCIL
keys 1..4
```

Geometry comes only from:

```text
data/reference/co/geometry/arvada_council_districts_2023_v0.1.json
```

## Governance

`governed_local_district_overlays` may reference geometry only through the
governed source registry. The source-registry row must be
`RESOLVED_MACHINE_READABLE`, the committed snapshot must validate, and the
snapshot division set must exactly equal the configured overlay division set.

PDF tracing, guessed polygons, and unregistered machine endpoints do not satisfy
this contract.

## Single-geocode rule

The extension runs inside the loader's `geocode_scope()`. The core resolver,
municipal overlays, governed local district overlays, and legislative overlays
therefore reuse one validated geocode for a resolve call.

A deterministic regression counts calls to the underlying geocoder and requires
exactly one.

## Geography-only boundary

The Alamosa and Arvada releases contain:

```text
1 jurisdiction
0 offices
0 officeholders
0 actions
```

The local overlay mutates only:

- `matched_divisions`
- `district_assignments`
- geography evidence
- coverage metadata

It does not supply civic facts.

## Fail closed

If the parent municipality is active but the point is outside its governed local
district polygons, the wrapper returns
`LOCAL_DISTRICT_NOT_RESOLVED`.

An ambiguous shared-boundary point returns
`LOCAL_DISTRICT_AMBIGUOUS`.

Unresolved source-registry state or invalid/missing snapshots also fail closed.

## Acceptance

The live release gate resolves all eight existing Alamosa/Arvada public-facility
controls through the reconstructed Civic GPS geocoder and the committed local
polygons. It then sends the emitted district assignment into Representation
Contract v1 and requires the exact expected municipal office set.

Factory `expected_division_id` values are acceptance evidence only; they never
supply the Civic GPS district assignment.


## Geocoder normalization note

The official Lee Fields facility address is retained in the Factory control as
`1000 Twentieth St, Alamosa, CO 81101`.

The reconstructed Civic GPS core uses a Census-backed address matcher that does
not currently match that spelled-out ordinal. The live acceptance probe uses
the equivalent routing alias:

```text
1000 20th St, Alamosa, CO 81101
```

This alias is **geocoder input normalization only**. It does not alter the
governed point-in-polygon snapshot, expected Ward 4 assertion, canonical
division, or applicable-office result.
