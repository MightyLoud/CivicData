from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import run_mb100_detroit as runner

# Match the clean MB100-014 RUN START captured in the command center.
runner.FIXED_ASOF = datetime(2026, 8, 6, 14, 35, 33, tzinfo=UTC)


if __name__ == "__main__":
    asyncio.run(runner.main())
