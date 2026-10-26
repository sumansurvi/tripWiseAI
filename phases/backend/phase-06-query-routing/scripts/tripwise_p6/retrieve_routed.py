"""Filtered vector retrieve using Phase 6 route hints."""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tripwise_p3.embedding_client import EmbeddingClient
from tripwise_p3.models import RagChunk
from tripwise_p3.retrieve import RetrieveHit, retrieve
from tripwise_p6.router import RouteResult


def retrieve_routed(
    session: Session,
    client: EmbeddingClient,
    route: RouteResult,
    *,
    top_k: int = 5,
) -> List[RetrieveHit]:
    query = (route.rewritten_query or "").strip()
    if not query:
        return []

    if not route.title_filters:
        return retrieve(session, client, query, top_k=top_k)

    query_vec = client.embed_query(query)
    distance = RagChunk.embedding.cosine_distance(query_vec)
    filters = []
    for title in route.title_filters:
        filters.append(RagChunk.title.ilike(f"%{title}%"))
    stmt = (
        select(
            RagChunk.id,
            RagChunk.title,
            RagChunk.section_title,
            RagChunk.text,
            RagChunk.source_url,
            RagChunk.heading_path,
            (1 - distance).label("score"),
        )
        .where(or_(*filters))
        .order_by(distance)
        .limit(max(top_k * 3, top_k))
    )
    rows = session.execute(stmt).all()
    hits: List[RetrieveHit] = []
    for row in rows:
        section = row.section_title or ""
        if route.section_hint and route.section_hint.lower() not in section.lower():
            # soft preference: keep but demote later by order; still include
            pass
        hits.append(
            RetrieveHit(
                title=row.title,
                section_title=row.section_title,
                text=row.text,
                source_url=row.source_url,
                score=float(row.score),
                chunk_id=str(row.id),
                heading_path=row.heading_path,
            )
        )

    if route.section_hint:
        hint = route.section_hint.lower()

        def _key(h: RetrieveHit) -> tuple:
            sec = (h.section_title or "").lower()
            return (0 if hint in sec else 1, -h.score)

        hits.sort(key=_key)
    else:
        hits.sort(key=lambda h: h.score, reverse=True)

    if not hits:
        # Fall back to unfiltered vector search.
        return retrieve(session, client, query, top_k=top_k)
    return hits[:top_k]
