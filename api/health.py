"""Vercel serverless: GET /api/health."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="TripWise Health", docs_url=None, redoc_url=None)


@app.get("/")
@app.get("")
def health() -> dict:
    return {"status": "ok"}
