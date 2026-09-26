# Governed District Geometry v0.1

This layer is the next gate after governed address controls.

## Purpose

Store authoritative machine-readable district polygons so address routing can be
verified by point-in-polygon rather than only by reviewed fixture controls.

## Rule

A map image/PDF is sufficient boundary evidence for manual QA, but it is **not**
promoted into canonical machine geometry by tracing or guessing.

A geometry snapshot is eligible only when it comes from:

- a direct official machine-readable source; or
- an official machine export whose provenance can be pinned.

## Current source-resolution state

### Alamosa

Current authority is the County-hosted City of Alamosa Wards map. The City also
publishes multiple ArcGIS FeatureServices, confirming an active municipal GIS
environment. No current ward FeatureServer/shapefile endpoint has yet been
verified.

Status:

```text
UNRESOLVED_ENDPOINT
ALAMOSA_WARD_MACHINE_SOURCE_UNRESOLVED
```

### Arvada

The City publishes an official Council District PDF, interactive ArcGIS map, and
Open Data portal. The exact backing machine polygon endpoint for the current
official interactive map has not yet been verified and pinned.

Status:

```text
UNRESOLVED_ENDPOINT
ARVADA_COUNCIL_DISTRICT_MACHINE_SOURCE_UNRESOLVED
```

## Snapshot contract

A governed snapshot records:

- jurisdiction OCDID;
- exact source locator;
- source snapshot/version identifier;
- retrieval timestamp;
- direct-machine vs official-export derivation;
- expected canonical division IDs;
- the raw canonical GeoJSON FeatureCollection;
- the property that maps each feature to canonical division identity.

The validator requires exactly one Polygon/MultiPolygon feature for every
expected district division.

## Point-in-polygon

`tools/geometry_governance.py` provides deterministic Polygon/MultiPolygon
point resolution, including holes and boundary handling.

Shared boundaries intentionally fail ambiguous:

```text
POINT_GEOMETRY_AMBIGUOUS
```

Points outside all governed features fail:

```text
POINT_OUTSIDE_GOVERNED_GEOMETRY
```

## Promotion gate

The existing package warnings:

```text
MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED
```

must remain open until the source registry moves to
`RESOLVED_MACHINE_READABLE` **and** a validated governed snapshot is committed.

No hand-digitized polygon from the official PDFs satisfies this gate.
