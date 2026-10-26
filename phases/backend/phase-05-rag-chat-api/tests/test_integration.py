"""Phase 5 live LLM + pipeline integration tests (opt-in).

Offline seeded citation test always runs.
Live tests require:
  TRIPWISE_RUN_INTEGRATION=1 pytest phases/backend/phase-05-rag-chat-api/tests -m integration -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PHASE5_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PHASE3_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "phase-03-embeddings-vector-store"
    / "scripts"
)
sys.path.insert(0, str(PHASE5_SCRIPTS))
sys.path.insert(0, str(PHASE3_SCRIPTS))

from tripwise_p3.config import Settings as P3Settings
from tripwise_p3.embedding_client import FakeEmbeddingClient, make_embedding_client
from tripwise_p3.models import make_session_factory
from tripwise_p3.retrieve import RetrieveHit, retrieve
from tripwise_p5.config import Settings
from tripwise_p5.groq_client import FakeChatClient, GroqChatClient
from tripwise_p5.rag import run_chat_turn
from tripwise_p5.scope import NO_ANSWER_MESSAGE

from integration_helpers import (
    WIKIVOYAGE_PREFIX,
    assert_no_ungrounded_prices,
    assert_wikivoyage_sources,
)

SEEDED_URL = "https://en.wikivoyage.org/wiki/Chennai"
SEEDED_PRICE = "34999"
SEEDED_HIT = RetrieveHit(
    title="Chennai",
    section_title="Do",
    text=(
        "Example city tour listing for tests: a full-day guided city tour "
        f"costs ₹{SEEDED_PRICE}. Book via local operators listed on Wikivoyage."
    ),
    source_url=SEEDED_URL,
    score=0.92,
    chunk_id="Chennai__listing__tour_test_0001",
    heading_path="Lead > Do",
)


def _p3_settings(settings: Settings) -> P3Settings:
    return P3Settings(
        database_url=settings.database_url,
        gemini_api_key=settings.gemini_api_key,
        gemini_embedding_model=settings.gemini_embedding_model,
        embedding_provider=getattr(settings, "embedding_provider", "local"),
        embedding_dim=settings.embedding_dim,
        chunks_dir=Path("."),
        min_chunk_chars=40,
        log_level=settings.log_level,
        local_embedding_model=getattr(
            settings, "local_embedding_model", "BAAI/bge-base-en-v1.5"
        ),
    )


def _unit_settings() -> Settings:
    return Settings(
        database_url="postgresql://unused",
        gemini_api_key="test",
        gemini_embedding_model="gemini-embedding-001",
        embedding_dim=768,
        groq_api_key="test",
        groq_model="openai/gpt-oss-20b",
        top_k=5,
        min_score=0.45,
        log_level="WARNING",
        host="127.0.0.1",
        port=8000,
    )


def test_seeded_price_and_url_offline_citation():
    """When evidence has ₹34999 + URL, response sources include that URL."""
    chat = FakeChatClient(
        reply=f"The tour price is ₹{SEEDED_PRICE}. See {SEEDED_URL}."
    )
    result = run_chat_turn(
        MagicMock(),
        _unit_settings(),
        FakeEmbeddingClient(),
        chat,
        "what is the price of tour to Chennai?",
        retrieve_fn=lambda *a, **k: [SEEDED_HIT],
    )
    assert result.refused is False
    assert SEEDED_PRICE in result.answer
    assert any(s.source_url == SEEDED_URL for s in result.sources)
    assert_wikivoyage_sources(result.sources)
    assert_no_ungrounded_prices(
        result.answer, [e.text for e in result.evidence]
    )


@pytest.mark.integration
def test_chennai_tour_price_live_grounding(live_settings):
    """Live stack: do not invent prices absent from retrieved evidence."""
    settings = live_settings
    embed = make_embedding_client(_p3_settings(settings), probe=False)
    chat = GroqChatClient(settings.groq_api_key, settings.groq_model)
    engine, factory = make_session_factory(settings.database_url)
    try:
        with factory() as session:
            result = run_chat_turn(
                session,
                settings,
                embed,
                chat,
                "what is the price of tour to Chennai?",
            )
    finally:
        engine.dispose()

    evidence_texts = [e.text for e in result.evidence]
    if result.refusal_reason == "insufficient_retrieval" or result.answer.strip() in {
        "I don't know",
        "I don’t know",
        NO_ANSWER_MESSAGE,
    }:
        assert result.evidence == []
        assert result.sources == []
        return

    assert_wikivoyage_sources(result.sources)
    assert_no_ungrounded_prices(result.answer, evidence_texts)
    if SEEDED_PRICE not in "\n".join(evidence_texts).replace(",", ""):
        assert SEEDED_PRICE not in result.answer.replace(",", "")


@pytest.mark.integration
def test_old_delhi_eat_live_smoke(live_settings):
    """Live retrieve → Groq interconnection for a known-good corpus query."""
    settings = live_settings
    embed = make_embedding_client(_p3_settings(settings), probe=False)
    chat = GroqChatClient(settings.groq_api_key, settings.groq_model)
    engine, factory = make_session_factory(settings.database_url)
    try:
        with factory() as session:
            hits = retrieve(session, embed, "Old Delhi eat", top_k=settings.top_k)
            assert hits, "expected pgvector hits — is Phase 3 embed complete?"
            assert all(h.source_url.startswith(WIKIVOYAGE_PREFIX) for h in hits)
            assert any(
                "Delhi" in (h.title or "") or "Delhi" in (h.chunk_id or "")
                for h in hits
            ), "hits should relate to Delhi"

            result = run_chat_turn(
                session,
                settings,
                embed,
                chat,
                "Old Delhi eat",
            )
    finally:
        engine.dispose()

    assert result.refused is False
    assert result.answer.strip()
    assert result.sources
    assert_wikivoyage_sources(result.sources)
    chat_urls = {s.source_url for s in result.sources}
    hit_urls = {h.source_url for h in hits}
    assert chat_urls & hit_urls, "chat sources should overlap retrieve hit URLs"
    blob = " ".join(
        [
            result.answer,
            " ".join(e.text for e in result.evidence),
            " ".join(s.title for s in result.sources),
        ]
    ).lower()
    assert "delhi" in blob or "paratha" in blob or "eat" in blob


@pytest.mark.integration
def test_seeded_price_live_groq_cites_url(live_settings):
    """Live Groq with fixture evidence: answer should use ₹34999 and cite seed URL."""
    settings = live_settings
    chat = GroqChatClient(settings.groq_api_key, settings.groq_model)
    result = run_chat_turn(
        MagicMock(),
        settings,
        FakeEmbeddingClient(),
        chat,
        "what is the price of tour to Chennai?",
        retrieve_fn=lambda *a, **k: [SEEDED_HIT],
    )
    assert result.refused is False
    answer_digits = re.sub(r"[,\s]", "", result.answer)
    assert SEEDED_PRICE in answer_digits or SEEDED_PRICE in result.answer
    assert any(s.source_url == SEEDED_URL for s in result.sources)
    assert_no_ungrounded_prices(result.answer, [e.text for e in result.evidence])
