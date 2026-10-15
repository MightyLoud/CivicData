# Pinned hosted launcher candidate

Build and smoke-test only; no deployment or pilot activation. The image reuses the existing governed address API at commit e9c11f26c0cec8acd409d92f4d4867b5ee5715f7. `/readyz` checks repository integrity only, not upstream data readiness. Pilot representation remains held with HTTP 503.

Run `python verify_container.py` from a Docker-enabled Linux amd64 host. Dependencies require CPython 3.12 and the supplied wheel hashes. The base image is digest pinned; apt/git build inputs are not fully locked. CI runs nine launcher checks against a separate pinned checkout, builds the image, checks HTTP liveness/readiness and the held pilot route, and uploads receipts. It does not establish hosted parity or approve production.
