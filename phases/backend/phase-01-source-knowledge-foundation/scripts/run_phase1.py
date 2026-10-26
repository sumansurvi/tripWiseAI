#!/usr/bin/env python3
"""Phase 1 entrypoint: init-db / ingest / inspect / quality / export-data."""

from __future__ import annotations

import sys
from pathlib import Path

PHASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PHASE_ROOT / "scripts"))

from tripwise.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
