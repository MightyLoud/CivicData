# Address pipeline audit corrections

The October 11 audit reproduced order-dependent acceptance and found stale
Alamosa/Arvada package exports, uncaught geometry JSON failures, gaps in live-CI
scope, and competing current control lists.

## Corrections

- Rank every provider observation before coordinate-alias deduplication. Retain
  the strongest observation per point; reject conflicting types at equal-best
  scores. Permutation regressions require the same result for every ordering.
- Regenerate the two package directories from their current jurisdiction JSON
  with `tools.jurisdiction_package_strict.build`. CSV controls, source evidence,
  resolved warning records, QA reports, manifests and checksums match that JSON.
  Civic record and source-evidence values are preserved.
- Resolve the default geometry registry under the supplied root and convert
  expected registry, snapshot and package failures into structured fail-closed
  results.
- Include CO package artifacts, governed geometry, shared controls and the local
  overlay test in live-CI scope. Regressions execute the actual PR grep pattern
  and compare workflow path filters one dependency at a time.
- Load current controls once through `tests.governed_district_controls`. ArcGIS
  smoke delegates to the same exact-office live gate; Civic GPS uses the same
  controls. Remove the obsolete alias map and label the archive warning as
  resolved historical evidence.

## Package source of truth

For these two already-governed packages, the current `jurisdiction.json` is the
source for regenerated exports. The original D-329 factory snapshot remains a
historical import and its exporter tests retain their original scope. No new
official, term, office, source assertion or geometry is introduced.

To regenerate a directory, load its JSON before calling the strict builder,
then require `verify_package(directory) == []`. The builder recreates the
directory inventory and its checksums. The hardening regression also compares
CSV control values and the complete QA report against current JSON.

## Acceptance boundary

ArcGIS retains its score/type/margin policy. Census retains its single-match
policy. Neither provider determines canonical civic geography, and no numeric
confidence is invented for Census. Both routes use governed polygons and
package-backed Contract v1 outputs with zero runtime canonical writes.

The original unsafe synthetic Ward 1/Ward 2 candidate set must return
`AMBIGUOUS_ADDRESS` in all permutations and emit no office set. New corruption
regressions require structured failure envelopes. Live acceptance requires all
eight current controls and exact expected office sets on both provider paths.
