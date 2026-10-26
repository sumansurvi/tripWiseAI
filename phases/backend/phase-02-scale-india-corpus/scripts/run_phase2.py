#!/usr/bin/env python3
"""Phase 2 entrypoint: scale India Wikivoyage corpus (scope_root API and/or dump)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PHASE2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPO_ROOT / "phases" / "backend" / "phase-01-source-knowledge-foundation" / "scripts"

sys.path.insert(0, str(PHASE2_ROOT / "scripts"))
sys.path.insert(0, str(PHASE1_SCRIPTS))

# Phase 2 defaults — apply before loading settings
os.environ.setdefault("TRIPWISE_SCOPE_MODE", "scope_root")
os.environ.setdefault("TRIPWISE_SCOPE_ROOT", "India")
os.environ.setdefault("TRIPWISE_SEEDS", "India")
os.environ.setdefault("TRIPWISE_MAX_DEPTH", "12")
os.environ.setdefault("TRIPWISE_FOLLOW_GO_NEXT", "false")
os.environ.setdefault(
    "TRIPWISE_ALLOWED_PAGE_TYPES",
    "country,region,city,district,park,topic,airport,unknown",
)
os.environ.setdefault("TRIPWISE_SKIP_PAGE_TYPES", "itinerary,phrasebook")

from tripwise.config import load_settings
from tripwise.logging_utils import configure_logging
from tripwise.models import init_db, make_session_factory, Page
from tripwise.pipeline import run_ingestion
from tripwise.source_client import WikivoyageClient
from sqlalchemy import func, select

from tripwise_p2.dump_ingest import run_dump_ingestion


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TripWise Phase 2 — scale India destination corpus"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create PostgreSQL tables (same schema as Phase 1)")
    ingest_api = sub.add_parser(
        "ingest-api",
        help=(
            "Recommended: BFS from India via Action API (scope_root). "
            "Use --max-pages while testing; watch live progress lines."
        ),
    )
    ingest_api.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Safety cap (overrides TRIPWISE_MAX_PAGES)",
    )
    dump = sub.add_parser(
        "ingest-dump",
        help=(
            "Optional bulk path: two-pass ingest from a complete local "
            "enwikivoyage pages-articles XML(.bz2). Requires a full download first."
        ),
    )
    dump.add_argument("dump_path", type=Path, help="Path to pages-articles dump")
    dump.add_argument(
        "--max-scan",
        type=int,
        default=0,
        help="Optional scan limit for tests (0 = full dump)",
    )
    dump.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages to persist (overrides TRIPWISE_MAX_PAGES)",
    )
    sub.add_parser("inspect", help="Print stored page counts")
    sub.add_parser("coverage", help="India corpus coverage summary")
    args = parser.parse_args(argv)

    if args.command in {"ingest-api", "ingest-dump"} and args.max_pages is not None:
        os.environ["TRIPWISE_MAX_PAGES"] = str(args.max_pages)

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)

    if args.command == "init-db":
        init_db(settings.database_url)
        print("database initialized")
        return 0

    engine, factory = make_session_factory(settings.database_url)
    try:
        if args.command == "ingest-api":
            with factory() as session, WikivoyageClient(settings) as client:
                result = run_ingestion(session, settings, client)
            print(json.dumps(result.__dict__, indent=2))
            return 0 if result.status in {"COMPLETED", "PARTIAL"} else 1
        if args.command == "ingest-dump":
            if not args.dump_path.is_file():
                print(f"dump not found: {args.dump_path}", file=sys.stderr)
                return 1
            with factory() as session:
                result = run_dump_ingestion(
                    session, settings, args.dump_path, max_scan=args.max_scan
                )
            print(json.dumps(result.__dict__, indent=2, default=str))
            return 0 if result.status in {"COMPLETED", "PARTIAL"} else 1
        if args.command == "inspect":
            with factory() as session:
                pages = session.scalars(select(Page).order_by(Page.title)).all()
                print(
                    json.dumps(
                        {
                            "pages": len(pages),
                            "by_type": dict(
                                session.execute(
                                    select(Page.page_type, func.count(Page.id)).group_by(
                                        Page.page_type
                                    )
                                ).all()
                            ),
                            "titles_sample": [p.title for p in pages[:40]],
                        },
                        indent=2,
                    )
                )
            return 0
        if args.command == "coverage":
            with factory() as session:
                pages = session.scalars(select(Page)).all()
                print(
                    json.dumps(
                        {
                            "scope_root": settings.scope_root,
                            "scope_mode": settings.scope_mode,
                            "total_pages": len(pages),
                            "huge_cities": sum(1 for p in pages if p.is_huge_city),
                            "with_source_url": sum(
                                1 for p in pages if (p.canonical_url or "").strip()
                            ),
                            "by_type": dict(
                                session.execute(
                                    select(Page.page_type, func.count(Page.id)).group_by(
                                        Page.page_type
                                    )
                                ).all()
                            ),
                            "note": (
                                "Full India tree (~1000+ pages) expected after dump or "
                                "long scope_root API run. Outline pages stored as-is."
                            ),
                        },
                        indent=2,
                    )
                )
            return 0
    finally:
        engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
