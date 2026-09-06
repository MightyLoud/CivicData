# Texas bounded legislative successor package v0.1

Status: `SUCCESSOR_PACKAGE_ACTIVE_BOUNDED`

Issued: September 6, 2026.

This artifact superseded the package bytes of the earlier provisional-identity Texas House District 49 / Senate District 14 candidate. The package itself remains byte-preserved after repository activation; activation is recorded separately and does not rewrite historical package or acceptance metadata.

## Current bounded package

Profile: `tx_legislative_two_office_v0.1`

Coverage:

- Texas House District 49;
- Texas Senate District 14;
- both bindings required atomically;
- representation only;
- omitted data means `NOT_INCLUDED_NOT_ABSENT`;
- `complete_jurisdiction=false`;
- Full Essentials unsupported;
- election scope unsupported.

The package contains exactly two canonical Divisions, two Offices, two AUTHORITATIVE Persons, and two CURRENT RoleTerms. Both RoleTerms start `2025-01-14`; actual end dates remain unknown/blank.

## Bounded QA and limitations

`parity_ok=true` and `qa_fail_count=0` apply to the exact exported two-chain graph. Five bounded limitations remain visible:

1. `BOUNDED_TWO_OFFICE_SCOPE`;
2. `SOURCE_PACKAGE_ADDRESS_CONTROLS_EXTERNAL`;
3. `FULL_TEXAS_ROSTER_NOT_INCLUDED`;
4. `FULL_ESSENTIALS_UNSUPPORTED`;
5. `ELECTION_SCOPE_UNSUPPORTED`.

Activation does not clear or relabel these limitations.

## Package hashes

- `jurisdiction.json`: `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`;
- deterministic package ZIP: `7b6abf28e0535041797b180488cb98ebf223b844b3081e7386ccbd63c85762b1`;
- acceptance receipt file: `3b204dc1d7c4c9442bf61fe422f3de907dfed0bd567ae15ffa6e853ab5399f96`;
- acceptance deterministic digest: `f58251a3a127841ec1773a342336d01145aca47d61957ea4bfd1e81121266483`.

Historical live evidence remains reusable only for geography under:

`GEOGRAPHY_ONLY__NO_OLD_REPRESENTATION_REPLAY`

Old provisional representation output is not replayed as current civic fact evidence.

## Activation

The successor package subsequently passed independent hosted production validation and the activation-readiness gate.

Hosted validation SHA-256:

`890073c847d9477c1a3c75d4228b5758d76a338954200d597577bc8a73396e37`

Readiness receipt SHA-256:

`be8e3435dc07fd8918e80212e60758b08e45ee97bf981fad821d4f2f7d8019d8`

The user then separately authorized repository activation. The exact package is now referenced by the default bounded Texas catalog entry and the exact House/Senate geography group is present in the default registry.

Activation moment:

`2d56d3ee1247be470c066df4b4321fd8e4679698`

Activation receipt:

`data/packages/tx/legislative/activation-v0.1.json`

Activation receipt SHA-256:

`8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166`

`tests/test_tx_successor_package.py` verifies the committed package/receipt hashes and now also requires the default catalog to contain exactly the certified successor entry and reconstruct exactly these package bytes.

Current disposition:

`SUCCESSOR_PACKAGE = ACTIVE_BOUNDED`

`REPOSITORY_ACTIVATION = ACTIVATED_BOUNDED`

`MERGE = NOT_AUTHORIZED`

`RELEASE = NOT_AUTHORIZED`

`CANONICAL_WRITES = 0`
