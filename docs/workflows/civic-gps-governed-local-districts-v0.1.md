# Civic GPS governed local district overlays v0.1

This extension wires committed local electoral-district geometry into the
reconstructed Civic GPS runtime without modifying the packed runtime bytes.

## Runtime sequence

```text
address
  → core Civic GPS geocode
  → Census place activation
  → routing-only municipal BASE bundle
  → cached geocode coordinate
  → committed governed local polygon snapshot
  → point-in-polygon
  → Civic GPS district assignment
  → Representation Contract v1
  → applicable offices + holders
```

## Current jurisdictions

### Alamosa, Colorado

- Census place GEOID: `0801090`
- Civic GPS jurisdiction: `jur-us-co-alamosa`
- local adapter: `DIST-CO-ALAMOSA-WARDS-GOVERNED`
- snapshot: `data/reference/co/geometry/alamosa_wards_2023_v0.1.json`
- district keys: `1..4`

### Arvada, Colorado

- Census place GEOID: `0803455`
- Civic GPS jurisdiction: `jur-us-co-arvada`
- local adapter: `DIST-CO-ARVADA-COUNCIL-GOVERNED`
- snapshot: `data/reference/co/geometry/arvada_council_districts_2023_v0.1.json`
- district keys: `1..4`

## Authority split

The Civic GPS extension emits only:

- jurisdiction activation;
- matched division geography;
- district assignment;
- source evidence / coverage metadata.

The Alamosa and Arvada routing releases contain **zero offices and zero
officeholders**. The extension also adds no action links.

All voter-facing offices and holders come from the certified Jurisdiction
Package projected through Representation Contract v1.

## Geocode reuse and bounded fallback

The wrapper opens one scoped geocode context per `resolve()` call. When the
core Census geocoder succeeds, the core resolver and governed local overlay both
call the engine's geocode interface but receive the same validated geocode from
request-local cache. A regression requires one underlying Census geocoder call.

If—and only if—the core returns `ADDRESS_NOT_MATCHED`, the wrapper may invoke
the existing governed geocoding boundary (currently ArcGIS World Geocoder) as a
coordinate-only fallback. That fallback succeeds only when the coordinate is
inside exactly one committed governed local geometry snapshot. It then creates
routing geography and runs the same local PIP overlay.

A fallback coordinate outside all governed local snapshots preserves the
original core `ADDRESS_NOT_MATCHED`; no broad geocoder fallback is created for
uncovered jurisdictions.

When this bounded fallback succeeds, its municipal/local geography is complete
for that resolve call. The wrapper does not re-run the failed Census geocode for
the local overlay or attempt legislative overlays from a geography response that
the core Census path never established.

## Geometry governance

At resolver construction, each local overlay must match a
`RESOLVED_MACHINE_READABLE` entry in the district-geometry source registry.
The configured snapshot path must exactly match the registry, the snapshot must
validate, and configured division coverage must equal the snapshot's expected
division set.

The runtime fails closed if an active municipality's coordinate is outside the
governed local polygons or falls on an ambiguous shared boundary. Geometry
assets are prepared lazily on first activation, so a Texas-only deployment does
not need Colorado snapshots merely because the shared extension registry
contains Colorado configuration.

## Live acceptance

The live Civic GPS gate resolves all eight current Alamosa/Arvada district
address controls. For every control it requires:

1. correct municipal jurisdiction activation;
2. correct governed district key;
3. zero municipality-specific Civic GPS civic-fact rows;
4. certified Contract v1 consumption;
5. exact expected municipal office set;
6. zero canonical writes.
