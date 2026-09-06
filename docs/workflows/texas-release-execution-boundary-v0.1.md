# Texas bounded publication execution boundary v0.1

Publication execution is **not authorized** by the release-authorization phase.

A later execution phase must create:

`data/packages/tx/legislative/publication-execution-authorization-v0.1.json`

with schema:

`texas-bounded-publication-execution/0.1`

The execution receipt must bind to the exact publication `main` SHA, the governed tag `tx-legislative-two-office-v0.1`, and release-authorization digest `7bf9a8ecf9c101e9faee4389f925f469fd1d37934cc1d3dc9bfd6a890989d6de`.

Only that future receipt may set:

- `execution_authorized=true`;
- `github_release_creation_authorized=true`.

It must continue to preserve:

- `railway_redeploy_authorized=false`;
- `canonical_writes=0`.

Until that receipt exists, the publication workflow's `publish` job is intentionally non-executable.
