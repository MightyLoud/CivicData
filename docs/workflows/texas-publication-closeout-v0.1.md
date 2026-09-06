# Texas bounded publication closeout v0.1

Status: `PUBLISHED_CERTIFIED`

This closeout certifies the already-published manifest-only GitHub Release for the bounded Texas House District 49 + Senate District 14 representation profile. It does **not** edit, replace, delete, republish, or otherwise mutate the release.

## Certified release

- release ID: `383744766`
- tag: `tx-legislative-two-office-v0.1`
- title: `Texas bounded legislative representation v0.1`
- release target: `defefa6d31987187839fa90434b201a287518e34`
- execution head: `d9045f5ae176d13b6226a4e7159e63702be5bdd8`
- published: `2026-09-06T23:07:32Z`
- draft: `false`
- prerelease: `false`

The observed GitHub release state is frozen in:

`data/packages/tx/legislative/publication-release-snapshot-v0.1.json`

Snapshot deterministic SHA-256:

`7ccba5503099d5292b4f7cfd4b46c4dd64d331b9e854ed6f9f1d50015581b9ed`

## Asset certification

Exactly one governed release asset is present:

`texas-bounded-runtime-release-manifest-v0.1.json`

- GitHub-reported size: **1,766 bytes**
- GitHub-reported SHA-256: `80bcb6f3d4d668ce62af84450b1db726156c0beaf7bc24b053b8c6291704cffe`
- reconstructed size: **1,766 bytes**
- reconstructed SHA-256: `80bcb6f3d4d668ce62af84450b1db726156c0beaf7bc24b053b8c6291704cffe`
- manifest internal deterministic SHA-256: `4d04488a9f191c048cc647737f3bea2e3631dd2159ee43a3df36a6445bcf40a1`

The reconstructed bytes are generated from the committed release authorization and publication execution receipt using the repository's canonical JSON routine. The reconstructed byte digest exactly matches GitHub's release-asset digest.

## Closeout receipt

`data/packages/tx/legislative/publication-closeout-v0.1.json`

Deterministic SHA-256:

`fb82a0831ae9c8eb24af66543f8b2db49820ded2b5145b9e5ff5b3f907e67bb3`

The closeout preserves:

- scope: House District 49 ∩ Senate District 14 only;
- both bindings required;
- `complete_jurisdiction=false`;
- Full Essentials unsupported;
- elections unsupported;
- raw successor-package bytes not published;
- source-package publication eligibility remains false;
- registry publication eligibility remains false;
- canonical writes: `0`.

## Runtime boundary

The Railway production service remained unchanged during publication and certification:

`bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67`

No Railway redeploy was authorized or performed by the publication or closeout phases.

## Verification

Offline verifier:

```sh
python tools/texas_publication_closeout.py
```

Tests:

```sh
python tests/test_texas_publication_closeout.py
```

CI workflow:

`.github/workflows/texas-publication-closeout.yml`

The closeout CI has read-only repository permissions and performs no release mutation.
