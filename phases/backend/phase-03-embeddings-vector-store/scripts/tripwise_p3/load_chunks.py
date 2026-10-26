"""Load citation-ready chunks from data/chunks/*.json."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Optional


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    chunk_type: str
    text: str
    title: str
    source_url: str
    section_title: Optional[str]
    heading_path: Optional[str]
    wiki_page_id: Optional[int]
    revision_id: Optional[int]
    license: Optional[str]
    content_hash: str
    embed_text: str


def content_hash_for(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_embed_text(
    *,
    title: str,
    heading_path: Optional[str],
    section_title: Optional[str],
    text: str,
    provider: str = "gemini",
    model: str = "gemini-embedding-001",
) -> str:
    """Prefix for retrieval quality + provider tag so model switches invalidate hashes."""
    path = heading_path or section_title or ""
    parts = [p for p in (title, path, "Wikivoyage") if p]
    prefix = " | ".join(parts)
    return f"provider={provider}|model={model}\n{prefix}\n{text.strip()}"


def iter_chunk_files(chunks_dir: Path) -> Iterator[Path]:
    if not chunks_dir.is_dir():
        return
    yield from sorted(chunks_dir.glob("*.json"))


def load_chunks_from_file(
    path: Path,
    *,
    min_chars: int = 40,
    provider: str = "gemini",
    model: str = "gemini-embedding-001",
) -> List[SourceChunk]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    license_name = payload.get("license")
    page_title = payload.get("title") or ""
    page_source_url = payload.get("source_url") or ""
    page_wiki_id = payload.get("wiki_page_id")
    page_rev = payload.get("revision_id")

    out: List[SourceChunk] = []
    for raw in payload.get("chunks") or []:
        chunk = _parse_one(
            raw,
            default_title=page_title,
            default_source_url=page_source_url,
            default_wiki_id=page_wiki_id,
            default_rev=page_rev,
            license_name=license_name,
            min_chars=min_chars,
            provider=provider,
            model=model,
        )
        if chunk is not None:
            out.append(chunk)
    return out


def load_all_chunks(
    chunks_dir: Path,
    *,
    min_chars: int = 40,
    provider: str = "gemini",
    model: str = "gemini-embedding-001",
) -> List[SourceChunk]:
    chunks: List[SourceChunk] = []
    for path in iter_chunk_files(chunks_dir):
        chunks.extend(
            load_chunks_from_file(
                path, min_chars=min_chars, provider=provider, model=model
            )
        )
    return chunks


def _parse_one(
    raw: dict[str, Any],
    *,
    default_title: str,
    default_source_url: str,
    default_wiki_id: Any,
    default_rev: Any,
    license_name: Optional[str],
    min_chars: int,
    provider: str,
    model: str,
) -> Optional[SourceChunk]:
    text = (raw.get("text") or "").strip()
    if len(text) < min_chars:
        return None
    source_url = (raw.get("source_url") or default_source_url or "").strip()
    if not source_url:
        return None
    chunk_id = (raw.get("chunk_id") or "").strip()
    if not chunk_id:
        return None
    title = (raw.get("title") or default_title or "").strip() or "Unknown"
    heading_path = raw.get("heading_path")
    section_title = raw.get("section_title")
    embed_text = build_embed_text(
        title=title,
        heading_path=heading_path,
        section_title=section_title,
        text=text,
        provider=provider,
        model=model,
    )
    return SourceChunk(
        chunk_id=chunk_id,
        chunk_type=(raw.get("chunk_type") or "section").strip(),
        text=text,
        title=title,
        source_url=source_url,
        section_title=section_title,
        heading_path=heading_path,
        wiki_page_id=_as_int(raw.get("wiki_page_id", default_wiki_id)),
        revision_id=_as_int(raw.get("revision_id", default_rev)),
        license=license_name,
        content_hash=content_hash_for(embed_text),
        embed_text=embed_text,
    )


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
