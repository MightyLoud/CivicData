# Governed local district routing

This extension connects archived, governed local electoral polygons to the
reconstructed Civic GPS runtime without changing the packed core engine.

## Runtime path

```text
address
  ↓
core Civic GPS geocoder
  ↓
BASE municipal activation
  ↓
governed local district overlay
  ↓
archived GeoJSON point-in-polygon
  ↓
district_assignments[]
  ↓
Representation Contract v1
  ↓
Empowered Vote
```

## Current municipal routes

### Alamosa

- Civic GPS jurisdiction: `jur-us-co-alamosa`
- Census place GEOID: `0801090`
- adapter: `DIST-CO-ALAMOSA-WARD`
- governed snapshot:
  `data/reference/co/geometry/alamosa_wards_2023_v0.1.json`

### Arvada

- Civic GPS jurisdiction: `jur-us-co-arvada`
- Census place GEOID: `0803455`
- adapter: `DIST-CO-ARVADA-COUNCIL`
- governed snapshot:
  `data/reference/co/geometry/arvada_council_districts_2023_v0.1.json`

Both BASE bundles and both releases are routing-only. They contain no offices,
officeholders, or action routing.

## Governance

At resolver construction time the extension requires:

1. a valid local-overlay configuration;
2. a `RESOLVED_MACHINE_READABLE` entry in the governed geometry source
   registry;
3. the exact snapshot path recorded by that registry entry;
4. a valid governed geometry snapshot;
5. exact equality between configured district OCDIDs and the snapshot's expected
   district coverage.

Any drift fails before live routing.

## Dynamic assignment

The Factory address controls do not provide the runtime district.

For a live request Civic GPS geocodes the address once. The extension passes the
longitude/latitude into the archived snapshot's point-in-polygon engine. The
returned canonical OCD division is mapped to the configured Civic GPS
`district_key`.

Factory address controls are used only afterward as acceptance expectations.

## Failure behavior

If the municipal jurisdiction is active but its point is outside the governed
district snapshot or lies ambiguously on multiple polygons, the local adapter
emits a conflict/known-gap and no district assignment.

The downstream Contract-v1 consumer therefore fails closed if that district is
required.

No nearest-polygon, label matching, or district guessing is allowed.

## Acceptance

The protected Civic GPS gate proves all eight governed test coordinates through
the actual runtime resolver:

- Alamosa Wards 1–4
- Arvada Council Districts 1–4

For every control it verifies:

- coordinate → governed polygon → dynamic district key;
- Contract-v1 division resolution;
- exact Factory-expected office IDs;
- zero canonical writes.

The Census address geocoder is measured separately as an upstream provider-health
sample. At least one live address per city must activate the municipality and
return the same dynamic district assignment. Individual Census
`ADDRESS_NOT_MATCHED` or transient request failures are reported as provider
gaps rather than being allowed to invalidate an independently governed
coordinate-to-district result.
