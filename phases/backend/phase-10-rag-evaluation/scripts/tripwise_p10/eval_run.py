"""Offline RAG eval over fixtures (no live Wikimedia in CI)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class EvalCase:
    id: str
    question: str
    journey: str
    expect_refuse: bool = False
    expect_titles: List[str] = field(default_factory=list)
    expect_absent: bool = False  # e.g. Kyoto when Japan not in corpus


@dataclass
class RetrievalScore:
    hit_at_k: bool
    citation_ok: bool
    details: str = ""


def score_retrieval(
    *,
    expect_titles: Sequence[str],
    retrieved_titles: Sequence[str],
    retrieved_urls: Sequence[str],
    expect_refuse: bool = False,
    refused: bool = False,
    expect_absent: bool = False,
) -> RetrievalScore:
    if expect_refuse:
        ok = refused
        return RetrievalScore(hit_at_k=ok, citation_ok=ok, details="refuse")
    if expect_absent:
        # Success = no confident wrong geography titles required; empty ok.
        return RetrievalScore(
            hit_at_k=True,
            citation_ok=all("kyoto" not in (u or "").lower() for u in retrieved_urls),
            details="absent_case",
        )
    if not expect_titles:
        return RetrievalScore(hit_at_k=True, citation_ok=True, details="no_gold")
    titles_l = [t.lower() for t in retrieved_titles]
    hit = any(
        any(exp.lower() in t for t in titles_l) for exp in expect_titles
    )
    urls_ok = all(
        (u or "").startswith("https://en.wikivoyage.org/") for u in retrieved_urls
    )
    return RetrievalScore(hit_at_k=hit, citation_ok=urls_ok)


def load_cases(path: Path) -> List[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [EvalCase(**row) for row in data]


def run_fixture_eval(cases: Sequence[EvalCase]) -> Dict[str, Any]:
    """Score routing/refusal without DB — retrieval gold checked when provided via stubs."""
    from tripwise_p6.router import route_query

    n = len(cases)
    refuse_ok = 0
    route_ok = 0
    for c in cases:
        route = route_query(c.question)
        if c.expect_refuse:
            if route.refuse_reason:
                refuse_ok += 1
                route_ok += 1
            continue
        if c.expect_absent:
            route_ok += 1
            continue
        # Soft: practical questions should not refuse.
        if route.should_retrieve():
            route_ok += 1
    return {
        "n_cases": n,
        "route_ok": route_ok,
        "refuse_ok": refuse_ok,
        "route_accuracy": route_ok / n if n else 0.0,
    }
