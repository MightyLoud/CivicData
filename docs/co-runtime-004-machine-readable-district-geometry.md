# CO-RUNTIME-004 — Machine-readable district geometry

## Bottom line

The governed Colorado representation pipeline now contains pinned, machine-readable
local-election geometry for every currently normalized ward/district jurisdiction:

- Alamosa Wards 1–4
- Arvada Council Districts 1–4

Normal validation is offline. Network access is used only by the refresh workflow
to detect upstream geometry drift.

## Pinned artifacts

```text
data/geometry/co/
  alamosa_wards.geojson
  arvada_council_districts.geojson
  district_control_points.json
  district_geometry_manifest.json
  district_geometry_verification.json
```

Both GeoJSON files are normalized to EPSG:4326 and contain exactly four polygon
features with a normalized `properties.district` value of `1`–`4`.

## Authoritative sources

### Alamosa

Official ArcGIS polygon layer:

```text
https://services2.arcgis.com/kQ9CrbL3URg6t3jo/ArcGIS/rest/services/Wards/FeatureServer/0
```

Field used:

```text
WARD
```

Pinned canonical GeoJSON SHA-256:

```text
1deec2550add4b6129cf2ec5b15e6c154b9d029d70376711ab36d9f12fb1e000
```

### Arvada

The official City Council Districts application is:

```text
https://arvada.maps.arcgis.com/apps/instant/sidebar/index.html?appid=332a7eba6a4641999d278cfa6ee149f4
```

Its web map identifies the City-owned Council Districts feature service. The
governed polygon layer is:

```text
https://services1.arcgis.com/eQyVgDz2cjhzbzN7/arcgis/rest/services/Council_Districts/FeatureServer/1
```

Field used:

```text
DISTRICT
```

Pinned canonical GeoJSON SHA-256:

```text
fb00b068f851899ef8446f4fc28e1bb6b74d98839a0038a82a2048df4568a491
```

## Point-in-polygon acceptance

All eight governed local-district controls were geocoded with score 100 during
the governed retrieval run and then independently tested against the downloaded
polygons.

| Jurisdiction | Control | Expected | Verified |
|---|---|---:|---:|
| Alamosa | Cattails Golf Course | Ward 1 | 1 |
| Alamosa | Carroll Park | Ward 2 | 2 |
| Alamosa | Jardin Hermosa Park | Ward 3 | 3 |
| Alamosa | Lee Fields | Ward 4 | 4 |
| Arvada | Lake Arbor Golf Course | District 1 | 1 |
| Arvada | Little Dry Creek Park | District 2 | 2 |
| Arvada | Little Raven Park | District 3 | 3 |
| Arvada | West Woods Golf Club | District 4 | 4 |

The exact coordinates and geocoder matches are retained in
`district_control_points.json`; the evaluated results are retained in
`district_geometry_verification.json`.

## Offline authority path

Routine CI runs:

```bash
python tests/test_district_geometry.py
```

It verifies:

1. the pinned geometry hashes match the manifest;
2. each geometry contains exactly districts 1–4;
3. all eight pinned coordinates recompute to the recorded district;
4. each Factory package contains the exact machine-readable source URL;
5. each district address control is bound to that source;
6. the former machine-readable-geometry warning is closed.

No network call is needed.

## Refresh / drift path

`.github/workflows/district-geometry-fetch.yml` remains the network-enabled
refresh check.

It fetches the current official FeatureServer geometry, geocodes the eight
controls, reruns point-in-polygon checks, and compares the current geometry
hashes to the pinned manifest.

A source hash change fails the drift check even when the control points still
pass. Geometry changes therefore require explicit review and an intentional
snapshot refresh rather than silently changing canonical routing.

## Warning disposition

The two prior nonblocking warnings:

```text
gap-co-alamosa-machine-readable-ward-geometry
gap-co-arvada-machine-readable-district-geometry
```

are closed because the missing artifacts now exist, are pinned, source-linked,
hashed, and tested offline.

This does not authorize publication or partner writes.
