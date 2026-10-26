#!/usr/bin/env python3
"""Parse a Wikivoyage wikitext file into sections, listings, and relationships."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PHASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PHASE_ROOT / "scripts"))

from tripwise.extract import extract_page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse Wikivoyage wikitext")
    parser.add_argument("path", type=Path, help="Path to a .wiki file")
    parser.add_argument(
        "--title",
        help="Page title (default: inferred from filename)",
    )
    args = parser.parse_args(argv)

    path: Path = args.path
    if not path.is_file():
        print(f"file not found: {path}", file=sys.stderr)
        return 1

    title = args.title or path.stem.replace("__", "/").replace("_", " ")
    extracted = extract_page(title, path.read_text(encoding="utf-8"))
    payload = {
        "title": extracted.title,
        "page_type": extracted.page_type,
        "article_status": extracted.article_status,
        "parent_title": extracted.parent_title,
        "is_huge_city": extracted.is_huge_city,
        "lead_text": (extracted.lead_text or "")[:300],
        "section_count": len(extracted.sections),
        "listing_count": len(extracted.listings),
        "listing_kinds": sorted({lst.listing_kind for lst in extracted.listings}),
        "relationships": [
            {"to_title": r.to_title, "relationship_type": r.relationship_type}
            for r in extracted.relationships[:20]
        ],
        "sample_listings": [
            {"kind": lst.listing_kind, "name": lst.name}
            for lst in extracted.listings[:10]
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
