from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import func, select

from tripwise.config import load_settings
from tripwise.export_json import export_from_db_page
from tripwise.logging_utils import configure_logging
from tripwise.models import (
    IngestionError,
    IngestionRun,
    Listing,
    Page,
    PageRelationship,
    PageSection,
    init_db,
    make_session_factory,
)
from tripwise.pipeline import run_ingestion
from tripwise.source_client import WikivoyageClient

# Architecture hard rules (docs/RAG_ARCHITECTURE.md) — Phase 1 surfaces these in quality.
ARCHITECTURE_RULES = {
    "chat_llm": "Groq",
    "embeddings": "Gemini → pgvector (Phase 3); chat (Groq) must retrieve these before generating",
    "no_standalone_llm_answers": (
        "The chatbot must not answer from model memory alone. "
        "Every travel claim requires retrieved embedding-backed chunks (or stored SQL rows). "
        "Empty retrieval → refuse / I don't know."
    ),
    "citation": (
        "Every user-facing answer must cite Wikivoyage source_url(s) from retriever metadata. "
        "Never invent a URL."
    ),
    "personal_information": (
        "Out of scope. Refuse passport/ID/bank/medical/private contact / 'what is my …' questions. "
        "Do not invent personal data."
    ),
    "acquisition": "Wikivoyage Action API (httpx). Not Playwright / HTML scrape.",
}

QUERY_COVERAGE = [
    ("Tell me about Jaipur.", ["Jaipur"], ["Lead", "Understand"]),
    ("What are the major attractions in Jaipur?", ["Jaipur"], ["See"]),
    ("What can I do in Delhi?", ["Delhi", "Delhi/Old Delhi", "Delhi/South"], ["Do", "See"]),
    ("How do I get around Delhi?", ["Delhi"], ["Get around"]),
    ("How do I travel from Delhi to Agra?", ["Delhi", "Agra", "India"], ["Get in", "Get around"]),
    ("Which Delhi neighborhoods should I consider?", ["Delhi"], ["Districts", "Understand"]),
    ("Which area should I stay in Mumbai?", ["Mumbai", "Mumbai/South", "Mumbai/Fort"], ["Sleep"]),
    ("What food should I try in Varanasi?", ["Varanasi"], ["Eat"]),
    ("What should I buy in Jaipur?", ["Jaipur"], ["Buy"]),
    ("Where can I experience nightlife in Mumbai?", ["Mumbai", "Mumbai/South", "Mumbai/Fort"], ["Drink"]),
    ("Why is Varanasi culturally significant?", ["Varanasi"], ["Understand"]),
    ("What should I know before visiting India?", ["India"], ["Stay safe", "Cope", "Respect", "Connect"]),
    ("When is a good time to visit India?", ["India", "Delhi", "Goa"], ["Understand"]),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TripWise Phase 1 Wikivoyage ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create PostgreSQL tables")
    sub.add_parser("ingest", help="Run controlled ingestion (+ write data JSON)")
    sub.add_parser("inspect", help="Print stored page/section/listing counts")
    sub.add_parser("quality", help="Print data-quality checks with source URLs")
    sub.add_parser("export-data", help="Rebuild data/raw|structured|chunks from Postgres")
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)

    if args.command == "init-db":
        init_db(settings.database_url)
        print("database initialized")
        return 0

    engine, factory = make_session_factory(settings.database_url)
    try:
        if args.command == "ingest":
            with factory() as session, WikivoyageClient(settings) as client:
                result = run_ingestion(session, settings, client)
            print(json.dumps(result.__dict__, indent=2))
            return 0 if result.status in {"COMPLETED", "PARTIAL"} else 1
        if args.command == "inspect":
            with factory() as session:
                print(json.dumps(_inspect(session), indent=2, default=str))
            return 0
        if args.command == "quality":
            with factory() as session:
                print(json.dumps(_quality(session), indent=2, default=str))
            return 0
        if args.command == "export-data":
            with factory() as session:
                print(json.dumps(_export_data(session), indent=2))
            return 0
    finally:
        engine.dispose()
    return 1


def _inspect(session) -> dict:
    pages = session.scalars(select(Page).order_by(Page.title)).all()
    return {
        "pages": len(pages),
        "sections": session.scalar(select(func.count(PageSection.id))),
        "listings": session.scalar(select(func.count(Listing.id))),
        "relationships": session.scalar(select(func.count(PageRelationship.id))),
        "latest_run": _latest_run(session),
        "page_summaries": [
            {
                "title": p.title,
                "page_type": p.page_type,
                "article_status": p.article_status,
                "parent_title": p.parent_title,
                "is_huge_city": p.is_huge_city,
                "revision_id": p.revision_id,
                "sections": len(p.sections),
                "listings": len(p.listings),
                "listing_kinds": sorted({lst.listing_kind for lst in p.listings}),
                "source_url": p.canonical_url,
            }
            for p in pages
        ],
    }


def _latest_run(session) -> dict | None:
    run = session.scalar(select(IngestionRun).order_by(IngestionRun.started_at.desc()))
    if not run:
        return None
    errors = session.scalars(
        select(IngestionError).where(IngestionError.run_id == run.id)
    ).all()
    return {
        "id": run.id,
        "status": run.status,
        "pages_discovered": run.pages_discovered,
        "pages_processed": run.pages_processed,
        "pages_succeeded": run.pages_succeeded,
        "pages_failed": run.pages_failed,
        "pages_skipped": run.pages_skipped,
        "records_created": run.records_created,
        "records_updated": run.records_updated,
        "records_unchanged": run.records_unchanged,
        "duration_ms": run.duration_ms,
        "errors": [
            {"title": e.page_title, "type": e.error_type, "operation": e.operation}
            for e in errors
        ],
    }


def _quality(session) -> dict:
    pages = {p.title: p for p in session.scalars(select(Page)).all()}
    coverage = []
    for question, titles, sections in QUERY_COVERAGE:
        found_pages = [t for t in titles if t in pages]
        found_sections = []
        for title in found_pages:
            names = {s.section_title for s in pages[title].sections}
            found_sections.extend(sorted(names.intersection(sections)))
        listing_support = []
        for title in found_pages:
            listing_support.extend(sorted({lst.listing_kind for lst in pages[title].listings}))
        source_urls = [pages[t].canonical_url for t in found_pages if pages[t].canonical_url]
        coverage.append(
            {
                "question": question,
                "pages_present": found_pages,
                "source_urls": source_urls,
                "matching_sections": sorted(set(found_sections)),
                "listing_kinds": sorted(set(listing_support)),
                "supported": bool(found_pages and (found_sections or listing_support)),
            }
        )

    kind_counts = dict(
        session.execute(
            select(Listing.listing_kind, func.count(Listing.id)).group_by(Listing.listing_kind)
        ).all()
    )
    type_counts = dict(
        session.execute(select(Page.page_type, func.count(Page.id)).group_by(Page.page_type)).all()
    )
    return {
        "architecture_rules": ARCHITECTURE_RULES,
        "citation_rule": ARCHITECTURE_RULES["citation"],
        "pages_missing_source_url": [
            p.title for p in pages.values() if not (p.canonical_url or "").strip()
        ],
        "page_type_counts": type_counts,
        "listing_kind_counts": kind_counts,
        "query_coverage": coverage,
        "unsupported_examples": [
            {
                "question": "Which Delhi hotel costs ₹5,000 tonight?",
                "supported": False,
                "source_urls": [],
                "reason": "Wikivoyage has no live hotel inventory or nightly INR prices.",
            },
            {
                "question": "What is my passport number?",
                "supported": False,
                "source_urls": [],
                "reason": (
                    "Personal information is out of scope for TripWise. "
                    "Refuse; do not answer from the LLM."
                ),
            },
            {
                "question": "Tell me something interesting (no destination / no retrieved chunks).",
                "supported": False,
                "source_urls": [],
                "reason": (
                    "No standalone LLM answers. Without retrieved embedding-backed "
                    "Wikivoyage chunks, reply I don't know."
                ),
            },
        ],
    }


def _export_data(session) -> dict:
    pages = session.scalars(select(Page).order_by(Page.title)).all()
    written = []
    for page in pages:
        paths = export_from_db_page(page)
        written.append(
            {
                "title": page.title,
                "source_url": page.canonical_url,
                "raw": str(paths["raw"]),
                "structured": str(paths["structured"]),
                "chunks": str(paths["chunks"]),
            }
        )
    return {"exported": len(written), "pages": written}


if __name__ == "__main__":
    sys.exit(main())
