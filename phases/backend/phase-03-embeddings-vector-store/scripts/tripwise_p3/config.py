"""Phase 3 settings: DATABASE_URL + embedding config (local bge default, Gemini fallback)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config").is_dir() and (parent / "docs").is_dir():
            return parent
    return here.parents[5]


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CHUNKS_DIR = DATA_DIR / "chunks"

load_dotenv(CONFIG_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

# gemini-embedding-001 / bge-base-en-v1.5 default output dimensionality
DEFAULT_EMBEDDING_DIM = 768
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
# Local ONNX embeddings are the default so chat is not coupled to Gemini quota.
DEFAULT_EMBEDDING_PROVIDER = "local"
MIN_CHUNK_CHARS = 40
LOCAL_PROVIDERS = frozenset({"local", "bge", "fastembed"})


@dataclass(frozen=True)
class Settings:
    database_url: str
    gemini_api_key: str
    gemini_embedding_model: str
    embedding_provider: str
    embedding_dim: int
    chunks_dir: Path
    min_chunk_chars: int
    log_level: str
    embed_batch_size: int = 32
    embed_min_interval_sec: float = 0.35
    local_embedding_model: str = DEFAULT_LOCAL_EMBEDDING_MODEL


def is_local_provider(provider: str) -> bool:
    return (provider or "").strip().lower() in LOCAL_PROVIDERS


def active_embedding_model(settings: Settings) -> str:
    """Model name stored in content hashes and used by the active client."""
    if is_local_provider(settings.embedding_provider):
        return settings.local_embedding_model
    return settings.gemini_embedding_model


def load_settings() -> Settings:
    provider = (
        os.getenv("TRIPWISE_EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER)
        .strip()
        .lower()
        or DEFAULT_EMBEDDING_PROVIDER
    )
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://tripwise:tripwise@127.0.0.1:5432/tripwise_p1",
        ),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_embedding_model=os.getenv(
            "GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        ).strip(),
        embedding_provider=provider,
        embedding_dim=int(os.getenv("GEMINI_EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM))),
        chunks_dir=Path(os.getenv("TRIPWISE_CHUNKS_DIR", str(CHUNKS_DIR))),
        min_chunk_chars=int(os.getenv("TRIPWISE_MIN_CHUNK_CHARS", str(MIN_CHUNK_CHARS))),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        embed_batch_size=max(1, int(os.getenv("TRIPWISE_EMBED_BATCH_SIZE", "32"))),
        embed_min_interval_sec=float(
            os.getenv("TRIPWISE_EMBED_MIN_INTERVAL_SEC", "0.35")
        ),
        local_embedding_model=os.getenv(
            "TRIPWISE_LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL
        ).strip()
        or DEFAULT_LOCAL_EMBEDDING_MODEL,
    )
