# Colorado district address controls — CO-RUNTIME-003

This batch closes the deterministic address-runtime coverage gaps for the two
currently normalized Colorado jurisdictions with local electoral districts.

## Alamosa

Boundary authority:

- City/County ward map, Wards 1–4:
  `https://www.alamosacounty.org/DocumentCenter/View/177/City-of-Alamosa-Wards-PDF?bidId=`

Address authority:

- City of Alamosa Parks & Recreation facilities map:
  `https://cityofalamosa.org/wp-content/uploads/2018/08/City-Parks-and-Recreation-Facilities.pdf`

Controls:

| Ward | Public facility | Address | Applicable offices |
|---|---|---|---|
| 1 | Cattails Golf Course | 500 Cottonwood Dr | Mayor + At-Large + Ward 1 |
| 2 | Carroll Park | 860 Craft Dr | Mayor + At-Large + Ward 2 |
| 3 | Jardin Hermosa Park | 1555 W Sixth St | Mayor + At-Large + Ward 3 |
| 4 | Alamosa Cemetery | 2190 State Ave | Mayor + At-Large + Ward 4 |

## Arvada

Boundary authority:

- City Council Districts map, adopted January 23, 2023:
  `https://maps.arvada.org/opendata/pdf/City_Council_Districts.pdf`

Address authority:

- City parks/facility pages and golf-course pages under `arvadaco.gov`.

Controls:

| District | Public facility | Address | Applicable offices |
|---|---|---|---|
| 1 | Lake Arbor Golf Course | 8600 Wadsworth Boulevard | Mayor + two At-Large + District 1 |
| 2 | Little Dry Creek Park | 7770 Pierce St | Mayor + two At-Large + District 2 |
| 3 | Harold D. Lutz Sports Complex | 10664 W 58th Ave | Mayor + two At-Large + District 3 |
| 4 | West Woods Golf Club | 6655 Quaker Street | Mayor + two At-Large + District 4 |

## Runtime semantics

The controls are consumed through:

```text
Factory qa.address_tests
  -> OCD division crosswalk
  -> Representation Contract v1
  -> Empowered Vote governed-address runtime
  -> exact applicable-office comparison
```

No district is inferred from a name or office title.

## Historical archive warning - resolved

The original CO-RUNTIME-003 address-control batch did not itself archive a
machine-readable district snapshot. Issue #100 subsequently archived and
verified both official polygon sources. The current governed source registry
marks both entries `RESOLVED_MACHINE_READABLE`.

Accordingly, both prior PIP warnings were narrowed to:

```text
MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED
```

That warning is retained as a resolved audit record, rather than a current
geometry blocker. Current package JSON is authoritative for acceptance controls;
CSV, QA report, manifest and checksum exports are regenerated with the existing
strict package builder and checked for parity.


## Ward 4 control refresh — 2026-10-11

The historical Ward 4 acceptance control used Lee Fields at
`1000 Twentieth St`. The governed polygon assignment was correct, but the
reconstructed Civic GPS Census-backed geocoder did not match that facility
street spelling (including tested `20th St` variants).

The Ward 4 control was therefore refreshed to another City-listed public
facility in the same governed ward:

```text
Alamosa Cemetery
2190 State Ave, Alamosa, CO 81101
```

The reconstructed Civic GPS resolver activates Alamosa and emits Ward 4 for this
address. ArcGIS independently geocodes it as a score-100 PointAddress at the
committed derived test coordinate. The Ward 4 polygon and applicable-office
assertions did not change.


## Arvada District 3 control refresh — 2026-10-11

The historical District 3 control used Little Raven Park at
`12140 W 57th Ave`. Its governed polygon assignment was correct, but the
reconstructed Civic GPS Census-backed geocoder did not return an address match.

The District 3 live control now uses another City-listed public athletic
facility inside the same governed district:

```text
Harold D. Lutz Sports Complex
10664 W 58th Ave, Arvada, CO 80002
```

The reconstructed Civic GPS resolver activates Arvada and emits District 3 for
this address. ArcGIS independently geocodes it as a score-100 PointAddress at
the committed derived test coordinate. The District 3 polygon and applicable
office assertions did not change.
