# Texas geometry marker refresh candidate

Review candidate only; no merge, deployment, or publication authorization.

The House schema/data markers changed on October 15. This candidate records an explicit marker revision under the existing policy schema and binds the comparison evidence hash into the deterministic governance receipt. Senate pins, source civic packages, registry IDs, and service identities are unchanged. Drift remains blocking.

The checksum-verified September 6 acceptance archive contains the original authoritative TLC shapefiles. Both current bounded district response byte hashes match the accepted captures, and same-CRS TLC comparisons reproduce the earlier numerical results. Live TLC download was HTTP 403; current statewide equivalence and current TLC download bytes are unverified. Raw current district responses are retained in the private review site's version 10 source repository at dist/evidence/texas-geometry, with exact hashes in comparison.json; the authoritative original archive is Library item libfile_8be1fbc47d808191a5b637c739f27e89.

Fresh live controls: Capitol positive and Round Rock negative; midpoint, 0.25 m inside, and 10 m inside for each chamber. All eight returned expected statuses. Metadata preflight passed before and after. These are internal review controls using a real recording network session; the consumer's injected-session caveat is preserved and this is not production release evidence.

Local regressions: 9 governance, 3 activation runtime, 6 successor package, and 3 post-activation runtime tests passed. The post-activation suite required reconstructing the committed runtime before execution; its initial missing-runtime error was resolved by that setup.

To capture a new append-only attempt, install requirements-civic-gps.txt and run `python candidates/texas_geometry_refresh/run_controls.py --output /absolute/new/attempt-directory`. The runner reconstructs the existing runtime and package in a temporary directory. It makes two public address geocodes and coordinate-only boundary requests, and never changes external source systems.
