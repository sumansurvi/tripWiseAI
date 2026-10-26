from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from tripwise.cleaning import normalize_title
from tripwise.extract import ExtractedPage, discoverable_titles
from tripwise.logging_utils import log_event

logger = logging.getLogger("tripwise.ingest.discovery")


@dataclass
class QueueItem:
    title: str
    depth: int
    discovered_from: str | None = None


@dataclass
class DiscoveryState:
    queued: deque[QueueItem] = field(default_factory=deque)
    seen: set[str] = field(default_factory=set)
    discovered: list[str] = field(default_factory=list)

    def enqueue(self, title: str, depth: int, discovered_from: str | None = None) -> bool:
        normalized = normalize_title(title)
        key = normalized.casefold()
        if not normalized or key in self.seen:
            return False
        self.seen.add(key)
        self.queued.append(QueueItem(normalized, depth, discovered_from))
        self.discovered.append(normalized)
        log_event(
            logger,
            logging.INFO,
            "page_discovered",
            page_title=normalized,
            operation="discover",
            status="queued",
        )
        return True


def seed_queue(seeds: list[str]) -> DiscoveryState:
    state = DiscoveryState()
    for seed in seeds:
        state.enqueue(seed, depth=0)
    return state


def maybe_enqueue_children(
    state: DiscoveryState,
    extracted: ExtractedPage,
    *,
    current_depth: int,
    max_depth: int,
    follow_go_next: bool,
    scope_mode: str,
    allowed_page_types: list[str],
) -> int:
    if current_depth >= max_depth:
        return 0
    if extracted.page_type not in set(allowed_page_types) and extracted.page_type != "unknown":
        return 0
    added = 0
    for title in discoverable_titles(
        extracted, follow_go_next=follow_go_next, scope_mode=scope_mode
    ):
        if state.enqueue(title, current_depth + 1, discovered_from=extracted.title):
            added += 1
    return added
