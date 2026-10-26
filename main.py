#!/usr/bin/env python3
"""TripWise AI — start the RAG chat API.

Thin entrypoint: delegates to Phase 5 (`run_phase5.py`). Pipeline tools
(ingest, embed, scheduler) stay under `phases/backend/`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RUN_PHASE5 = (
    REPO_ROOT
    / "phases"
    / "backend"
    / "phase-05-rag-chat-api"
    / "scripts"
    / "run_phase5.py"
)


def main(argv=None) -> int:
    spec = importlib.util.spec_from_file_location("tripwise_run_phase5", RUN_PHASE5)
    if spec is None or spec.loader is None:
        print(f"Cannot load {RUN_PHASE5}", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
