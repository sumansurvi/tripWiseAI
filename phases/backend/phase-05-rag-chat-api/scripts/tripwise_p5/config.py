"""Phase 5 settings: DB + retrieve embeddings + Groq chat."""

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

load_dotenv(CONFIG_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_TOP_K = 5
DEFAULT_EMBEDDING_PROVIDER = "local"
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
# Calibrated 2026-10-01 on BAAI/bge-base-en-v1.5 @768d over the India corpus
# (calibrate-gate: in-corpus min ≈ 0.67, out-of-corpus max ≈ 0.62).
DEFAULT_MIN_SCORE = 0.64


@dataclass(frozen=True)
class Settings:
    database_url: str
    gemini_api_key: str
    gemini_embedding_model: str
    embedding_dim: int
    groq_api_key: str
    groq_model: str
    top_k: int
    min_score: float
    log_level: str
    host: str
    port: int
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    local_embedding_model: str = DEFAULT_LOCAL_EMBEDDING_MODEL


def load_settings() -> Settings:
    # On Vercel, default to Gemini (local bge/ONNX is not in the serverless bundle).
    default_provider = DEFAULT_EMBEDDING_PROVIDER
    if os.getenv("VERCEL") == "1":
        default_provider = "gemini"
    provider = (
        os.getenv("TRIPWISE_EMBEDDING_PROVIDER", default_provider)
        .strip()
        .lower()
        or default_provider
    )
    # Gemini-calibrated gate when serving with Gemini on Vercel (override via env).
    default_min = DEFAULT_MIN_SCORE
    if provider == "gemini" and os.getenv("TRIPWISE_CHAT_MIN_SCORE") is None:
        default_min = 0.65
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://tripwise:tripwise@127.0.0.1:5432/tripwise_p1",
        ),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_embedding_model=os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
        ).strip(),
        embedding_dim=int(os.getenv("GEMINI_EMBEDDING_DIM", "768")),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
        or DEFAULT_GROQ_MODEL,
        top_k=int(os.getenv("TRIPWISE_CHAT_TOP_K", str(DEFAULT_TOP_K))),
        min_score=float(os.getenv("TRIPWISE_CHAT_MIN_SCORE", str(default_min))),
        log_level=os.getenv("LOG_LEVEL", "WARNING").upper(),
        host=os.getenv("TRIPWISE_CHAT_HOST", "127.0.0.1"),
        port=int(os.getenv("TRIPWISE_CHAT_PORT", "8000")),
        embedding_provider=provider,
        local_embedding_model=(
            os.getenv(
                "TRIPWISE_LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL
            ).strip()
            or DEFAULT_LOCAL_EMBEDDING_MODEL
        ),
    )
