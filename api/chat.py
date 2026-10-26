"""Vercel serverless: POST /api/chat → TripWise RAG turn."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

# Sibling import (Vercel may not treat api/ as a package on PYTHONPATH).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from _shared import bootstrap, run_chat_payload

bootstrap()

app = FastAPI(title="TripWise Chat", docs_url=None, redoc_url=None)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=0)
    history: List[Any] = Field(default_factory=list)
    conversation_id: Optional[str] = None


@app.post("/")
def chat(body: ChatRequest) -> dict:
    try:
        return run_chat_payload(
            body.message,
            history=body.history,
            conversation_id=body.conversation_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
