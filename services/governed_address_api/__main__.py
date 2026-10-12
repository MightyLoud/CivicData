"""Launch the local adapter on 127.0.0.1."""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from services.governed_address_api.main import ROOT, create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        root = args.repo_root.resolve()
        if not root.is_dir():
            parser.error("--repo-root must name an existing directory")
        app = create_app(repo_root=root, timeout_seconds=args.timeout_seconds)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
