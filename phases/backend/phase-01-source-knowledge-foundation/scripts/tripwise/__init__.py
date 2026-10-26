"""TripWise Phase 1 — Wikivoyage Action API ingest (India sample).

Aligned with docs/RAG_ARCHITECTURE.md Phase 1:
- Acquisition via Action API (httpx), not Playwright
- Writes data/raw|structured|chunks with source_url
- No LLM rewrite; chat/embeddings are later phases (Groq chat, Gemini embeddings)
"""

__version__ = "0.1.0"
