#!/usr/bin/env python3
"""Fetch Wikivoyage pages via the Action API (httpx).

This is not Playwright / browser scraping. Use ingest/export-data for full
Postgres + data/raw|structured|chunks JSON. --save-wiki only dumps plain .wiki.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PHASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PHASE_ROOT / "scripts"))

from tripwise.config import DATA_DIR, load_settings
from tripwise.logging_utils import configure_logging
from tripwise.source_client import WikivoyageClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl / fetch Wikivoyage pages")
    parser.add_argument(
        "titles",
        nargs="*",
        help="Page titles (default: configured TRIPWISE_SEEDS)",
    )
    parser.add_argument(
        "--save-wiki",
        action="store_true",
        help="Also write plain .wiki files under data/raw/wiki/ (JSON export happens on ingest)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)
    titles = args.titles or list(settings.seeds)
    wiki_dir = DATA_DIR / "raw" / "wiki"
    if args.save_wiki:
        wiki_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    with WikivoyageClient(settings) as client:
        for page in client.fetch_pages(titles):
            if args.save_wiki and page.wikitext is not None and not page.missing:
                safe = page.title.replace("/", "__").replace(" ", "_")
                (wiki_dir / f"{safe}.wiki").write_text(page.wikitext, encoding="utf-8")

            if page.missing:
                summaries.append(
                    {
                        "title": page.title,
                        "requested_title": page.requested_title,
                        "missing": True,
                        "source_url": None,
                    }
                )
                continue

            summaries.append(
                {
                    "title": page.title,
                    "wiki_page_id": page.wiki_page_id,
                    "revision_id": page.revision_id,
                    "source_url": page.canonical_url,
                    "wikitext_chars": len(page.wikitext or ""),
                }
            )
    print(json.dumps({"fetched": len(summaries), "pages": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
