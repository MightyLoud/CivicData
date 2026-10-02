# Empowered.Vote Essentials consumer — EV-IMP-001

This directory is a bounded, read-only consumer proof for the `EV-CDT-001-FX01` Tacoma package.

It does **not** create a second civic-data authority. It consumes the frozen governed CivicData.Tech payload and preserves canonical IDs, source provenance, explicit scope limits, and fail-closed behavior.

## What it proves

- exact frozen-address lookup for governed Tacoma/Pierce controls;
- only geographically applicable Tacoma offices are displayed;
- current holder data is joined by canonical office/person IDs;
- recent certified election → contest → candidacy relationships are preserved;
- official-source provenance is exposed with every displayed office and contest;
- unsupported addresses fail closed;
- the adapter performs zero canonical writes;
- identical input produces an identical deterministic consumer model.

## Run

```bash
python consumers/empowered_vote/render.py \
  /path/to/10_frozen_ev_payload.json \
  --address "747 Market Street, Tacoma, WA 98402" \
  --json-out artifacts/ev-imp-001-tacoma.json \
  --html-out artifacts/ev-imp-001-tacoma.html

python tests/empowered_vote_essentials_test.py
```

## Scope boundary

The governed full Tacoma payload is intentionally not vendored into this code directory; its hashes and bounded acceptance result are recorded in `docs/ev-imp-001-acceptance.json`.

This is not a production geocoder. Only addresses present in the governed `address_controls` array are accepted. A non-fixture address returns `ADDRESS_NOT_IN_FROZEN_FIXTURE` rather than guessing.

The frozen package is Tacoma-centered. The resolver may establish another jurisdiction such as Pierce County, but this consumer does not invent county officials when those records are not in the Tacoma fixture.

## Representation Contract v1 shadow path

The existing Jurisdiction Package consumer remains unchanged and remains the production path during migration.

Two additive modules provide the Contract v1 shadow path:

- `contract_v1.py` consumes a **certified** Representation Contract v1 snapshot and joins it to Civic GPS geography.
- `contract_v1_catalog.py` selects the same governed package from the existing package catalog, projects it into Contract v1, and runs both paths side by side.

For Akron:

```python
from consumers.empowered_vote import contract_v1_catalog

comparison = contract_v1_catalog.compare_shadow_to_legacy(
    "250 Main Avenue, Akron, CO 80720",
    civic_gps_result,
    repo_root=".",
)
assert comparison["parity_ok"] is True
```

Public output fails closed when Contract v1 is uncertified. A CivicPatch-rendered or partner-submitted contract can therefore participate in reconciliation without becoming voter-facing authority.

Current Contract v1 scope is representation only. Election, contest, candidacy, countywide-special-case, and multi-binding production profiles continue on their existing governed paths until separately migrated and parity-tested.

See `docs/empowered-vote-contract-v1.md`.


## Generic governed-address runtime conformance

`runtime_conformance.py` generalizes the Contract-v1 runtime proof across
governed Jurisdiction Packages.

It uses each package's passing `qa.address_tests` rows as the reviewed
address → division/office fixture boundary and then executes the same
Contract-v1 representative lookup used by Empowered Vote.

This is intentionally labeled:

```text
GOVERNED_FACTORY_ADDRESS_CONTROL
```

rather than `CIVIC_GPS_LIVE`. Live/network Civic GPS remains a separate smoke
test. District/ward divisions without a governed address control are reported as
coverage gaps, never inferred.


## Governed coordinate → division runtime

District routing can now bypass predeclared Factory district bindings.

`tools/governed_geography_resolver.py` loads the governed geometry source
registry and committed polygon snapshot, runs point-in-polygon, and returns the
canonical OCD division. It can also emit a geography-only payload compatible
with the existing Civic GPS normalization boundary.

Current deterministic coverage:

```text
8 district controls → GOVERNED_GEOMETRY_PIP
10 citywide controls → GOVERNED_FACTORY_ADDRESS_CONTROL
```

For the eight Alamosa/Arvada district controls,
`expected_division_id` is validation evidence only. Changing that expected
value does not change the runtime PIP result; it causes conformance to fail.
Address geocoding remains a separate upstream responsibility.
