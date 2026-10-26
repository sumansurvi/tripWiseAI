"""Phase 5 RAG / scope / API tests (mocked Groq + FakeEmbeddingClient)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

PHASE5_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PHASE3_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "phase-03-embeddings-vector-store"
    / "scripts"
)
sys.path.insert(0, str(PHASE5_SCRIPTS))
sys.path.insert(0, str(PHASE3_SCRIPTS))

from tripwise_p3.embedding_client import FakeEmbeddingClient
from tripwise_p3.retrieve import RetrieveHit
from tripwise_p5.app import create_app
from tripwise_p5.config import Settings
from tripwise_p5.groq_client import FakeChatClient
from tripwise_p5.rag import run_chat_turn
from tripwise_p5.scope import NO_ANSWER_MESSAGE, check_personal_info


def _settings() -> Settings:
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


JOURNEY_QUESTIONS = [
    ("A", "Tell me about Jaipur"),
    ("B", "Best things to do in Delhi"),
    ("C", "What attractions should I visit in Agra?"),
    ("D", "How do I get around Delhi?"),
    ("E", "Which area should I stay in in Mumbai?"),
    ("F", "What food should I try in Old Delhi?"),
    ("G", "What should I know before visiting India?"),
]


def test_pii_refusal():
    assert check_personal_info("What is my passport number?") == "personal_information"
    assert check_personal_info("Tell me about Jaipur") is None


def test_run_chat_pii_no_retrieve():
    session = MagicMock()
    chat = FakeChatClient()
    result = run_chat_turn(
        session,
        _settings(),
        FakeEmbeddingClient(),
        chat,
        "What is my Aadhaar number?",
        retrieve_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no retrieve")),
    )
    assert result.refused is True
    assert result.refusal_reason == "personal_information"
    assert chat.calls == []


def test_insufficient_retrieval_i_dont_know():
    session = MagicMock()
    chat = FakeChatClient()

    def weak_retrieve(*args, **kwargs):
        return [
            RetrieveHit(
                title="X",
                section_title=None,
                text="noise",
                source_url="https://en.wikivoyage.org/wiki/X",
                score=0.1,
                chunk_id="x1",
            )
        ]

    result = run_chat_turn(
        session,
        _settings(),
        FakeEmbeddingClient(),
        chat,
        "xyzzy unrelated",
        retrieve_fn=weak_retrieve,
    )
    assert result.answer == NO_ANSWER_MESSAGE
    assert "don't know" not in result.answer.lower()
    assert result.evidence == []
    assert chat.calls == []


def test_happy_path_uses_groq_and_sources():
    session = MagicMock()
    chat = FakeChatClient(reply="Try Paranthe Wali Gali.")

    def good_retrieve(*args, **kwargs):
        return [
            RetrieveHit(
                title="Delhi/Old Delhi",
                section_title="Eat",
                text="Paranthe Wali Gali has many paratha shops.",
                source_url="https://en.wikivoyage.org/wiki/Delhi/Old_Delhi",
                score=0.76,
                chunk_id="Delhi__Old_Delhi__section__0021",
            )
        ]

    result = run_chat_turn(
        session,
        _settings(),
        FakeEmbeddingClient(),
        chat,
        "Old Delhi eat",
        retrieve_fn=good_retrieve,
    )
    assert result.refused is False
    assert "Paranthe" in result.answer
    assert result.sources[0].source_url.endswith("Old_Delhi")
    assert result.evidence[0].chunk_id == "Delhi__Old_Delhi__section__0021"
    assert len(chat.calls) == 1


@pytest.mark.parametrize("jid,question", JOURNEY_QUESTIONS)
def test_journeys_a_g_not_pii(jid, question):
    assert check_personal_info(question) is None, jid


@pytest.mark.parametrize("jid,question", JOURNEY_QUESTIONS)
def test_journeys_a_g_chat_path(jid, question):
    session = MagicMock()
    chat = FakeChatClient(reply=f"Answer for {jid}")

    def good_retrieve(*args, **kwargs):
        return [
            RetrieveHit(
                title="India",
                section_title="Understand",
                text="India travel context for tests.",
                source_url="https://en.wikivoyage.org/wiki/India",
                score=0.7,
                chunk_id="India__section__0001",
            )
        ]

    result = run_chat_turn(
        session,
        _settings(),
        FakeEmbeddingClient(),
        chat,
        question,
        retrieve_fn=good_retrieve,
    )
    assert result.refused is False
    assert result.answer.startswith("Answer for")


def test_api_chat_endpoint():
    session = MagicMock()
    factory = MagicMock()
    factory.return_value.__enter__ = lambda s: session
    factory.return_value.__exit__ = lambda *a: False

    # sessionmaker() returns a context manager when used as `with factory()`
    class Factory:
        def __call__(self):
            return self

        def __enter__(self):
            return session

        def __exit__(self, *args):
            return False

    hits = [
        RetrieveHit(
            title="Delhi",
            section_title="Eat",
            text="Street food is popular.",
            source_url="https://en.wikivoyage.org/wiki/Delhi",
            score=0.8,
            chunk_id="d1",
        )
    ]

    app = create_app(
        _settings(),
        embed_client=FakeEmbeddingClient(),
        chat_client=FakeChatClient(reply="Street food tips."),
        session_factory=Factory(),
    )

    # Patch hybrid path used inside run_chat_turn
    import tripwise_p5.rag as rag_mod

    def fake_hybrid(*args, **kwargs):
        return hits

    original = rag_mod.hybrid_retrieve
    rag_mod.hybrid_retrieve = fake_hybrid
    try:
        with TestClient(app) as client:
            # PII
            r = client.post("/chat", json={"message": "What is my passport number?"})
            assert r.status_code == 200
            body = r.json()
            assert body["refused"] is True

            r2 = client.post("/chat", json={"message": "Old Delhi eat"})
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["refused"] is False
            assert body2["answer"] == "Street food tips."
            assert body2["sources"][0]["source_url"].endswith("Delhi")
    finally:
        rag_mod.hybrid_retrieve = original


def test_travel_questions_mentioning_documents_are_not_refused():
    for q in (
        "Do I need a passport for India?",
        "Do I need a visa for India?",
        "What is my best option for 4 days in Delhi?",
        "What's my best route from Agra to Jaipur?",
        "ATM and bank hours in Delhi",
    ):
        assert check_personal_info(q) is None, q


def test_personal_data_requests_are_refused():
    for q in (
        "What is my passport number?",
        "What's my bank account?",
        "Tell me my medical history",
        "what is my date of birth",
        "whats my email",
    ):
        assert check_personal_info(q) == "personal_information", q


def test_clean_answer_extracts_recommendation_and_drops_filler():
    from tripwise_p5.rag import _clean_answer

    raw = (
        "**Delhi vs Mumbai**\n\n"
        "| Aspect | Delhi | Mumbai |\n|---|---|---|\n"
        "| Food | Street food | Vada pav |\n"
        "| Metro | Cheap | Not covered in the provided sources. |\n\n"
        "**What I recommend:** Pick Delhi for history.\n\n"
        "Sources:\n- Delhi: https://en.wikivoyage.org/wiki/Delhi\n"
    )
    body, rec = _clean_answer(raw)
    assert rec == "Pick Delhi for history."
    assert "What I recommend" not in body
    assert "Not covered" not in body and "Sources" not in body
    assert "Street food" in body


def test_no_answer_detection():
    from tripwise_p5.rag import _is_no_answer

    assert _is_no_answer("NO_ANSWER")
    assert _is_no_answer("I'm sorry, but I don't have information on that.")
    assert not _is_no_answer("**What to eat in Old Delhi**\n\n| Dish | Where |")


def test_clean_answer_drops_rows_with_empty_cells():
    from tripwise_p5.rag import _clean_answer

    raw = (
        "| Aspect | Delhi | Mumbai |\n|---|---|---|\n"
        "| Transport | Taxis | Metro |\n"
        "| Ticketing | Not detailed | Smart card |\n"
        "| Fares | N/A | ₹10 |\n"
    )
    body, _ = _clean_answer(raw)
    assert "Transport" in body
    assert "Ticketing" not in body and "Fares" not in body
