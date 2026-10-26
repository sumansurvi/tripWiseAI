"""Heuristic intent / entity routing for TripWise chat."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from tripwise_p5.scope import check_personal_info
except ImportError:  # pragma: no cover

    def check_personal_info(message: str) -> Optional[str]:
        text = (message or "").strip()
        if not text:
            return "empty_message"
        if re.search(r"\b(passport|what is my|what's my)\b", text, re.I):
            return "personal_information"
        return None


# Destinations the router can pin to a Wikivoyage title. Keep in sync with what is
# actually ingested; unknown places fall through to unfiltered vector search + the
# relevance gate (which answers "I don't know" for out-of-corpus places).
KNOWN_DESTINATIONS = (
    "Delhi",
    "Old Delhi",
    "New Delhi",
    "Mumbai",
    "Bombay",
    "Jaipur",
    "Goa",
    "Kolkata",
    "Agra",
    "Varanasi",
    "Leh",
    "India",
)

HUGE_CITY_PARENTS = {
    # Values must match Wikivoyage titles in the corpus (e.g. "Delhi/South").
    "delhi": ["Old Delhi", "New Delhi", "Delhi/South", "Delhi/North"],
    "mumbai": ["Mumbai/South", "Mumbai/Fort"],
}

PRACTICAL_RE = re.compile(
    r"\b(currency|visa|sim|atm|money|budget|plug|voltage|safety|emergency|"
    r"clinic|hospital|embassy|consulate|language|phrase)\b",
    re.I,
)
FOOD_RE = re.compile(
    r"\b(eat|food|restaurant|cuisine|street food|drink|bar|cafe|café)\b", re.I
)
TRANSPORT_RE = re.compile(
    r"\b(metro|train|bus|taxi|uber|auto|airport|flight|get around|transport)\b",
    re.I,
)
COMPARE_RE = re.compile(
    r"\b(vs\.?|versus|compare|comparison|which is (cheaper|better))\b", re.I
)
FOLLOWUP_RE = re.compile(
    r"\b(there|that place|same city|cheaper|also|what about)\b", re.I
)


@dataclass
class RouteResult:
    intent: str
    entities: List[str] = field(default_factory=list)
    title_filters: List[str] = field(default_factory=list)
    section_hint: Optional[str] = None
    refuse_reason: Optional[str] = None
    rewritten_query: Optional[str] = None

    def should_retrieve(self) -> bool:
        return self.refuse_reason is None and self.intent not in {
            "personal_info",
            "out_of_scope",
        }


def _extract_entities(text: str) -> List[str]:
    """Known destinations in order of appearance; longest match wins on overlap
    (so "Old Delhi" does not also yield "Delhi")."""
    lower = text.lower()
    taken: List[tuple] = []  # (start, end, name)
    for name in sorted(KNOWN_DESTINATIONS, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(name.lower())}\b", lower):
            if any(m.start() < e and m.end() > b for b, e, _ in taken):
                continue
            taken.append((m.start(), m.end(), name))
    taken.sort(key=lambda t: t[0])
    found: List[str] = []
    for _, _, name in taken:
        if name not in found:
            found.append(name)
    return found


def extract_entities(text: str) -> List[str]:
    """Public wrapper: destinations explicitly named in ``text``."""
    return _extract_entities(text)


def _expand_huge_cities(entities: List[str], *, overview_only: bool) -> List[str]:
    if overview_only:
        return list(entities)
    out: List[str] = []
    for e in entities:
        key = e.lower()
        if key in HUGE_CITY_PARENTS:
            out.extend(HUGE_CITY_PARENTS[key])
        out.append(e)
    # unique preserve order
    seen = set()
    uniq: List[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def route_query(
    message: str,
    *,
    active_destination: Optional[str] = None,
) -> RouteResult:
    text = (message or "").strip()
    reason = check_personal_info(text)
    if reason == "empty_message":
        return RouteResult(intent="out_of_scope", refuse_reason=reason)
    if reason:
        return RouteResult(intent="personal_info", refuse_reason=reason)

    entities = _extract_entities(text)
    if not entities and active_destination:
        entities = [active_destination]

    overview_only = bool(
        re.search(r"\b(overview|general|about the city)\b", text, re.I)
    )
    title_filters = _expand_huge_cities(entities, overview_only=overview_only)

    if COMPARE_RE.search(text) and len(entities) >= 2:
        return RouteResult(
            intent="comparison",
            entities=entities,
            title_filters=title_filters,
            rewritten_query=text,
        )
    if PRACTICAL_RE.search(text):
        # Country practical often lives on India page.
        filters = title_filters or ["India"]
        return RouteResult(
            intent="practical",
            entities=entities or ["India"],
            title_filters=filters,
            section_hint="Understand",
            rewritten_query=text,
        )
    if FOOD_RE.search(text):
        return RouteResult(
            intent="food",
            entities=entities,
            title_filters=title_filters,
            section_hint="Eat",
            rewritten_query=text,
        )
    if TRANSPORT_RE.search(text):
        return RouteResult(
            intent="transport",
            entities=entities,
            title_filters=title_filters,
            section_hint="Get around",
            rewritten_query=text,
        )
    if FOLLOWUP_RE.search(text) and active_destination:
        rewritten = f"{text} (about {active_destination})"
        return RouteResult(
            intent="follow_up",
            entities=entities or [active_destination],
            title_filters=title_filters or [active_destination],
            rewritten_query=rewritten,
        )

    return RouteResult(
        intent="destination",
        entities=entities,
        title_filters=title_filters,
        rewritten_query=text,
    )
