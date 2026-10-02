# Governed Geocoding Boundary v0.1

This layer completes the currently governed address-to-representation path for
jurisdictions with archived district geometry.

## Authority boundary

A geocoder is **not** a civic-data authority.

It may propose:

```text
matched address
longitude
latitude
score
match type
```

It may not decide:

```text
jurisdiction
district
office
officeholder
certification
```

Those remain governed by the geometry registry, Canonical/Contract data, and
consumer gates.

## Default acceptance policy

The current internal policy is intentionally conservative and configurable:

```text
minimum score: 95
minimum lead over distinct runner-up: 5 points
allowed match types:
  - PointAddress
  - StreetAddress
  - Subaddress
maximum returned candidates considered: 5
```

These thresholds are CivicData policy, not a claim that the provider guarantees
accuracy above a universal score.

Exact duplicate/alias candidates at the same coordinate collapse to one
geographic candidate because they cannot alter downstream district assignment.

## Fail-closed states

- `ADDRESS_NOT_MATCHED`
- `GEOCODER_SCORE_BELOW_POLICY`
- `AMBIGUOUS_ADDRESS`
- `GEOCODER_ADDRESS_TYPE_NOT_ALLOWED`
- malformed/non-finite/out-of-range coordinate or provider payload
- point outside all governed geometry
- point inside more than one governed jurisdiction
- missing governed package after geography resolution

## Current live provider

Initial adapter:

```text
ARCGIS_WORLD_GEOCODER
```

The live PR gate sends the eight current Alamosa/Arvada district-control
addresses through:

```text
ArcGIS findAddressCandidates
  → geocoding policy
  → coordinate
  → governed geometry PIP
  → jurisdiction + canonical division
  → Representation Contract v1
  → Empowered Vote applicable offices/holders
```

The live gate is deliberately separate from deterministic CI because it depends
on an external network service.

## Current scope

The no-hint address runtime can automatically select between governed geometry
jurisdictions currently present in the geometry registry.

It does not yet constitute nationwide jurisdiction discovery. Addresses outside
all governed snapshots fail closed rather than falling back to inferred civic
geography.
