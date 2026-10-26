"""Embed index: FakeEmbeddingClient + hash skip (no network / no Postgres)."""

from pathlib import Path
from unittest.mock import MagicMock

from tripwise_p3.embed_index import _upsert_one, run_embed_index
from tripwise_p3.embedding_client import DailyQuotaExceeded, FakeEmbeddingClient
from tripwise_p3.load_chunks import load_chunks_from_file
from tripwise_p3.config import Settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://unused",
        gemini_api_key="",
        gemini_embedding_model="gemini-embedding-001",
        embedding_provider="gemini",
        embedding_dim=768,
        chunks_dir=FIXTURES,
        min_chunk_chars=40,
        log_level="WARNING",
    )


def _session_with_hashes(pairs=None, get_value=None):
    session = MagicMock()
    session.execute.return_value.all.return_value = list(pairs or [])
    session.get.return_value = get_value
    return session


def test_upsert_skips_when_hash_matches():
    chunks = load_chunks_from_file(FIXTURES / "sample_chunks.json")
    chunk = chunks[0]
    client = FakeEmbeddingClient(dim=768)
    session = MagicMock()
    existing = MagicMock()
    existing.content_hash = chunk.content_hash
    session.get.return_value = existing

    outcome = _upsert_one(session, client, chunk)
    assert outcome == "skipped"
    assert client.calls == []


def test_upsert_embeds_when_missing():
    chunks = load_chunks_from_file(FIXTURES / "sample_chunks.json")
    chunk = chunks[0]
    client = FakeEmbeddingClient(dim=768)
    session = MagicMock()
    session.get.return_value = None

    outcome = _upsert_one(session, client, chunk)
    assert outcome == "embedded"
    assert len(client.calls) == 1
    assert session.add.call_count >= 2


def test_run_embed_index_reports_skip_on_second_pass(capsys):
    chunks = load_chunks_from_file(FIXTURES / "sample_chunks.json")
    client = FakeEmbeddingClient(dim=768)
    settings = _settings()

    session = _session_with_hashes()
    first = run_embed_index(session, settings, client, chunks=chunks)
    assert first.embedded == len(chunks)
    assert first.skipped == 0
    out = capsys.readouterr().out
    assert "progress embedded=" in out
    assert "\r" in out
    assert "\033[2K" in out

    calls_after_first = len(client.calls)

    def get_existing(model, key):
        m = MagicMock()
        m.content_hash = next(c.content_hash for c in chunks if c.chunk_id == key)
        return m

    session2 = _session_with_hashes(
        [(c.chunk_id, c.content_hash) for c in chunks]
    )
    session2.get.side_effect = get_existing
    second = run_embed_index(session2, settings, client, chunks=chunks)
    assert second.skipped == len(chunks)
    assert second.embedded == 0
    assert len(client.calls) == calls_after_first


def test_daily_quota_pause_is_partial_not_failed(capsys):
    chunks = load_chunks_from_file(FIXTURES / "sample_chunks.json")
    settings = _settings()
    # Force one chunk per API call so the second request can raise daily quota.
    settings = Settings(
        database_url=settings.database_url,
        gemini_api_key=settings.gemini_api_key,
        gemini_embedding_model=settings.gemini_embedding_model,
        embedding_provider=settings.embedding_provider,
        embedding_dim=settings.embedding_dim,
        chunks_dir=settings.chunks_dir,
        min_chunk_chars=settings.min_chunk_chars,
        log_level=settings.log_level,
        embed_batch_size=1,
    )
    fake = FakeEmbeddingClient(dim=768)

    class OnceThenDaily:
        on_rate_limited = None

        def __init__(self):
            self.n = 0

        def embed_texts(self, texts):
            self.n += 1
            if self.n > 1:
                raise DailyQuotaExceeded("PerDay FreeTier")
            return fake.embed_texts(texts)

    session = _session_with_hashes()
    result = run_embed_index(session, settings, OnceThenDaily(), chunks=chunks)
    assert result.embedded == 1
    assert result.status == "PARTIAL"
    assert result.stop_reason is not None
    assert "1000/day" in result.stop_reason
    assert "Detail:" not in result.stop_reason
    out = capsys.readouterr().out
    assert "Paused: Gemini free-tier daily embed limit" in out
