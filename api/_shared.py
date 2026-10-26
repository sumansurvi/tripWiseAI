"""Shared bootstrap for Vercel Python functions (FastAPI under /api/*)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_BOOTSTRAPPED = False
_STATE: Dict[str, Any] = {}


def bootstrap() -> None:
    """Add phase script dirs to sys.path once; force Gemini embeddings on Vercel."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    root = Path(__file__).resolve().parents[1]
    backend = root / "phases" / "backend"
    script_dirs = [
        backend / "phase-05-rag-chat-api" / "scripts",
        backend / "phase-03-embeddings-vector-store" / "scripts",
        backend / "phase-06-query-routing" / "scripts",
        backend / "phase-07-hybrid-retrieval" / "scripts",
        backend / "phase-08-conversation" / "scripts",
        backend / "phase-09-comparison-recommendations" / "scripts",
    ]
    for path in reversed(script_dirs):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    # Vercel sets VERCEL=1. Production chat cannot ship local bge/ONNX.
    if os.getenv("VERCEL") == "1":
        os.environ["TRIPWISE_EMBEDDING_PROVIDER"] = "gemini"

    from tripwise_p3.warnings_util import suppress_vendor_noise

    suppress_vendor_noise(quiet_http_logs=True)
    _BOOTSTRAPPED = True


def get_runtime() -> Dict[str, Any]:
    """Lazy-init settings + embed + chat + DB session factory (cold-start friendly)."""
    bootstrap()
    if _STATE.get("ready"):
        return _STATE

    from pathlib import Path as _Path

    from tripwise_p3.config import Settings as P3Settings
    from tripwise_p3.config import is_local_provider
    from tripwise_p3.embedding_client import make_embedding_client
    from tripwise_p3.models import make_session_factory
    from tripwise_p5.config import load_settings
    from tripwise_p5.groq_client import GroqChatClient

    settings = load_settings()
    if is_local_provider(settings.embedding_provider):
        # Serverless bundle omits fastembed; refuse local on Vercel.
        if os.getenv("VERCEL") == "1":
            raise RuntimeError(
                "TRIPWISE_EMBEDDING_PROVIDER=local is not supported on Vercel. "
                "Set TRIPWISE_EMBEDDING_PROVIDER=gemini and re-embed Supabase."
            )

    if not is_local_provider(settings.embedding_provider) and not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required when TRIPWISE_EMBEDDING_PROVIDER=gemini")
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required for /chat generation")

    engine, factory = make_session_factory(settings.database_url)
    p3 = P3Settings(
        database_url=settings.database_url,
        gemini_api_key=settings.gemini_api_key,
        gemini_embedding_model=settings.gemini_embedding_model,
        embedding_provider=settings.embedding_provider,
        embedding_dim=settings.embedding_dim,
        chunks_dir=_Path("."),
        min_chunk_chars=40,
        log_level=settings.log_level,
        local_embedding_model=settings.local_embedding_model,
    )
    embed = make_embedding_client(p3, probe=False)
    chat = GroqChatClient(settings.groq_api_key, settings.groq_model)

    _STATE.update(
        {
            "ready": True,
            "settings": settings,
            "embed_client": embed,
            "chat_client": chat,
            "session_factory": factory,
            "engine": engine,
        }
    )
    return _STATE


def run_chat_payload(
    message: str,
    *,
    history: Optional[list] = None,
    conversation_id: Optional[str] = None,
) -> dict:
    from tripwise_p5.rag import chat_result_to_dict, run_chat_turn

    runtime = get_runtime()
    factory = runtime["session_factory"]
    with factory() as session:
        result = run_chat_turn(
            session,
            runtime["settings"],
            runtime["embed_client"],
            runtime["chat_client"],
            message,
            history=history or [],
            conversation_id=conversation_id,
        )
    return chat_result_to_dict(result)
