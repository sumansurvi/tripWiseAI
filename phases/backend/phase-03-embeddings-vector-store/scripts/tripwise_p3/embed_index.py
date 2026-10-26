"""Idempotent chunk_embed_index: data/chunks → embeddings → rag_* tables."""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from tripwise_p3.config import Settings, active_embedding_model
from tripwise_p3.embedding_client import (
    DailyQuotaExceeded,
    EmbeddingClient,
    classify_gemini_quota,
    is_transient_gemini_error,
)
from tripwise_p3.load_chunks import SourceChunk, load_all_chunks
from tripwise_p3.models import RagChunk, RagDocument, utcnow

logger = logging.getLogger("tripwise.phase3.embed")

# Stop burning API/rate limits when every call fails the same way.
MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class EmbedResult:
    status: str
    total: int
    embedded: int
    skipped: int
    failed: int
    junk_skipped: int
    stop_reason: Optional[str] = None


def _terminal_width() -> int:
    return max(20, shutil.get_terminal_size(fallback=(80, 24)).columns)


def print_embed_progress(
    *,
    done: int,
    total: int,
    embedded: int,
    skipped: int,
    failed: int,
    title: str,
) -> None:
    """Overwrite a single terminal line for success ticks."""
    line = (
        f"progress embedded={embedded}/{total} skipped={skipped} failed={failed} "
        f"done={done}/{total} title={title}"
    )
    width = _terminal_width() - 1
    if len(line) > width:
        line = line[: max(0, width - 1)] + "…"
    sys.stdout.write("\r\033[2K" + line)
    sys.stdout.flush()


def print_embed_message(message: str) -> None:
    """Print a message on a new line below the in-place progress line."""
    sys.stdout.write("\n\033[2K" + message + "\n")
    sys.stdout.flush()


def finish_embed_progress() -> None:
    """End the in-place progress line so the next prompt/JSON is clean."""
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_embed_index(
    session: Session,
    settings: Settings,
    client: EmbeddingClient,
    *,
    chunks: Optional[list[SourceChunk]] = None,
) -> EmbedResult:
    if hasattr(client, "on_rate_limited") and client.on_rate_limited is None:
        client.on_rate_limited = lambda secs: print_embed_message(
            f"retrying; sleeping {secs:.0f}s"
        )

    loaded = chunks if chunks is not None else load_all_chunks(
        settings.chunks_dir,
        min_chars=settings.min_chunk_chars,
        provider=settings.embedding_provider,
        model=active_embedding_model(settings),
    )
    total = len(loaded)
    embedded = 0
    skipped = 0
    failed = 0
    consecutive_failures = 0
    stop_reason: Optional[str] = None
    quota_paused = False
    batch_size = max(1, int(getattr(settings, "embed_batch_size", 32)))
    pending: list[SourceChunk] = []
    done = 0
    existing_hashes = _load_chunk_hashes(session)

    def flush_pending() -> bool:
        """Embed + upsert pending batch. Returns False if should stop outer loop."""
        nonlocal embedded, failed, consecutive_failures, stop_reason, quota_paused, done
        if not pending:
            return True
        batch = list(pending)
        pending.clear()
        try:
            vectors = client.embed_texts([c.embed_text for c in batch])
            _upsert_batch(session, batch, vectors)
            for chunk, vector in zip(batch, vectors):
                existing_hashes[chunk.chunk_id] = chunk.content_hash
                embedded += 1
                done += 1
                print_embed_progress(
                    done=done,
                    total=total,
                    embedded=embedded,
                    skipped=skipped,
                    failed=failed,
                    title=chunk.title,
                )
            session.commit()
            consecutive_failures = 0
            return True
        except DailyQuotaExceeded:
            session.rollback()
            remaining = max(0, total - embedded - skipped)
            stop_reason = (
                "Paused: Gemini free-tier daily embed limit (1000/day) reached. "
                f"This run saved embedded={embedded} skipped={skipped}; "
                f"~{remaining} chunks left. "
                "Re-run after the daily quota resets; hash skip will resume."
            )
            quota_paused = True
            print_embed_message(stop_reason)
            print_embed_progress(
                done=done + len(batch),
                total=total,
                embedded=embedded,
                skipped=skipped,
                failed=failed,
                title=batch[0].title,
            )
            return False
        except Exception as exc:  # noqa: BLE001 — fall back to per-chunk
            session.rollback()
            print_embed_message(
                f"batch failed ({type(exc).__name__}); retrying one-by-one"
            )
            logger.warning("embed_batch_failed size=%s %s", len(batch), exc)
            for chunk in batch:
                try:
                    _upsert_one(session, client, chunk)
                    session.commit()
                    embedded += 1
                    consecutive_failures = 0
                except DailyQuotaExceeded:
                    session.rollback()
                    remaining = max(0, total - embedded - skipped)
                    stop_reason = (
                        "Paused: Gemini free-tier daily embed limit (1000/day) reached. "
                        f"This run saved embedded={embedded} skipped={skipped}; "
                        f"~{remaining} chunks left. "
                        "Re-run after the daily quota resets; hash skip will resume."
                    )
                    quota_paused = True
                    print_embed_message(stop_reason)
                    return False
                except Exception as one_exc:  # noqa: BLE001
                    session.rollback()
                    failed += 1
                    consecutive_failures += 1
                    err = f"{type(one_exc).__name__}: {one_exc}"
                    quota = classify_gemini_quota(one_exc)
                    if quota == "rpm" or is_transient_gemini_error(one_exc):
                        print_embed_message(
                            f"retries exhausted title={chunk.title} "
                            f"chunk_id={chunk.chunk_id}"
                        )
                    else:
                        print_embed_message(
                            f"error title={chunk.title} chunk_id={chunk.chunk_id} {err}"
                        )
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES and embedded == 0:
                        stop_reason = (
                            f"Stopped after {MAX_CONSECUTIVE_FAILURES} consecutive "
                            f"failures with nothing embedded. Last error: {err}"
                        )
                        print_embed_message(stop_reason)
                        return False
                done += 1
                print_embed_progress(
                    done=done,
                    total=total,
                    embedded=embedded,
                    skipped=skipped,
                    failed=failed,
                    title=chunk.title,
                )
            return True

    for chunk in loaded:
        if existing_hashes.get(chunk.chunk_id) == chunk.content_hash:
            skipped += 1
            done += 1
            print_embed_progress(
                done=done,
                total=total,
                embedded=embedded,
                skipped=skipped,
                failed=failed,
                title=chunk.title,
            )
            continue
        pending.append(chunk)
        if len(pending) >= batch_size:
            if not flush_pending():
                break

    if not quota_paused and not stop_reason:
        flush_pending()

    finish_embed_progress()

    if quota_paused:
        # Progress is already in Postgres; not a hard failure.
        status = "PARTIAL" if (embedded or skipped) else "FAILED"
    elif stop_reason or (failed and not embedded and total):
        status = "FAILED"
    elif failed and embedded:
        status = "PARTIAL"
    else:
        status = "COMPLETED"

    return EmbedResult(
        status=status,
        total=total,
        embedded=embedded,
        skipped=skipped,
        failed=failed,
        junk_skipped=0,
        stop_reason=stop_reason,
    )


def _load_chunk_hashes(session: Session) -> dict:
    """id → content_hash without fetching embedding vectors (important over WAN)."""
    rows = session.execute(select(RagChunk.id, RagChunk.content_hash)).all()
    return {row[0]: row[1] for row in rows}


_DOC_UPDATE_COLS = (
    "title",
    "section_title",
    "heading_path",
    "chunk_type",
    "source_url",
    "wiki_page_id",
    "revision_id",
    "license",
    "text",
    "content_hash",
    "updated_at",
)
_CHUNK_UPDATE_COLS = _DOC_UPDATE_COLS + ("document_id", "embedding")


def _row_payload(chunk: SourceChunk, now) -> dict:
    return {
        "title": chunk.title,
        "section_title": chunk.section_title,
        "heading_path": chunk.heading_path,
        "chunk_type": chunk.chunk_type,
        "source_url": chunk.source_url,
        "wiki_page_id": chunk.wiki_page_id,
        "revision_id": chunk.revision_id,
        "license": chunk.license,
        "text": chunk.text,
        "content_hash": chunk.content_hash,
        "created_at": now,
        "updated_at": now,
    }


def _upsert_batch(
    session: Session,
    batch: list[SourceChunk],
    vectors: list[list[float]],
) -> None:
    """One INSERT … ON CONFLICT per table for the whole batch (few WAN round-trips)."""
    now = utcnow()
    doc_rows = []
    chunk_rows = []
    for chunk, vector in zip(batch, vectors):
        payload = _row_payload(chunk, now)
        doc_rows.append({"id": chunk.chunk_id, **payload})
        chunk_rows.append(
            {
                "id": chunk.chunk_id,
                "document_id": chunk.chunk_id,
                "embedding": vector,
                **payload,
            }
        )
    doc_ins = pg_insert(RagDocument).values(doc_rows)
    session.execute(
        doc_ins.on_conflict_do_update(
            index_elements=["id"],
            set_={col: getattr(doc_ins.excluded, col) for col in _DOC_UPDATE_COLS},
        )
    )
    chunk_ins = pg_insert(RagChunk).values(chunk_rows)
    session.execute(
        chunk_ins.on_conflict_do_update(
            index_elements=["id"],
            set_={col: getattr(chunk_ins.excluded, col) for col in _CHUNK_UPDATE_COLS},
        )
    )


def _apply_vector(
    session: Session,
    chunk: SourceChunk,
    vector: list[float],
    *,
    exists: Optional[bool] = None,
) -> None:
    now = utcnow()
    if exists is None:
        exists = session.get(RagChunk, chunk.chunk_id) is not None

    doc_values = dict(
        title=chunk.title,
        section_title=chunk.section_title,
        heading_path=chunk.heading_path,
        chunk_type=chunk.chunk_type,
        source_url=chunk.source_url,
        wiki_page_id=chunk.wiki_page_id,
        revision_id=chunk.revision_id,
        license=chunk.license,
        text=chunk.text,
        content_hash=chunk.content_hash,
        updated_at=now,
    )
    chunk_values = dict(doc_values, embedding=vector)

    if exists:
        session.execute(
            update(RagDocument)
            .where(RagDocument.id == chunk.chunk_id)
            .values(**doc_values)
        )
        session.execute(
            update(RagChunk)
            .where(RagChunk.id == chunk.chunk_id)
            .values(**chunk_values)
        )
        return

    session.add(
        RagDocument(
            id=chunk.chunk_id,
            created_at=now,
            **doc_values,
        )
    )
    session.add(
        RagChunk(
            id=chunk.chunk_id,
            document_id=chunk.chunk_id,
            created_at=now,
            **chunk_values,
        )
    )


def _upsert_one(
    session: Session, client: EmbeddingClient, chunk: SourceChunk
) -> str:
    existing = session.get(RagChunk, chunk.chunk_id)
    if existing is not None and existing.content_hash == chunk.content_hash:
        return "skipped"

    vector = client.embed_texts([chunk.embed_text])[0]
    _apply_vector(session, chunk, vector)
    return "embedded"


def existing_hash(session: Session, chunk_id: str) -> Optional[str]:
    row = session.execute(
        select(RagChunk.content_hash).where(RagChunk.id == chunk_id)
    ).scalar_one_or_none()
    return row
