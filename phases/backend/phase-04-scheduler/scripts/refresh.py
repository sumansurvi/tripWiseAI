#!/usr/bin/env python3
"""Alias for Phase 4 one-shot refresh (same orchestrator as `run_phase4.py tick`)."""

from __future__ import annotations

import sys
from pathlib import Path

# Re-export tick via run_phase4
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_phase4 import main

if __name__ == "__main__":
    raise SystemExit(main(["tick"]))
