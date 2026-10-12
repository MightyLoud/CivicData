#!/usr/bin/env python3
"""ArcGIS smoke shares current controls and exact-office acceptance assertions."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.governed_geocoding_live_probe import main


if __name__ == "__main__":
    raise SystemExit(main())
