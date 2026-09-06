# Texas bounded release authorization v0.1

Status: `RELEASE_AUTHORIZED__PUBLICATION_NOT_EXECUTED`

The bounded Texas runtime has passed merged-runtime release readiness and now has a separate governed release-authorization receipt.

Authorization receipt:

`data/packages/tx/legislative/release-authorization-v0.1.json`

Deterministic SHA-256:

`7bf9a8ecf9c101e9faee4389f925f469fd1d37934cc1d3dc9bfd6a890989d6de`

The receipt authorizes the release/publication **workflow layer** while explicitly preserving execution as a separate future decision:

- `release_authorized=true`;
- `publication_workflow_authorized=true`;
- `publication_execution_authorized=false`;
- `github_release_creation_authorized=false`;
- `railway_redeploy_authorized=false`;
- `canonical_writes=0`.

Authorization basis:

- runtime merged to `main`: `2570cba11d218ab32588a30ef6c43a7fce5c2f7c`;
- release-readiness SHA: `abeacad639da187818748c5af70e9df05fab27bf52101d270b7cd9c133f0c031`;
- post-activation hosted evidence SHA: `ed079fdfade76c06271f4b6be57fc669db7586b2ad66dc56ec13e3694f2abfb6`;
- service contract SHA: `ea4a5ab38550db2e8568c18c186ce9aa7393e6efc2ca4d41d1f9abaffb97638b`;
- package SHA: `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`;
- catalog entry SHA: `1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189`;
- legislative group SHA: `826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a`.

The authorized publication surface is the bounded runtime release only. Raw successor-package bytes remain outside the release surface, and neither source-package nor registry-layer publication eligibility is changed.
