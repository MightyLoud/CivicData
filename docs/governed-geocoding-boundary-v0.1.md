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

All candidate observations are normalized and ranked before aliases at the
same coordinate are collapsed. The strongest observation represents each point;
the margin is then measured against the strongest distinct location. Candidate
ordering cannot change acceptance or the selected point. Aliases with the same
best score but conflicting address types fail with `GEOCODER_ALIAS_TYPE_CONFLICT`.

## Fail-closed states

- `ADDRESS_NOT_MATCHED`
- `GEOCODER_SCORE_BELOW_POLICY`
- `AMBIGUOUS_ADDRESS`
- `GEOCODER_ADDRESS_TYPE_NOT_ALLOWED`
- `GEOCODER_ALIAS_TYPE_CONFLICT`
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

Both ArcGIS live entry scripts and the Civic GPS live district probe consume
the same current controls through `tests/governed_district_controls.py` and
require the exact applicable office set after runtime resolution. Historical
facility replacements are documented in CO-RUNTIME-003, rather than maintained
as competing current control lists.

The Census-backed Civic GPS path has provider-specific acceptance semantics:
exactly one address match and finite WGS84 coordinates, without a synthetic
ArcGIS confidence score. Both paths still require governed geometry before
district assignment and keep expected control results out of routing inputs.

## Current scope

The no-hint address runtime can automatically select between governed geometry
jurisdictions currently present in the geometry registry.

It does not yet constitute nationwide jurisdiction discovery. Addresses outside
all governed snapshots fail closed rather than falling back to inferred civic
geography.
