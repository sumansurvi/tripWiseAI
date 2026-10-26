#!/usr/bin/env python3
"""Phase 3 entrypoint: init-db | embed | retrieve | calibrate-gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PHASE3_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PHASE3_ROOT / "scripts"))

from tripwise_p3.warnings_util import suppress_vendor_noise

suppress_vendor_noise(quiet_http_logs=True)

from tripwise_p3.calibrate import calibrate_gate, suggestion_to_jsonable
from tripwise_p3.config import is_local_provider, load_settings
from tripwise_p3.embed_index import print_embed_message, run_embed_index
from tripwise_p3.embedding_client import make_embedding_client
from tripwise_p3.models import init_db, make_session_factory
from tripwise_p3.retrieve import hits_to_jsonable, retrieve


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "TripWise Phase 3 — embeddings → pgvector "
            "(local bge default; Gemini optional; Groq is chat only)"
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "init-db",
        help="CREATE EXTENSION vector + create rag_documents / rag_chunks",
    )
    sub.add_parser(
        "embed",
        help="chunk_embed_index: embed data/chunks into pgvector (skips unchanged hashes)",
    )
    ret = sub.add_parser(
        "retrieve",
        help="Semantic top-k over stored embeddings (no LLM generation)",
    )
    ret.add_argument("query", help="Natural-language query, e.g. 'Old Delhi eat'")
    ret.add_argument("--top-k", type=int, default=5, help="Number of hits (default 5)")
    cal = sub.add_parser(
        "calibrate-gate",
        help="Print a suggested TRIPWISE_CHAT_MIN_SCORE from eval fixture queries",
    )
    cal.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Hits per query when measuring best cosine (default 5)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()

    if args.command == "init-db":
        try:
            init_db(settings.database_url, embedding_dim=settings.embedding_dim)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("database initialized (vector extension + rag_* tables)")
        return 0

    local = is_local_provider(settings.embedding_provider)
    if args.command in {"embed", "retrieve", "calibrate-gate"} and not local:
        if not settings.gemini_api_key:
            print(
                "GEMINI_API_KEY is missing or empty in config/.env.\n"
                "Create a key at https://aistudio.google.com/apikey and set:\n"
                "  GEMINI_API_KEY=your_key_here\n"
                "  GEMINI_EMBEDDING_MODEL=gemini-embedding-001\n"
                "Or set TRIPWISE_EMBEDDING_PROVIDER=local to embed on this machine.",
                file=sys.stderr,
            )
            return 1

    if args.command == "embed":
        try:
            client = make_embedding_client(
                settings,
                probe=not local,
                on_rate_limited=lambda secs: print_embed_message(
                    f"retrying; sleeping {secs:.0f}s"
                ),
            )
        except (RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        engine, factory = make_session_factory(settings.database_url)
        try:
            with factory() as session:
                result = run_embed_index(session, settings, client)
            print(json.dumps(result.__dict__, indent=2))
            return 0 if result.status in {"COMPLETED", "PARTIAL"} else 1
        finally:
            engine.dispose()

    if args.command == "retrieve":
        try:
            client = make_embedding_client(settings, probe=False)
        except (RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        engine, factory = make_session_factory(settings.database_url)
        try:
            with factory() as session:
                hits = retrieve(session, client, args.query, top_k=args.top_k)
            print(json.dumps(hits_to_jsonable(hits), indent=2))
            return 0
        finally:
            engine.dispose()

    if args.command == "calibrate-gate":
        try:
            client = make_embedding_client(settings, probe=False)
        except (RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        engine, factory = make_session_factory(settings.database_url)
        try:
            with factory() as session:
                suggestion = calibrate_gate(
                    session, client, top_k=args.top_k
                )
            print(json.dumps(suggestion_to_jsonable(suggestion), indent=2))
            return 0
        finally:
            engine.dispose()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
