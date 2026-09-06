# Texas legislative geometry governance v0.1

Status: `RESOLVED_INTERNAL_ONLY`

This contract governs the bounded Texas House 49 / Senate 14 internal preview. It does not create a production package profile, authorize publication, change canonical data, or activate Texas in the production registry/catalog.

## Accepted geometry evidence

The September 6, 2026 live acceptance compared the captured service polygons to the official Texas Legislative Council plan shapefiles in TLC's NAD83 Lambert CRS. The accepted evidence is bound to candidate commit `a9994e75d9aac62ae1ae494b8984199e7477bd6a` and archive `Day12_TX_Live_Controls_2026-09-06.zip`, SHA-256 `f8f7d11bccd35d23496cbb3cb0f4dd82f2604bf5b3ac3d3cc7799e4eccb21a39`.

| Chamber | TLC plan | TLC resource / revision | Accepted service marker | Accepted comparison |
| --- | --- | --- | --- | --- |
| House 49 | `PLANH2316` | resource `a4d3230f-47f2-4253-85f3-51a6c3c9ad0a`; revision `b41261de-fc86-4290-9276-c1281d3b4139` | item `0627be7aa6f0440081bd750734761a63`; layer `Texas_State_House_Districts_89th_2025_2027`; schema/data edit `2025-03-17T17:36:25Z` | Hausdorff `0.0000678642 m`; matching vertex count |
| Senate 14 | `PLANS2168` | resource `8247dbc6-b942-4a29-813c-1ebc603a7236`; revision `ff3cee08-8f50-4092-8663-8f3f4bdde189` | item `bef1f9f8758d43378e554c09d5ed6f5c`; layer `Texas_State_Senate_89th_Districts_89th_2025_2027`; schema edit `2025-03-17T17:38:56Z`; data edit `2026-02-04T18:05:32Z` | Hausdorff `0.0000676856 m`; matching vertex count |

The comparison values are numerical snapshot comparisons, not claims of physical survey accuracy or statewide equivalence.

## Runtime rule

Before the default live `resolve_texas_internal_preview` path performs any address geocode or legislative polygon query, it must verify both live ArcGIS layers against the accepted version markers in `civic_gps_extensions/texas_geometry_governance.py`.

For each chamber the preflight requires:

- exact service item ID;
- exact layer name;
- exact schema and data last-edit timestamps at UTC-second precision;
- `DIST_NBR` still present as `esriFieldTypeInteger`.

Any missing metadata, network failure, or mismatch is `GEOMETRY_VERSION_DRIFT` and suppresses the entire Texas legislative preview. The caller must not update a timestamp merely to restore service. A changed marker requires a new authoritative TLC/service comparison, a new acceptance artifact, and an explicit policy revision.

The successful preflight emits a deterministic receipt binding the observed live markers to the accepted TLC identifiers and acceptance-archive hash.

## Test-only sessions

An injected request-compatible `session` remains available for deterministic synthetic testing. That path is explicitly labeled `CONTROLLED_TEST_SESSION_NOT_LIVE_VERIFIED`; it does not satisfy live geometry governance and is not release evidence. Direct generic legislative-overlay use likewise does not create Texas production authority.

## Senate naming discrepancy

The Senate service description references the 88th Legislature while the accepted layer name references the 89th/2025-2027 layer. This discrepancy remains explicit. It is not normalized away. The bounded District 14 geometry is accepted only because the captured service polygon matched the TLC `PLANS2168` snapshot under the recorded comparison.

## Release posture

`GEOMETRY_VERSION_GOVERNANCE = RESOLVED_INTERNAL_ONLY` when:

1. this contract and its pins are present;
2. offline drift controls pass;
3. the live metadata preflight passes against both layers;
4. the accepted live-control archive/hash and candidate commit remain unchanged.

This closes only the geometry-version-governance blocker for the internal bounded preview. Production-profile support, public-identity publication disposition, production deployment validation, merge/release, and activation remain separately governed.
