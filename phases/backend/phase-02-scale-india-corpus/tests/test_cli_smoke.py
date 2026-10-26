"""Offline CLI smoke for Phase 2 entrypoint (no network)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_phase2.py"


def test_run_phase2_help_lists_ingest_api():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    out = completed.stdout + completed.stderr
    assert "ingest-api" in out
    assert "ingest-dump" in out
    assert "coverage" in out


def test_run_phase2_ingest_api_help():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "ingest-api", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "--max-pages" in (completed.stdout + completed.stderr)
