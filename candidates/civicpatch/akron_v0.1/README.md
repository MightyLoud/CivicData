# Akron CivicPatch partner-ready candidate v0.1

Target file if CivicPatch accepts the candidate:

```text
CivicPatch/open-data:data/co/local/place_akron.yml
```

Pinned target state:

```text
CivicPatch/open-data@69331c2b0d97e13695dab07ec1d6a969c99a3e4d
```

## Reviewed identity disposition

Retain existing CivicPatch IDs:

- Braden Brent — `d31247df-3332-490e-b45d-fa8e7bb55e0b`
- Crystann Benson — `623089fb-bd23-4615-a440-1a61da966c15`
- Jared Jefferson — `dd07c3f5-1432-4c30-9bc9-9f73bb3385c2`

Jared's formal published role is corrected to **Trustee**. Mayor Pro Tem is
preserved as an internal leadership fact in the reconciliation receipt, not
published as a separate formal office.

New current officials remain preview identities pending CivicPatch acceptance:

- Annette Bowin
- Joe Tarnow
- Ron Kraich
- Terry Alexander

Pinned CivicPatch rows omitted from the replacement candidate because they are
not on the current official Town roster:

- Brandon Hill
- Ariella Gonzales-Vondy
- David Kembel
- Jennifer Hansen

Omission from this roster candidate is **not** a canonical Person deletion.

## Evidence

Current official sources reviewed for this candidate:

- https://www.townofakron.com/172/Board-of-Trustees
- https://codelibrary.amlegal.com/codes/akron_co/latest/akron_co/0-0-0-134
- https://codelibrary.amlegal.com/codes/akron_co/latest/akron_co/0-0-0-127

The detailed reviewed crosswalk is:

```text
acceptance/civicpatch/akron_identity_reconciliation_v0.1.json
```

## Files

`place_akron.yml` is the partner-ready replacement candidate.

The generator also produces a bundle, manifest, and action receipt during CI.
Tests require the committed YAML to match the deterministic generator output.

No upstream CivicPatch write is authorized by this artifact.
