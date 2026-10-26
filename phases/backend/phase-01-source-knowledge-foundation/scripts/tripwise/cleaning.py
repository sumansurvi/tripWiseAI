from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import urlparse

WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
EXTERNAL_LINK_RE = re.compile(r"\[(https?://[^\s\]]+)\s+([^\]]+)\]")
BARE_EXTERNAL_RE = re.compile(r"\[(https?://[^\s\]]+)\]")
TEMPLATE_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.S)
REF_RE = re.compile(r"<ref\b[^>]*>.*?</ref>", re.I | re.S)
TAG_RE = re.compile(r"</?[^>]+>")
BOLD_ITALIC_RE = re.compile(r"'{2,}")
TABLE_ROW_RE = re.compile(r"^\s*[|!].*$", re.M)
HEADING_MARK_RE = re.compile(r"^={2,6}\s*(.+?)\s*={2,6}\s*$", re.M)
MULTI_NL_RE = re.compile(r"\n{3,}")
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    cleaned = html.unescape(title or "").strip()
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned.startswith(":"):
        cleaned = cleaned[1:]
    return cleaned


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    return value


def heading_display(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def strip_wikitext(wikitext: str, keep_headings: bool = True) -> str:
    """Clean source text. Does not summarize or rewrite meaning."""
    text = html.unescape(wikitext or "")
    text = REF_RE.sub("", text)
    text = text.replace("&nbsp;", " ")
    if keep_headings:
        text = HEADING_MARK_RE.sub(lambda m: m.group(1).strip(), text)
    text = WIKI_LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)
    text = EXTERNAL_LINK_RE.sub(lambda m: m.group(2).strip(), text)
    text = BARE_EXTERNAL_RE.sub(lambda m: m.group(1), text)
    # Remove templates after listings have already been extracted elsewhere.
    for _ in range(8):
        next_text = TEMPLATE_RE.sub("", text)
        if next_text == text:
            break
        text = next_text
    text = TAG_RE.sub("", text)
    text = BOLD_ITALIC_RE.sub("", text)
    text = TABLE_ROW_RE.sub("", text)
    text = text.replace("{{", " ").replace("}}", " ")
    text = MULTI_SPACE_RE.sub(" ", text)
    text = MULTI_NL_RE.sub("\n\n", text)
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = "\n".join(lines).strip()
    return cleaned


def is_empty_prose(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return len(compact) < 8
