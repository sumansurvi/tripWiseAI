"""RAG turn: route → hybrid retrieve → compare (optional) → Groq (or refuse)."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from sqlalchemy.orm import Session

from tripwise_p3.embedding_client import EmbeddingClient
from tripwise_p3.retrieve import RetrieveHit
from tripwise_p5.config import Settings
from tripwise_p5.groq_client import (
    SYSTEM_PROMPT,
    ChatClient,
    build_user_prompt,
)
from tripwise_p5.scope import NO_ANSWER_MESSAGE, REFUSAL_MESSAGE
from tripwise_p6.router import _expand_huge_cities, extract_entities, route_query
from tripwise_p6.retrieve_routed import retrieve_routed
from tripwise_p7.hybrid import hybrid_retrieve
from tripwise_p8.memory import DEFAULT_STORE, rewrite_with_slots
from tripwise_p9.compare import build_comparison, interleave

logger = logging.getLogger("tripwise.phase5.rag")

RetrieveFn = Callable[..., List[RetrieveHit]]


@dataclass
class EvidenceItem:
    chunk_id: str
    text: str
    score: float


@dataclass
class SourceItem:
    title: str
    source_url: str


@dataclass
class ChatResult:
    request_id: str
    answer: str
    evidence: List[EvidenceItem]
    sources: List[SourceItem]
    refused: bool
    refusal_reason: Optional[str]
    conversation_id: Optional[str] = None
    recommendation: Optional[str] = None
    trade_offs: List[dict] = field(default_factory=list)
    intent: Optional[str] = None


def _sources_from_hits(hits: Sequence[RetrieveHit]) -> List[SourceItem]:
    seen = set()
    out: List[SourceItem] = []
    for h in hits:
        key = h.source_url
        if key in seen:
            continue
        seen.add(key)
        out.append(SourceItem(title=h.title, source_url=h.source_url))
    return out


def _evidence_from_hits(hits: Sequence[RetrieveHit]) -> List[EvidenceItem]:
    return [
        EvidenceItem(chunk_id=h.chunk_id, text=h.text, score=h.score) for h in hits
    ]


def _vector_filtered(session, client, query, *, top_k=5, title_filters=None):
    from tripwise_p6.router import RouteResult

    route = RouteResult(
        intent="destination",
        rewritten_query=query,
        title_filters=list(title_filters or []),
    )
    return retrieve_routed(session, client, route, top_k=top_k)



# ---------------------------------------------------------------------------
# Answer post-processing (keep replies crisp; never leak internals)
# ---------------------------------------------------------------------------

NO_ANSWER_SENTINEL = "NO_ANSWER"

_SOURCES_TAIL_RE = re.compile(
    r"\n{0,2}(?:#{1,4}\s*)?(?:\*\*)?(?:Sources?|References?)(?:\*\*)?\s*:?\s*(?:\*\*)?\s*\n[\s\S]*$",
    re.IGNORECASE,
)
_RECOMMEND_RE = re.compile(
    r"^[ \t>]*(?:[-*]\s+)?\*{0,2}what i recommend\*{0,2}\s*[:\-–]?\s*\*{0,2}\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_NOT_COVERED_ROW_RE = re.compile(
    r"not (?:covered|available|mentioned|provided|found)[^|\n]*(?:sources?|context|data)"
    r"|no (?:information|data) (?:in|on|about)[^|\n]*(?:sources?|context)",
    re.IGNORECASE,
)
# A table cell that is just filler for "no data" → the whole row is dropped.
_EMPTY_CELL_RE = re.compile(
    r"\|\s*(?:not detailed|not specified|not mentioned|not provided|not available|"
    r"n/?a|unknown|no info(?:rmation)?|none|-|—|–)\s*(?=\|)",
    re.IGNORECASE,
)
_APOLOGY_NO_INFO_RE = re.compile(
    r"(?:i(?:'|’)?m sorry|sorry|unfortunately)[^.\n]{0,80}"
    r"(?:don(?:'|’)?t have|do not have|no information|couldn(?:'|’)?t find|not (?:covered|available))",
    re.IGNORECASE,
)


def _is_no_answer(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    if text.upper().startswith(NO_ANSWER_SENTINEL):
        return True
    # Model apologised instead of answering → treat as unknown, don't show a half-answer.
    return bool(_APOLOGY_NO_INFO_RE.search(text))


def _clean_answer(answer: str) -> tuple:
    """Return (body, recommendation). Strips Sources tail, filler rows, citation marks."""
    text = _SOURCES_TAIL_RE.sub("", answer or "")
    rec = None
    m = _RECOMMEND_RE.search(text)
    if m:
        rec = m.group(1).strip().strip("*").strip() or None
        text = _RECOMMEND_RE.sub("", text)
    # Drop table rows that only say "not covered in the provided sources".
    kept = []
    for line in text.splitlines():
        if line.lstrip().startswith("|") and (
            _NOT_COVERED_ROW_RE.search(line) or _EMPTY_CELL_RE.search(line)
        ):
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"【\d+】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, rec


class _CachedEmbed:
    """Embed each distinct query once per turn (comparison retrieves per side)."""

    def __init__(self, inner: EmbeddingClient):
        self._inner = inner
        self._cache: dict = {}

    def embed_query(self, text: str):
        if text not in self._cache:
            self._cache[text] = self._inner.embed_query(text)
        return self._cache[text]

    def embed_texts(self, texts):
        return self._inner.embed_texts(texts)


def _comparison_hits(
    session, embed_client, settings, query: str, entities: Sequence[str]
) -> tuple:
    """Retrieve each side separately so both destinations are represented.

    Returns (hits, missing_entities). A side with no sufficiently relevant chunks is
    reported as missing — the caller then answers politely that it doesn't know.
    """
    client = _CachedEmbed(embed_client)
    sides: List[List[RetrieveHit]] = []
    missing: List[str] = []
    for ent in list(entities)[:2]:
        filters = _expand_huge_cities([ent], overview_only=False)

        def _vect(sess, c, q, top_k=5, _f=filters):
            return _vector_filtered(sess, c, q, top_k=top_k, title_filters=_f)

        side = hybrid_retrieve(
            session,
            client,
            query,
            top_k=3,
            title_filters=filters,
            enable_rerank=False,
            vector_fn=_vect,
            min_vector_score=settings.min_score,
        )
        # Keep only chunks that actually belong to this destination's pages.
        side = [
            h for h in side if any(f.lower() in (h.title or "").lower() for f in filters)
        ]
        if not side:
            missing.append(ent)
        sides.append(side)
    return interleave(*sides), missing


def _no_answer(request_id, state, route) -> "ChatResult":
    return ChatResult(
        request_id=request_id,
        answer=NO_ANSWER_MESSAGE,
        evidence=[],
        sources=[],
        refused=False,
        refusal_reason="insufficient_retrieval",
        conversation_id=state.conversation_id,
        intent=route.intent,
    )


def run_chat_turn(
    session: Session,
    settings: Settings,
    embed_client: EmbeddingClient,
    chat_client: ChatClient,
    message: str,
    *,
    history: Optional[List[Any]] = None,
    conversation_id: Optional[str] = None,
    retrieve_fn: Optional[RetrieveFn] = None,
) -> ChatResult:
    request_id = str(uuid.uuid4())
    logger.debug("chat_request request_id=%s", request_id)

    state = DEFAULT_STORE.get_or_create(conversation_id)
    raw = (message or "").strip()
    _ = history

    route = route_query(raw, active_destination=state.active_destination)
    if route.refuse_reason == "empty_message":
        return ChatResult(
            request_id=request_id,
            answer="Please ask a destination or travel question.",
            evidence=[],
            sources=[],
            refused=True,
            refusal_reason=route.refuse_reason,
            conversation_id=state.conversation_id,
            intent=route.intent,
        )
    if route.refuse_reason:
        return ChatResult(
            request_id=request_id,
            answer=REFUSAL_MESSAGE,
            evidence=[],
            sources=[],
            refused=True,
            refusal_reason=route.refuse_reason,
            conversation_id=state.conversation_id,
            intent=route.intent,
        )

    # Only borrow the active destination for bare follow-ups. A message that names
    # its own destination(s), or a comparison, must not be rewritten.
    if route.intent == "comparison" or extract_entities(raw):
        query = route.rewritten_query or raw
    else:
        query = rewrite_with_slots(route.rewritten_query or raw, state)

    # Exactly one chat LLM call per turn (below). Routing/compare are local heuristics.
    # Query embed runs once per distinct query (cached), not a chat LLM.
    if retrieve_fn is not None:
        hits = retrieve_fn(session, embed_client, query, top_k=settings.top_k)
        if route.intent == "comparison" and len(route.entities) >= 2:
            hits = build_comparison(route.entities, hits).evidence[: settings.top_k] or hits
    elif route.intent == "comparison" and len(route.entities) >= 2:
        hits, missing = _comparison_hits(
            session, embed_client, settings, query, route.entities
        )
        if missing:
            # Can't compare honestly without evidence for both sides.
            return _no_answer(request_id, state, route)
    else:

        def _vect(sess, client, q, top_k=5):
            return _vector_filtered(
                sess, client, q, top_k=top_k, title_filters=route.title_filters
            )

        hits = hybrid_retrieve(
            session,
            embed_client,
            query,
            top_k=settings.top_k,
            title_filters=route.title_filters or None,
            enable_rerank=False,
            vector_fn=_vect,
            # Hard relevance gate on cosine similarity (Phase 5 rule: weak → polite "don't know").
            min_vector_score=settings.min_score,
        )

    if not hits:
        return _no_answer(request_id, state, route)
    # Cosine min_score gate for injected retrieve_fn paths (tests).
    # Hybrid RRF scores are not comparable to cosine similarity.
    if retrieve_fn is not None and hits[0].score < settings.min_score:
        return _no_answer(request_id, state, route)

    user_prompt = build_user_prompt(query, hits)
    raw_answer = chat_client.complete(system=SYSTEM_PROMPT, user=user_prompt)
    if _is_no_answer(raw_answer):
        return _no_answer(request_id, state, route)
    answer, recommendation = _clean_answer(raw_answer)
    if route.intent != "comparison":
        recommendation = None  # "What I recommend" is only for comparisons
    if not answer:
        return _no_answer(request_id, state, route)

    state.append_turn("user", raw)
    state.append_turn("assistant", answer)
    if route.entities:
        state.active_destination = route.entities[0]
        if route.intent == "comparison":
            state.compared_destinations = list(route.entities[:2])
    state.last_domain = route.intent

    return ChatResult(
        request_id=request_id,
        answer=answer,
        evidence=_evidence_from_hits(hits),
        sources=_sources_from_hits(hits),
        refused=False,
        refusal_reason=None,
        conversation_id=state.conversation_id,
        recommendation=recommendation,
        trade_offs=[],
        intent=route.intent,
    )


def chat_result_to_dict(result: ChatResult) -> dict:
    return {
        "request_id": result.request_id,
        "answer": result.answer,
        "evidence": [asdict(e) for e in result.evidence],
        "sources": [asdict(s) for s in result.sources],
        "refused": result.refused,
        "refusal_reason": result.refusal_reason,
        "conversation_id": result.conversation_id,
        "recommendation": result.recommendation,
        "trade_offs": result.trade_offs,
        "intent": result.intent,
    }
