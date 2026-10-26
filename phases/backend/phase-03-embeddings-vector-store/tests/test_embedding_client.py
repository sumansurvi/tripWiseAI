"""Local embedding client factory and BGE query prefix (no model download)."""

from pathlib import Path

from tripwise_p3.config import Settings, active_embedding_model, is_local_provider
from tripwise_p3.embedding_client import (
    BGE_QUERY_PREFIX,
    FakeEmbeddingClient,
    LocalEmbeddingClient,
    make_embedding_client,
)


def _settings(**overrides) -> Settings:
    values = dict(
        database_url="postgresql://unused",
        gemini_api_key="",
        gemini_embedding_model="gemini-embedding-001",
        embedding_provider="local",
        embedding_dim=768,
        chunks_dir=Path("."),
        min_chunk_chars=40,
        log_level="WARNING",
        local_embedding_model="BAAI/bge-base-en-v1.5",
    )
    values.update(overrides)
    return Settings(**values)


class _DummyModel:
    def __init__(self):
        self.embedded = []

    def embed(self, texts, batch_size=32):
        self.embedded.extend(list(texts))
        for _ in texts:
            yield [0.1] * 768


def test_local_embed_query_applies_bge_prefix():
    model = _DummyModel()
    client = LocalEmbeddingClient(_settings(), model=model)
    vec = client.embed_query("Old Delhi eat")
    assert len(vec) == 768
    assert model.embedded == [BGE_QUERY_PREFIX + "Old Delhi eat"]


def test_local_embed_texts_does_not_prefix_documents():
    model = _DummyModel()
    client = LocalEmbeddingClient(_settings(), model=model)
    texts = ["provider=local|model=BAAI/bge-base-en-v1.5\nDelhi | Eat\nStreet food."]
    out = client.embed_texts(texts)
    assert len(out) == 1
    assert model.embedded == texts


def test_make_embedding_client_local_does_not_need_gemini_key():
    client = make_embedding_client(_settings(gemini_api_key=""), probe=False)
    assert isinstance(client, LocalEmbeddingClient)


def test_make_embedding_client_rejects_unknown_provider():
    try:
        make_embedding_client(_settings(embedding_provider="openai"))
    except ValueError as exc:
        assert "openai" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_active_model_follows_provider():
    local = _settings(embedding_provider="local")
    gemini = _settings(embedding_provider="gemini")
    assert is_local_provider(local.embedding_provider)
    assert active_embedding_model(local) == "BAAI/bge-base-en-v1.5"
    assert active_embedding_model(gemini) == "gemini-embedding-001"


def test_fake_client_still_deterministic():
    client = FakeEmbeddingClient(dim=8)
    assert client.embed_query("a") == client.embed_query("a")
    assert client.embed_query("a") != client.embed_query("b")
