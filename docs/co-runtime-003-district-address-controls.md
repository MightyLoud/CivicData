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
| 4 | Lee Fields | 1000 Twentieth St | Mayor + At-Large + Ward 4 |

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
| 3 | Little Raven Park | 12140 W 57th Ave | Mayor + two At-Large + District 3 |
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

## Remaining warning

These controls close address-runtime coverage. They do **not** by themselves
archive a machine-readable polygon/feature-service snapshot for either city's
district geometry.

Accordingly, both prior PIP warnings were narrowed to:

```text
MACHINE_READABLE_DISTRICT_GEOMETRY_NOT_ARCHIVED
```

That warning remains nonblocking and separate from the now-complete address
runtime coverage.
