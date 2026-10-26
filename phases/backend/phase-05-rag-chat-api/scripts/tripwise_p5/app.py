"""FastAPI app: POST /chat."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from tripwise_p3.config import Settings as P3Settings
from tripwise_p3.config import is_local_provider
from tripwise_p3.embedding_client import EmbeddingClient, make_embedding_client
from tripwise_p3.models import make_session_factory
from tripwise_p5.config import Settings, load_settings
from tripwise_p5.groq_client import ChatClient, GroqChatClient
from tripwise_p5.rag import chat_result_to_dict, run_chat_turn

logger = logging.getLogger("tripwise.phase5.api")


def _cors_origins() -> List[str]:
    """Localhost defaults plus TRIPWISE_CORS_ORIGINS (comma-separated)."""
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    extra = os.getenv("TRIPWISE_CORS_ORIGINS", "").strip()
    if extra:
        for part in extra.split(","):
            origin = part.strip().rstrip("/")
            if origin and origin not in origins:
                origins.append(origin)
    # Same-origin Vercel UI → API does not need CORS; still allow preview URLs.
    vercel_url = os.getenv("VERCEL_URL", "").strip()
    if vercel_url:
        https = f"https://{vercel_url}"
        if https not in origins:
            origins.append(https)
    return origins


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=0)
    history: List[Any] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    evidence: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    refused: bool
    refusal_reason: Optional[str] = None
    conversation_id: Optional[str] = None
    recommendation: Optional[str] = None
    trade_offs: List[Dict[str, Any]] = Field(default_factory=list)
    intent: Optional[str] = None


def create_app(
    settings: Optional[Settings] = None,
    *,
    embed_client: Optional[EmbeddingClient] = None,
    chat_client: Optional[ChatClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> FastAPI:
    settings = settings or load_settings()

    state: Dict[str, Any] = {
        "settings": settings,
        "embed_client": embed_client,
        "chat_client": chat_client,
        "session_factory": session_factory,
        "engine": None,
    }

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, settings.log_level, logging.WARNING),
            format="%(levelname)s %(name)s: %(message)s",
        )
        # Quiet noisy HTTP / client libs unless LOG_LEVEL=DEBUG
        for name in ("httpx", "httpcore", "groq", "google", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)
        if state["session_factory"] is None:
            engine, factory = make_session_factory(settings.database_url)
            state["engine"] = engine
            state["session_factory"] = factory
        if state["embed_client"] is None:
            p3 = P3Settings(
                database_url=settings.database_url,
                gemini_api_key=settings.gemini_api_key,
                gemini_embedding_model=settings.gemini_embedding_model,
                embedding_provider=settings.embedding_provider,
                embedding_dim=settings.embedding_dim,
                chunks_dir=Path("."),
                min_chunk_chars=40,
                log_level=settings.log_level,
                local_embedding_model=settings.local_embedding_model,
            )
            if not is_local_provider(p3.embedding_provider) and not settings.gemini_api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is required when TRIPWISE_EMBEDDING_PROVIDER=gemini"
                )
            # probe=False: a Gemini 429 must not prevent the API from starting.
            state["embed_client"] = make_embedding_client(p3, probe=False)
        if state["chat_client"] is None:
            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY is required for /chat generation")
            state["chat_client"] = GroqChatClient(
                settings.groq_api_key, settings.groq_model
            )
        yield
        engine = state.get("engine")
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="TripWise RAG Chat",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(body: ChatRequest) -> ChatResponse:
        factory = state["session_factory"]
        if factory is None:
            raise HTTPException(status_code=503, detail="DB not ready")
        with factory() as session:
            result = run_chat_turn(
                session,
                state["settings"],
                state["embed_client"],
                state["chat_client"],
                body.message,
                history=body.history,
                conversation_id=body.conversation_id,
            )
        return ChatResponse(**chat_result_to_dict(result))

    return app
