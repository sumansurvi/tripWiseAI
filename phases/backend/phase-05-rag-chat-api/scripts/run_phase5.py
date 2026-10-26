#!/usr/bin/env python3
"""Phase 5 entrypoint: serve FastAPI RAG chat."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PHASE5_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND = REPO_ROOT / "phases" / "backend"

# Phase 3 retrieve + Phase 5 app + Phases 6–9 used by rag.py
_SCRIPT_DIRS = [
    PHASE5_ROOT / "scripts",
    BACKEND / "phase-03-embeddings-vector-store" / "scripts",
    BACKEND / "phase-06-query-routing" / "scripts",
    BACKEND / "phase-07-hybrid-retrieval" / "scripts",
    BACKEND / "phase-08-conversation" / "scripts",
    BACKEND / "phase-09-comparison-recommendations" / "scripts",
]
for _d in reversed(_SCRIPT_DIRS):
    p = str(_d)
    if p not in sys.path:
        sys.path.insert(0, p)

from tripwise_p3.warnings_util import suppress_vendor_noise

suppress_vendor_noise(quiet_http_logs=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TripWise Phase 5 — RAG chat API (Gemini retrieve → Groq)"
    )
    parser.add_argument("--host", default=None, help="Bind host (default from env)")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    args = parser.parse_args(argv)

    from tripwise_p5.config import load_settings

    settings = load_settings()
    from tripwise_p3.config import is_local_provider

    if not is_local_provider(settings.embedding_provider) and not settings.gemini_api_key:
        print(
            "GEMINI_API_KEY is missing in config/.env "
            "(needed when TRIPWISE_EMBEDDING_PROVIDER=gemini).",
            file=sys.stderr,
        )
        return 1
    if not settings.groq_api_key:
        print(
            "GROQ_API_KEY is missing in config/.env (needed for chat generation).\n"
            "Create a key at https://console.groq.com/keys",
            file=sys.stderr,
        )
        return 1

    host = args.host or settings.host
    port = args.port or settings.port

    import uvicorn
    from tripwise_p5.app import create_app

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    app = create_app(settings)
    print(f"TripWise API  http://{host}:{port}  (POST /chat)", flush=True)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
