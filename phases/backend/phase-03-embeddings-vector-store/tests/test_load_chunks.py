"""Tests for loading data/chunks JSON into SourceChunk records."""

from pathlib import Path

from tripwise_p3.load_chunks import (
    build_embed_text,
    content_hash_for,
    load_chunks_from_file,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_load_skips_junk_and_keeps_food_chunks():
    chunks = load_chunks_from_file(FIXTURES / "sample_chunks.json", min_chars=40)
    ids = {c.chunk_id for c in chunks}
    assert "Delhi__Old_Delhi__section__0000" in ids
    assert "Delhi__Old_Delhi__listing__0000" in ids
    assert "Delhi__Old_Delhi__section__0001" not in ids  # "*\n*" junk
    assert all(c.source_url.startswith("https://en.wikivoyage.org/") for c in chunks)


def test_embed_text_prefix_and_stable_hash():
    text = build_embed_text(
        title="Delhi/Old Delhi",
        heading_path="Lead > Eat",
        section_title="Eat",
        text="Street food near Chandni Chowk.",
        provider="gemini",
        model="gemini-embedding-001",
    )
    assert text.startswith("provider=gemini|model=gemini-embedding-001")
    assert "Delhi/Old Delhi | Lead > Eat | Wikivoyage" in text
    assert content_hash_for(text) == content_hash_for(text)
    assert content_hash_for(text) != content_hash_for(text + "x")


def test_provider_switch_invalidates_hash():
    kwargs = dict(
        title="Delhi/Old Delhi",
        heading_path="Lead > Eat",
        section_title="Eat",
        text="Street food near Chandni Chowk.",
    )
    gemini = build_embed_text(provider="gemini", model="gemini-embedding-001", **kwargs)
    groq = build_embed_text(provider="groq", model="nomic-embed-text-v1_5", **kwargs)
    assert content_hash_for(gemini) != content_hash_for(groq)


def test_local_provider_switch_invalidates_hash():
    kwargs = dict(
        title="Delhi/Old Delhi",
        heading_path="Lead > Eat",
        section_title="Eat",
        text="Street food near Chandni Chowk.",
    )
    gemini = build_embed_text(provider="gemini", model="gemini-embedding-001", **kwargs)
    local = build_embed_text(
        provider="local", model="BAAI/bge-base-en-v1.5", **kwargs
    )
    assert content_hash_for(gemini) != content_hash_for(local)
