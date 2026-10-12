# Governed Address Runtime v0.1

This completes the internal address → representatives pipeline for jurisdictions
with governed polygon geometry.

## Flow

```text
address
  → geocoder candidates
  → confidence / ambiguity gate
  → coordinate
  → governed geometry resolve_any()
  → canonical jurisdiction + district
  → certified Factory package
  → Representation Contract v1
  → Empowered Vote offices + holders
```

## Authority boundary

The geocoder is **not** civic authority. It proposes a location.

The geocoding gate requires:

- score >= 95 by default;
- PointAddress, StreetAddress, or Subaddress;
- at least a 5-point margin over a geographically distinct runner-up;
- valid finite WGS84 longitude/latitude.

Multiple labels for the same returned coordinate are collapsed before ambiguity
evaluation, after ranking all observations. Conflicting match types among
equal-best aliases fail closed. The selected point and margin are independent
of provider candidate order.

The governed polygon snapshot remains authoritative for coordinate → district.

## Fail closed

Examples:

- `ADDRESS_NOT_MATCHED`
- `GEOCODER_SCORE_BELOW_POLICY`
- `GEOCODER_ADDRESS_TYPE_NOT_ALLOWED`
- `AMBIGUOUS_ADDRESS`
- invalid coordinates
- point outside all governed geometry
- ambiguous governed jurisdiction/division
- unavailable or corrupt source registry/snapshot
- malformed, duplicate, missing or unexportable jurisdiction package

The source registry defaults to the supplied repository root. Expected registry,
snapshot and package failures return a structured `FAIL-CLOSED` result with
zero canonical writes.

## Live provider

The initial live adapter uses the public ArcGIS World Geocoder with
`forStorage=false`. No geocoder response is promoted into canonical data.

CI runs the eight governed Alamosa/Arvada public-facility addresses through the
full live chain. Both provider paths read current package controls through one
shared loader and compare the exact expected office set after resolution.

## Output

Successful output includes:

- selected geocoder observation + policy;
- governed geometry source and snapshot;
- canonical jurisdiction/division;
- certified package path;
- applicable offices/holders;
- `canonical_writes = 0`.
