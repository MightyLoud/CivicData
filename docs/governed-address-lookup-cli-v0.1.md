# Internal governed address lookup CLI v0.1

Run a quoted street address through the existing generic address runtime:

```bash
python tools/governed_address_lookup.py "500 Cottonwood Dr, Alamosa, CO 81101"
```

From another working directory, use the full script path. Its default repository
root comes from the script location, rather than the working directory:

```bash
python /path/to/CivicData/tools/governed_address_lookup.py "500 Cottonwood Dr, Alamosa, CO 81101"
```

An alternate checkout containing the governed data can be supplied explicitly:

```bash
python tools/governed_address_lookup.py "500 Cottonwood Dr, Alamosa, CO 81101" --repo-root /path/to/CivicData --timeout-seconds 20
```

The command sends the address to the current ArcGIS World Geocoder adapter and
uses its existing conservative policy: minimum score 95, minimum distinct-location
margin 5, allowed PointAddress/StreetAddress/Subaddress types, and up to five
requested candidates. Coordinates then reach the governed polygon resolver,
which selects the jurisdiction and district without an expected result or hint.
Contract v1 supplies the applicable offices and holders.

Successful stdout is the unchanged runtime JSON. It includes
`resolved_division_ocdid`, `applicable_offices[].holders`, `source_evidence`,
`source_assertions`, `geocoding`, `governed_geography` and `package_path`.
Geography provenance includes the official source URL, archived snapshot path
and snapshot ID. `canonical_writes` remains zero. Contract generation uses the
current UTC timestamp automatically.

| Exit code | Meaning | Output |
|---|---|---|
| 0 | Runtime PASS | JSON on stdout |
| 1 | Resolution rejected or execution failed | FAIL-CLOSED JSON on stdout |
| 2 | Missing/invalid command arguments | Usage/error on stderr |
| 130 | Lookup interrupted | FAIL-CLOSED JSON on stdout |

Examples of preserved rejection codes include `AMBIGUOUS_ADDRESS`,
`GEOCODER_SCORE_BELOW_POLICY`, `ADDRESS_NOT_MATCHED`,
`GEOCODER_PROVIDER_REQUEST_FAILED` and `POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY`.
Unexpected execution failures become `LOOKUP_EXECUTION_FAILED`; malformed runtime
results become `LOOKUP_RUNTIME_RESULT_INVALID`. No partial JSON is emitted.

Current polygon coverage is Alamosa Wards 1–4 and Arvada Council Districts 1–4.
Addresses outside governed coverage fail closed. This is the bounded municipal
representation path, not complete national, state or county office coverage.
The command does not deploy or modify the Texas HTTP service.

The dedicated CI workflow runs offline CLI and existing runtime regressions on
relevant PRs and main pushes, and can be invoked manually. Injected providers are
an in-process testing seam; no candidate file, fixture flag, expected division,
jurisdiction override or policy-relaxation option is exposed by the command.

```bash
python -m unittest -v tests.test_governed_address_lookup tests.test_address_geocoding_runtime
```
