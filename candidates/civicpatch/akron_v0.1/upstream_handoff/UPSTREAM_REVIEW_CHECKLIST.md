# Akron upstream review checklist

## Base

- [ ] Confirm `main` is still based on or compatible with `69331c2b0d97e13695dab07ec1d6a969c99a3e4d`.
- [ ] Confirm `data/co/local/place_akron.yml` still has blob SHA `3c335cac8e5d07fb18b67db70aa12c7dc1d7a7d7`, or rebase the candidate first.

## Data review

- [ ] Confirm the current official Town roster lists the seven proposed people.
- [ ] Retain the existing CivicPatch IDs for Braden Brent, Crystann Benson, and Jared Jefferson.
- [ ] Review or remint the four proposed IDs for Annette Bowin, Joe Tarnow, Ron Kraich, and Terry Alexander.
- [ ] Confirm Jared Jefferson is represented formally as Trustee; treat Mayor Pro Tem as internal leadership.
- [ ] Confirm no exact term dates should be inferred from published expiration years.
- [ ] Treat omitted old roster rows as historical/stale-roster removal from this current file, not Person-identity deletion.

## CivicPatch validation

Run from the CivicPatch/open-data checkout:

```bash
uv run python scripts/github_actions/validate_jurisdiction.py "ocd-jurisdiction/country:us/state:co/place:akron/government"
```

- [ ] CivicPatch schema validation passes.
- [ ] Review the full YAML diff.
- [ ] Confirm no unrelated jurisdiction files changed.

## Provenance

- [ ] Board roster source reviewed.
- [ ] Board-composition code source reviewed.
- [ ] Mayor-Pro-Tem code source reviewed.

## Publication

- [ ] Maintainer approves proposed/new person IDs.
- [ ] Maintainer confirms replacement-file workflow is appropriate.
- [ ] Only then merge/publish upstream.
