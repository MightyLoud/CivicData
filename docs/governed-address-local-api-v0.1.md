# Local governed address HTTP adapter v0.1

From the repository root, install the existing HTTP stack plus Pydantic 2 and
launch the adapter:

```bash
python -m pip install -r requirements-governed-address-api.txt
python -m services.governed_address_api --port 8010
```

The supplied launcher binds to `127.0.0.1`. It accepts `--port`, `--repo-root`
and `--timeout-seconds` (default 30; greater than zero and at most 120). The
repository root defaults to the module's checkout location. Access logging is
disabled. This is a local internal adapter; no hosted deployment is configured.

Submit a JSON object containing only a street address:

```bash
curl --request POST http://127.0.0.1:8010/v1/representation \
  --header 'Content-Type: application/json' \
  --data '{"address":"208 Edgemont Blvd, Alamosa, CO 81101"}'
```

The address must be a string with 1–500 characters after whitespace is collapsed.
Other fields and malformed requests are rejected before geocoding. There is no
HTTP option for coordinates, expected divisions, jurisdiction hints, alternate
data roots or relaxed geocoding policy.

The adapter calls `build_representation_for_address` with the current UTC
generation timestamp. The existing ArcGIS World Geocoder supplies candidate
coordinates, subject to the runtime's minimum score 95, distinct-location margin
5, PointAddress/StreetAddress/Subaddress types and five requested candidates.
The governed polygon resolver selects the jurisdiction and district; Contract v1
supplies offices and holders. Provider injection in `create_app` is an in-process
testing seam.

Successful responses preserve the runtime JSON, including
`resolved_division_ocdid`, `applicable_offices[].holders`, `source_evidence`,
`source_assertions`, `geocoding`, `governed_geography` and `package_path`.
Geography provenance includes the official source URL, archived snapshot path
and snapshot ID. Every lookup response has `Cache-Control: no-store`, and
`canonical_writes` remains zero.

| HTTP status | Result | Representative error codes |
|---|---|---|
| 200 | Runtime `PASS` | — |
| 404 | No address match or point outside governed coverage | `ADDRESS_NOT_MATCHED`, `POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY` |
| 422 | Invalid request, ambiguous result or match rejected by policy | `ADDRESS_REQUEST_INVALID`, `AMBIGUOUS_ADDRESS`, `GEOCODER_SCORE_BELOW_POLICY`, `POINT_GEOMETRY_AMBIGUOUS` |
| 503 | Provider, governed-data or execution failure | `GEOCODER_PROVIDER_REQUEST_FAILED`, `GOVERNED_GEOMETRY_SOURCE_REGISTRY_INVALID`, `ADDRESS_API_EXECUTION_FAILED` |

Lookup failures have `status: FAIL-CLOSED`, an `error` code and
`canonical_writes: 0`. Existing runtime errors are preserved. Malformed runtime
envelopes become `ADDRESS_API_RUNTIME_RESULT_INVALID`; unexpected exceptions or
non-finite output become `ADDRESS_API_EXECUTION_FAILED`. The adapter does not
return partial success JSON or exception details.

`GET /healthz` reports process health only. It does not contact the geocoder or
validate data readiness. `GET /v1/representation` is not a lookup method, and
interactive documentation routes are disabled.

Current polygon coverage is Alamosa Wards 1–4 and Arvada Council Districts 1–4.
This endpoint returns the bounded municipal representation model. State, county
and national office coverage is not added by this adapter. The existing Texas
service is a separate application.

The dedicated workflow runs offline HTTP, CLI and existing address runtime
regressions on relevant PRs and main pushes, and can be invoked manually. The
HTTP suite verifies all eight district controls against real polygons and
package office/holder IDs, failure status codes, read-only data, and a real
loopback TCP request through Uvicorn. CI does not call a live geocoder.

```bash
python -m pip install -r requirements-governed-address-api.txt 'httpx>=0.28,<1'
python -m unittest -v tests.test_governed_address_api tests.test_governed_address_lookup tests.test_address_geocoding_runtime
```
