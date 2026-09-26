# SeeGov + Civic Mirror ↔ Shared Civic Spine v0.1

Status: **read-only partner integration; no canonical write-back**

## Bottom line

SeeGov and Civic Mirror attach product-native records to the shared representation spine through reviewed Organization/Person identity crosswalks. They do not become canonical representation authorities.

~~~text
SeeGov meetings / speakers              Civic Mirror evidence / bills / events
             |                                      |
             +---------- reviewed shared IDs --------+
                                |
                                v
                     Representation Contract v1
                                |
                     explicit representation
                         observation only
                                |
                                v
                    Partner Assertion v0.1
                                |
                    proposed / held for review
~~~

## Transport boundary

These adapters consume normalized snapshot JSON. The input can later come from an API, export, webhook, file, or connector without changing shared semantics.

Input schemas:

- `schemas/seegov_partner_snapshot_v0.1.schema.json`
- `schemas/civic_mirror_partner_snapshot_v0.1.schema.json`

No partner API shape is assumed by the shared contract.

## SeeGov ownership

SeeGov keeps ownership of meeting identity, source video, transcript and agenda links, moment/highlight annotations, meeting vote-outcome records, and speaker observations.

The adapter resolves exact reviewed crosswalks using `system = seegov`. A meeting/transcript alone creates no representation assertion. Only an explicit `representation_observation` is translated into Partner Assertion v0.1.

Membership/Post observations require an exact reviewed Person + Organization identity and a unique open Membership in the current Contract snapshot.

## Civic Mirror ownership

Civic Mirror keeps ownership of evidence records, editorial evidence tags, bill records, event records, and product-specific research/display metadata.

The adapter resolves exact reviewed crosswalks using `system = civic_mirror`. A Civic Mirror evidence item creates a shared assertion only when it explicitly carries a representation observation.

Editorial labels such as good/bad/questionable/neutral remain Civic Mirror metadata; they are never copied into the canonical representation layer merely because they are attached to evidence. Bills/events likewise remain product-native in this adapter.

## Target resolution

Partner observations can target `person`, `organization`, `membership`, or `post`. Resolution is ID-based:

~~~text
partner external Person ID -> reviewed per-... -> exactly one Contract Person
partner external Org ID    -> reviewed org-... -> exactly one Contract Organization
per-... + org-...          -> exactly one open Membership -> Membership or Post
~~~

No name matching is performed.

## Held observations

Identity/scope uncertainty produces `held_observations`, not malformed assertions. Typical reasons include `PERSON_IDENTITY_UNRESOLVED`, `ORGANIZATION_IDENTITY_UNRESOLVED`, `PERSON_SHARED_ID_OUT_OF_SCOPE`, `OPEN_MEMBERSHIP_NOT_FOUND`, and `OPEN_MEMBERSHIP_AMBIGUOUS`.

Held observations have zero canonical effect.

## Assertion governance

Resolved observations emit Partner Assertion v0.1 records with `review_status = proposed`, empty review history, and an explicitly supplied `base_snapshot_id`. Adapters never call promotion or certification functions.

## CLI — SeeGov

~~~bash
python adapters/seegov/adapter.py seegov-normalized-snapshot.json \
  --contract representation-contract.json \
  --identity-registry reviewed-shared-identity-registry.json \
  --base-snapshot-id snapshot-123 \
  --output seegov-integration.json
~~~

## CLI — Civic Mirror

~~~bash
python adapters/civic_mirror/adapter.py civic-mirror-normalized-snapshot.json \
  --contract representation-contract.json \
  --identity-registry reviewed-shared-identity-registry.json \
  --base-snapshot-id snapshot-123 \
  --output civic-mirror-integration.json
~~~

## Akron acceptance proof

The first acceptance case uses the governed Akron Board of Trustees, a reviewed shared Organization identity, Jared Jefferson's reviewed shared Person identity, and his open Trustee Membership.

The test proves:

- SeeGov meeting body and speaker resolve through reviewed IDs;
- explicit `membership.label = Mayor Pro Tem` becomes a valid proposed assertion;
- an unreviewed SeeGov speaker is held as an identity conflict;
- transcript/moment/vote records stay SeeGov-owned;
- Civic Mirror official evidence resolves through shared identity;
- an explicit Person observation becomes a valid proposed assertion;
- Civic Mirror editorial tags are preserved but never promoted;
- Civic Mirror bills/events stay product-owned;
- missing partner crosswalks are held, never name-matched;
- all canonical write counts remain zero.

## Write boundary

~~~text
SeeGov shared canonical writes       = 0
Civic Mirror shared canonical writes = 0
identity registry writes             = 0
Factory writes                       = 0
CivicPatch writes                    = 0
canonical_writes                     = 0
~~~

Identity changes use the shared identity-registry review flow. Representation fact changes use partner-assertion review and copy-on-write promotion. Geography identity uses the OCDID validation flow.

## Canonical-core assertion IDs

Partner assertions target Canonical Representation Core primary keys, not Contract v1 projection UUIDs.

Factory-backed Contract v1 records carry their promotable core IDs in external identifiers:

- Organization → `civicdata_factory_body` → canonical `organization_id`
- Person → `civicdata_factory_person` → canonical `person_id`
- Post → `civicdata_factory_office` → canonical `post_id`
- Membership → `civicdata_factory_role_term` → canonical `membership_id`

If a resolved Contract record does not expose a canonical-core subject ID, the observation is held with `CANONICAL_SUBJECT_ID_UNAVAILABLE`. The adapter does not emit an assertion that the promotion workflow cannot target.

The Akron acceptance suite reviews a SeeGov Membership assertion and promotes it directly against `tools/canonical_representation_core.from_jurisdiction_package(...)`, proving the adapter output is compatible with the canonical copy-on-write governance path.
