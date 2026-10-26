"""Comparison support: balanced evidence for two destinations.

The written comparison and the "What I recommend" line come from the single Groq
call (grounded only in the retrieved chunks). This module never fabricates
recommendation text or exposes chunk counts / internal retrieval stats to users.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from tripwise_p3.retrieve import RetrieveHit


@dataclass
class TradeOff:
    aspect: str
    destination_a: str
    destination_b: str
    note: str


@dataclass
class ComparisonResult:
    trade_offs: List[TradeOff] = field(default_factory=list)
    recommendation: Optional[str] = None
    evidence: List[RetrieveHit] = field(default_factory=list)
    # Destinations for which no retrieved evidence was found.
    missing: List[str] = field(default_factory=list)


def _hits_for(title: str, hits: Sequence[RetrieveHit]) -> List[RetrieveHit]:
    t = title.lower()
    return [h for h in hits if t in (h.title or "").lower()]


def interleave(*groups: Sequence[RetrieveHit]) -> List[RetrieveHit]:
    """Round-robin merge so every side is represented, de-duplicated by chunk id."""
    merged: List[RetrieveHit] = []
    seen = set()
    longest = max((len(g) for g in groups), default=0)
    for i in range(longest):
        for g in groups:
            if i < len(g) and g[i].chunk_id not in seen:
                seen.add(g[i].chunk_id)
                merged.append(g[i])
    return merged


def build_comparison(
    destinations: Sequence[str],
    hits: Sequence[RetrieveHit],
    *,
    intent: str = "comparison",
) -> ComparisonResult:
    if len(destinations) < 2:
        return ComparisonResult(evidence=list(hits))
    a, b = destinations[0], destinations[1]
    a_hits = _hits_for(a, hits)
    b_hits = _hits_for(b, hits)
    missing = [d for d, h in ((a, a_hits), (b, b_hits)) if not h]
    merged = interleave(a_hits, b_hits)
    # Keep any remaining hits after the balanced core.
    seen = {h.chunk_id for h in merged}
    merged.extend(h for h in hits if h.chunk_id not in seen)
    return ComparisonResult(evidence=merged, missing=missing)


def comparison_to_dict(result: ComparisonResult) -> dict:
    return {
        "trade_offs": [asdict(t) for t in result.trade_offs],
        "recommendation": result.recommendation,
    }
