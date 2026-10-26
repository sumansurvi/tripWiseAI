"""Write Wikivoyage-derived JSON under data/raw, data/structured, data/chunks."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Silence unused — PROJECT_ROOT re-exported for callers
from tripwise.config import DATA_DIR, PROJECT_ROOT  # noqa: F401
from tripwise.extract import ExtractedPage
from tripwise.persist import LICENSE_NAME, LICENSE_URL, SOURCE_HOME, WIKIVOYAGE_SOURCE_ID, attribution_for
from tripwise.source_client import RetrievedPage


def title_slug(title: str) -> str:
    return re.sub(r"[^\w.-]+", "_", title.replace("/", "__").strip()) or "page"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _source_block() -> dict[str, str]:
    return {
        "id": WIKIVOYAGE_SOURCE_ID,
        "name": "English Wikivoyage",
        "base_url": SOURCE_HOME,
        "license_name": LICENSE_NAME,
        "license_url": LICENSE_URL,
    }


def export_page_json(
    retrieved: RetrievedPage,
    extracted: ExtractedPage,
    *,
    data_dir: Path | None = None,
) -> dict[str, Path]:
    """Write raw, structured, and chunks JSON for one page. Returns written paths.

    Architecture: every artifact must include a real Wikivoyage source_url
    (canonical_url from the Action API). Never invent a URL.
    """
    if not (retrieved.canonical_url or "").strip():
        raise ValueError(
            f"Refusing to export {retrieved.title!r}: missing canonical_url/source_url "
            "(architecture requires citation-ready URLs)."
        )

    root = data_dir or DATA_DIR
    slug = title_slug(retrieved.title)
    source_url = retrieved.canonical_url.strip()
    attribution = attribution_for(retrieved.title, retrieved.revision_id)

    raw_payload = {
        "source_url": source_url,
        "title": retrieved.title,
        "requested_title": retrieved.requested_title,
        "redirected_from": retrieved.redirected_from,
        "wiki_page_id": retrieved.wiki_page_id,
        "revision_id": retrieved.revision_id,
        "revision_timestamp": retrieved.revision_timestamp,
        "sha1": retrieved.sha1,
        "license": LICENSE_NAME,
        "attribution": attribution,
        "source": _source_block(),
        "wikitext": retrieved.wikitext,
    }

    structured_payload = {
        "source_url": source_url,
        "title": retrieved.title,
        "wiki_page_id": retrieved.wiki_page_id,
        "revision_id": retrieved.revision_id,
        "license": LICENSE_NAME,
        "attribution": attribution,
        "source": _source_block(),
        "page": {
            "wiki_page_id": retrieved.wiki_page_id,
            "title": retrieved.title,
            "canonical_url": source_url,
            "page_type": extracted.page_type,
            "article_status": extracted.article_status,
            "parent_title": extracted.parent_title,
            "latitude": extracted.latitude,
            "longitude": extracted.longitude,
            "is_huge_city": extracted.is_huge_city,
            "revision_id": retrieved.revision_id,
            "revision_timestamp": retrieved.revision_timestamp,
            "license": LICENSE_NAME,
            "attribution": attribution,
            "lead_text": extracted.lead_text or None,
        },
        "sections": [
            {
                "heading_path": s.heading_path,
                "section_title": s.section_title,
                "subsection_title": s.subsection_title,
                "heading_level": s.heading_level,
                "cleaned_text": s.cleaned_text,
                "source_url": source_url,
            }
            for s in extracted.sections
        ],
        "listings": [
            {
                "listing_kind": lst.listing_kind,
                "name": lst.name,
                "alt_name": lst.alt_name,
                "description": lst.description,
                "address": lst.address,
                "directions": lst.directions,
                "latitude": lst.latitude,
                "longitude": lst.longitude,
                "url": lst.url,
                "phone": lst.phone,
                "hours": lst.hours,
                "price_raw": lst.price_raw,
                "section_path": lst.section_path,
                "source_url": source_url,
            }
            for lst in extracted.listings
        ],
        "relationships": [
            {"to_title": r.to_title, "relationship_type": r.relationship_type}
            for r in extracted.relationships
        ],
    }

    chunks: list[dict[str, Any]] = []
    for idx, section in enumerate(extracted.sections):
        text = (section.cleaned_text or "").strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_id": f"{slug}__section__{idx:04d}",
                "chunk_type": "section",
                "text": text,
                "heading_path": section.heading_path,
                "section_title": section.section_title,
                "subsection_title": section.subsection_title,
                "source_url": source_url,
                "title": retrieved.title,
                "wiki_page_id": retrieved.wiki_page_id,
                "revision_id": retrieved.revision_id,
            }
        )
    for idx, listing in enumerate(extracted.listings):
        parts = [listing.name or "", listing.description or ""]
        text = " — ".join(p for p in parts if p).strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_id": f"{slug}__listing__{idx:04d}",
                "chunk_type": "listing",
                "text": text,
                "listing_kind": listing.listing_kind,
                "name": listing.name,
                "heading_path": listing.section_path,
                "source_url": source_url,
                "title": retrieved.title,
                "wiki_page_id": retrieved.wiki_page_id,
                "revision_id": retrieved.revision_id,
            }
        )

    chunks_payload = {
        "source_url": source_url,
        "title": retrieved.title,
        "wiki_page_id": retrieved.wiki_page_id,
        "revision_id": retrieved.revision_id,
        "license": LICENSE_NAME,
        "attribution": attribution,
        "source": _source_block(),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }

    paths = {
        "raw": root / "raw" / f"{slug}.json",
        "structured": root / "structured" / f"{slug}.json",
        "chunks": root / "chunks" / f"{slug}.json",
    }
    _write_json(paths["raw"], raw_payload)
    _write_json(paths["structured"], structured_payload)
    _write_json(paths["chunks"], chunks_payload)
    return paths


def export_from_db_page(page, *, data_dir: Path | None = None) -> dict[str, Path]:
    """Rebuild JSON artifacts from a persisted Page ORM object."""
    from tripwise.extract import extract_page
    from tripwise.source_client import RetrievedPage

    retrieved = RetrievedPage(
        requested_title=page.title,
        title=page.title,
        wiki_page_id=page.wiki_page_id,
        canonical_url=page.canonical_url,
        revision_id=page.revision_id,
        revision_timestamp=page.revision_timestamp,
        sha1=None,
        wikitext=page.raw_wikitext,
    )
    extracted = extract_page(page.title, page.raw_wikitext)
    return export_page_json(retrieved, extracted, data_dir=data_dir)


# Silence unused import warning for PROJECT_ROOT re-exports in docs
__all__ = ["export_page_json", "export_from_db_page", "title_slug", "DATA_DIR", "PROJECT_ROOT"]
