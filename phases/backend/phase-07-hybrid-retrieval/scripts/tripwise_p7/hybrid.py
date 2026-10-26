"""Lexical + vector fusion (Postgres ILIKE / simple token overlap + vectors).

Rerank is disabled by default (enable via ``enable_rerank=True`` only after eval lift).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tripwise_p3.embedding_client import EmbeddingClient
from tripwise_p3.models import RagChunk
from tripwise_p3.retrieve import RetrieveHit, retrieve


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)

# Words that match almost every chunk and only add noise to lexical search.
_STOPWORDS = frozenset(
    """the and for are but not you your with what whats which who whom whose when where why how
    can could should would will shall may might must does did has have had was were been being
    this that these those there here from into onto over under about after before between
    best good great top some any all get got give tell show find need want know visit visiting
    trip travel place places thing things around near out off too very just also than then
    india indian""".split()
)


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2]


def _content_tokens(text: str) -> List[str]:
    """Distinctive query tokens (stopwords removed) used for lexical matching."""
    return [t for t in _tokens(text) if t not in _STOPWORDS]


def lexical_candidates(
    session: Session,
    query: str,
    *,
    limit: int = 20,
    title_filters: Optional[Sequence[str]] = None,
) -> List[RetrieveHit]:
    toks = _content_tokens(query)
    if not toks:
        return []
    # Prefer exact-ish phrase + token OR filters (lightweight BM25 stand-in).
    clauses = [RagChunk.text.ilike(f"%{query.strip()}%")]
    for t in toks[:8]:
        clauses.append(RagChunk.text.ilike(f"%{t}%"))
    stmt = select(
        RagChunk.id,
        RagChunk.title,
        RagChunk.section_title,
        RagChunk.text,
        RagChunk.source_url,
        RagChunk.heading_path,
    )
    if title_filters:
        title_or = [RagChunk.title.ilike(f"%{t}%") for t in title_filters]
        stmt = stmt.where(or_(*title_or))
    stmt = stmt.where(or_(*clauses)).limit(limit)
    rows = session.execute(stmt).all()
    qset = set(toks)
    hits: List[RetrieveHit] = []
    for row in rows:
        tset = set(_tokens(row.text))
        overlap = len(qset & tset) / max(len(qset), 1)
        # Require real overlap: a single shared word is noise for multi-word asks.
        if len(qset) >= 2 and overlap < 0.5:
            continue
        hits.append(
            RetrieveHit(
                title=row.title,
                section_title=row.section_title,
                text=row.text,
                source_url=row.source_url,
                score=float(overlap),
                chunk_id=str(row.id),
                heading_path=row.heading_path,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def _rrf_fuse(
    vector_hits: Sequence[RetrieveHit],
    lexical_hits: Sequence[RetrieveHit],
    *,
    k: int = 60,
    top_k: int = 5,
) -> List[RetrieveHit]:
    scores: Dict[str, float] = {}
    by_id: Dict[str, RetrieveHit] = {}
    for rank, h in enumerate(vector_hits):
        scores[h.chunk_id] = scores.get(h.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        by_id[h.chunk_id] = h
    for rank, h in enumerate(lexical_hits):
        scores[h.chunk_id] = scores.get(h.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        by_id.setdefault(h.chunk_id, h)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out: List[RetrieveHit] = []
    for cid, fused in ordered[:top_k]:
        h = by_id[cid]
        out.append(
            RetrieveHit(
                title=h.title,
                section_title=h.section_title,
                text=h.text,
                source_url=h.source_url,
                score=float(fused),
                chunk_id=h.chunk_id,
                heading_path=h.heading_path,
            )
        )
    return out


def hybrid_retrieve(
    session: Session,
    client: EmbeddingClient,
    query: str,
    *,
    top_k: int = 5,
    title_filters: Optional[Sequence[str]] = None,
    enable_rerank: bool = False,
    vector_fn=None,
    min_vector_score: Optional[float] = None,
) -> List[RetrieveHit]:
    """Fuse vector + lexical. ``enable_rerank`` reserved; default off (no lift proven).

    ``min_vector_score`` is the relevance gate: if the best *cosine* similarity among
    vector hits is below it, nothing is returned (caller answers "I don't know").
    Lexical hits never rescue an off-topic query — they only re-rank vector matches.
    """
    _ = enable_rerank  # intentionally unused until eval shows lift
    v_fn = vector_fn or retrieve
    vector_hits = v_fn(session, client, query, top_k=max(top_k * 4, 20))
    if min_vector_score is not None:
        best = max((h.score for h in vector_hits), default=0.0)
        if best < min_vector_score:
            return []
    # If vector_fn already filtered, still run lexical with same titles.
    lex_hits = lexical_candidates(
        session, query, limit=20, title_filters=title_filters
    )
    if not lex_hits:
        return vector_hits[:top_k]
    if not vector_hits:
        return lex_hits[:top_k]
    return _rrf_fuse(vector_hits, lex_hits, top_k=top_k)


# Scheduler note: after Phase 3 embed, optionally rebuild a future tsvector index.
SCHEDULER_LEXICAL_STAGE = "phase-07-lexical-rebuild"  # register when tsvector lands
