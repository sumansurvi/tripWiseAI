"""Short-term conversation slots for follow-up rewrite."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConversationState:
    conversation_id: str
    active_destination: Optional[str] = None
    compared_destinations: List[str] = field(default_factory=list)
    last_domain: Optional[str] = None
    turns: List[Dict[str, str]] = field(default_factory=list)  # role/content

    def append_turn(self, role: str, content: str, *, max_turns: int = 10) -> None:
        self.turns.append({"role": role, "content": content})
        if len(self.turns) > max_turns * 2:
            self.turns = self.turns[-(max_turns * 2) :]


class ConversationStore:
    """Process-local store. Cleared when process restarts; new id clears slots."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: Dict[str, ConversationState] = {}

    def get_or_create(self, conversation_id: Optional[str]) -> ConversationState:
        cid = (conversation_id or "").strip() or str(uuid.uuid4())
        with self._lock:
            state = self._by_id.get(cid)
            if state is None:
                state = ConversationState(conversation_id=cid)
                self._by_id[cid] = state
            return state

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._by_id.pop(conversation_id, None)


def rewrite_with_slots(message: str, state: ConversationState) -> str:
    text = (message or "").strip()
    if not text:
        return text
    if state.active_destination and len(text.split()) <= 8:
        # Short follow-ups benefit from destination hint.
        lowered = text.lower()
        dest = state.active_destination.lower()
        if dest not in lowered and not any(
            d.lower() in lowered for d in state.compared_destinations
        ):
            return f"{text} (regarding {state.active_destination})"
    return text


DEFAULT_STORE = ConversationStore()
