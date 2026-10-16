# Factory export certification review

A normalized Factory source change can inherit historical `certified` gates and verification dates through the existing exporter. Export generation alone must not be treated as a new certification review. This additive review module leaves the legacy exporter and all runtime entry points unchanged.

`tools.factory_export_review.prepare_review(package, prior_contract, generated_at=...)` validates the strict source shape and prior contract, prepares a separate draft, clears its inherited verification time, and binds source/prior/draft canonical-JSON SHA-256 fingerprints. Existing assertions retain their original assertion and review timestamps; changed existing assertion content is rejected for separate reconciliation. New assertions receive no inferred assertion or review timestamp. Generating a draft is not an evidence observation or acceptance event.

`apply_certification(review, decision, source_package=..., history=...)` requires explicit approval for `FULL_RUNTIME_CONTRACT`, matching source/prior/draft fingerprints, a named reviewer under `civicdata_certification`, a timezone-aware verification time no earlier than draft generation, a reason, evidence references and all four boolean gates explicitly true. It reuses the shared governance certification helper. Returned history appends the exact decision and resulting contract fingerprint to a separate sidecar; it does not add fields to the runtime schema. The caller must retain this sidecar. Input objects remain unchanged. Runtime publication and activation remain false.

The decision is trusted caller input, not an authentication credential or cryptographic signature. The caller must verify reviewer identity/authority and gate evidence independently and supply the current source package; the module validates it and rejects a source fingerprint mismatch. The helper does not independently fetch evidence, establish freshness, authenticate a user, publish, or write canonical files. History is supplied and retained by the caller; the module does not provide a persistent append-only database or validate old historical entries.

## Alamosa review boundary

Creyton confirmed reviewer authority and accepted the retained official extract for Liz Hensley's Mayor Pro Tem title observation at the October 16 capture. That is bounded evidence acceptance, **not** approval of a full runtime-contract certification. Exact leadership dates remain unknown. It must not be passed as a `FULL_RUNTIME_CONTRACT` approval. No actual certification is executed by this PR; positive certification tests use a synthetic reviewer and fixture decision only.

A full-contract decision still needs scope-wide evidence review and explicit approval. Alternatives include retaining the corrected source and draft while historical runtime contracts remain fixed. Public activation and runtime publication require their own decisions.

## Checks

The seven unit tests exercise real Alamosa source/draft preparation, uncertified consumer rejection, preserved timestamps, synthetic full-contract certification with sidecar history, twelve incomplete gate controls, eleven approval/authority/metadata/hash controls, backdated review rejection, changed source/draft rejection and changed prior assertion rejection. CI runs these with existing governance/export/contract/role tests. No new certified runtime artifact is committed.
