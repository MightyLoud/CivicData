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
