"""Heuristic personal-info / out-of-scope refusal (no LLM)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Patterns that indicate personal data or clearly out-of-scope asks.
# Match requests FOR personal data (numbers, records, "what is my <private thing>"),
# not travel questions that merely mention a document ("Do I need a passport for India?").
_PRIVATE_NOUNS = (
    r"(?:passport|aadhaar|aadhar|ssn|social security|pan|bank|card|account|"
    r"medical|health|phone|email|e-mail|address|dob|date of birth|birthday|"
    r"age|name|salary|income|password|pin|id|license|licence|visa (?:number|status))"
)
_PII_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:passport|visa|aadhaar|aadhar|pan|driving licen[cs]e|id)\s*(?:number|no\.?|details|copy|scan)\b",
        r"\b(?:aadhaar|aadhar|ssn)\b",
        r"\bsocial security\b",
        r"\bbank (?:account|details|balance)\b",
        r"\brouting number\b",
        r"\b(?:credit|debit) card\b",
        r"\bmedical (?:record|history)s?\b",
        r"\b(?:my|his|her|their)\s+(?:phone number|email|e-mail|home address|address|dob)\b",
        # "what is my <private noun>" — but not "what is my best option ..."
        rf"\bwhat(?:'s|s| is| are)\s+(?:my|his|her|their)\s+{_PRIVATE_NOUNS}\b",
        r"\btell me (?:my|his|her|their)\s+(?:medical|bank|passport|personal)\b",
        r"\bpersonal (?:data|information|info)\b",
        r"\bdate of birth\b",
        r"\bmy dob\b",
    )
]

# Polite reply when retrieval finds nothing relevant (never answered from the LLM alone).
NO_ANSWER_MESSAGE = (
    "Sorry, I couldn't find anything about that in my travel sources yet. "
    "I can help with destination questions grounded in Wikivoyage: places to visit, "
    "food, getting around, where to stay, and practical tips. "
    "Try asking about a specific city or region, for example "
    "“What should I eat in Old Delhi?”"
)

REFUSAL_MESSAGE = (
    "Personal information is outside TripWise’s scope. "
    "I can help with destination research grounded in Wikivoyage "
    "(places, food, transport, practical travel tips), not personal data."
)


def check_personal_info(message: str) -> Optional[str]:
    """Return refusal reason if message looks like a personal-info ask, else None."""
    text = (message or "").strip()
    if not text:
        return "empty_message"
    for pat in _PII_PATTERNS:
        if pat.search(text):
            return "personal_information"
    return None


def is_in_scope_travel(message: str) -> Tuple[bool, Optional[str]]:
    """Convenience: (ok_to_retrieve, refusal_reason)."""
    reason = check_personal_info(message)
    if reason:
        return False, reason
    return True, None
