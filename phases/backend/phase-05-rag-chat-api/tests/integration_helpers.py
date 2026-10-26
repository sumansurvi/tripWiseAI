"""Helpers for Phase 5 grounding / integration assertions."""

from __future__ import annotations

import os
import re
from typing import Iterable, Set

import pytest

from tripwise_p5.config import load_settings

WIKIVOYAGE_PREFIX = "https://en.wikivoyage.org/"
PRICE_RE = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*)?(\d{1,3}(?:,\d{2,3})+|\d{4,})",
    re.IGNORECASE,
)


def integration_enabled() -> bool:
    return os.getenv("TRIPWISE_RUN_INTEGRATION", "").strip() == "1"


def require_live_stack():
    """Skip unless opt-in flag and Gemini + Groq + DATABASE_URL are present."""
    if not integration_enabled():
        pytest.skip(
            "Set TRIPWISE_RUN_INTEGRATION=1 to run live Phase 5 integration tests"
        )
    settings = load_settings()
    missing = []
    if not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if not settings.groq_api_key:
        missing.append("GROQ_API_KEY")
    if not settings.database_url:
        missing.append("DATABASE_URL")
    if missing:
        pytest.skip(f"Missing env for integration: {', '.join(missing)}")
    return settings


def prices_in_text(text: str) -> Set[str]:
    return {m.group(1).replace(",", "") for m in PRICE_RE.finditer(text or "")}


def assert_wikivoyage_sources(sources: Iterable) -> None:
    sources = list(sources)
    assert sources, "expected at least one source"
    for s in sources:
        url = s.source_url if hasattr(s, "source_url") else s["source_url"]
        assert url.startswith(WIKIVOYAGE_PREFIX), f"non-Wikivoyage source: {url}"


def assert_no_ungrounded_prices(answer: str, evidence_texts: Iterable[str]) -> None:
    """Fail if answer states a 4+ digit price absent from all evidence text."""
    evidence_blob = "\n".join(evidence_texts)
    evidence_prices = prices_in_text(evidence_blob)
    for price in prices_in_text(answer):
        assert price in evidence_prices, (
            f"ungrounded price {price!r} in answer; not found in evidence"
        )
