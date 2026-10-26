"""Compute whether a page is under a scope root via isPartOf ancestry."""

from __future__ import annotations

from typing import Dict, Optional, Set


def normalize_title(title: str) -> str:
    return (title or "").replace("_", " ").strip()


def is_under_scope(
    title: str,
    parent_by_title: Dict[str, Optional[str]],
    scope_root: str,
    *,
    max_hops: int = 32,
) -> bool:
    """True if title equals scope_root or walks to it via parent_by_title."""
    root = normalize_title(scope_root).casefold()
    current = normalize_title(title)
    seen: Set[str] = set()
    for _ in range(max_hops):
        if not current:
            return False
        key = current.casefold()
        if key == root:
            return True
        if key in seen:
            return False
        seen.add(key)
        parent = parent_by_title.get(current) or parent_by_title.get(current.replace(" ", "_"))
        if parent is None:
            # try case-insensitive lookup
            parent = None
            for k, v in parent_by_title.items():
                if normalize_title(k).casefold() == key:
                    parent = v
                    break
        if not parent:
            return False
        current = normalize_title(parent)
    return False


def extract_is_part_of(wikitext: str) -> Optional[str]:
    import re

    match = re.search(r"\{\{\s*isPartOf\s*\|\s*([^}|]+)", wikitext or "", re.I)
    if not match:
        return None
    return normalize_title(match.group(1))
