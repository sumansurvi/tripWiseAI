"""Top-k cosine retrieval over rag_chunks (no LLM generation)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from tripwise_p3.embedding_client import EmbeddingClient
from tripwise_p3.models import RagChunk


@dataclass
class RetrieveHit:
    title: str
    section_title: Optional[str]
    text: str
    source_url: str
    score: float
    chunk_id: str
    heading_path: Optional[str] = None


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def rank_by_cosine(
    query_vec: Sequence[float],
    rows: Sequence[tuple],
    *,
    top_k: int = 5,
) -> List[RetrieveHit]:
    """Pure-Python ranking for tests and fallback.

    ``rows`` items: (chunk_id, title, section_title, text, source_url, heading_path, embedding)
    """
    scored: List[RetrieveHit] = []
    for chunk_id, title, section_title, text, source_url, heading_path, emb in rows:
        score = cosine_similarity(query_vec, emb)
        scored.append(
            RetrieveHit(
                title=title,
                section_title=section_title,
                text=text,
                source_url=source_url,
                score=score,
                chunk_id=chunk_id,
                heading_path=heading_path,
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]


def retrieve(
    session: Session,
    client: EmbeddingClient,
    query: str,
    *,
    top_k: int = 5,
) -> List[RetrieveHit]:
    query_vec = client.embed_query(query.strip())
    # Cosine distance operator from pgvector; convert to similarity = 1 - distance.
    distance = RagChunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(
            RagChunk.id,
            RagChunk.title,
            RagChunk.section_title,
            RagChunk.text,
            RagChunk.source_url,
            RagChunk.heading_path,
            distance.label("distance"),
        )
        .order_by(distance)
        .limit(top_k)
    )
    hits: List[RetrieveHit] = []
    for row in session.execute(stmt):
        dist = float(row.distance)
        hits.append(
            RetrieveHit(
                chunk_id=row.id,
                title=row.title,
                section_title=row.section_title,
                text=row.text,
                source_url=row.source_url,
                heading_path=row.heading_path,
                score=1.0 - dist,
            )
        )
    return hits


def hits_to_jsonable(hits: List[RetrieveHit]) -> list[dict]:
    return [asdict(h) for h in hits]
