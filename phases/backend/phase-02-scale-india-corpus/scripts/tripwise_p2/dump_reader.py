"""Stream MediaWiki XML dumps (plain or .bz2) and yield page title/text/id."""

from __future__ import annotations

import bz2
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, TextIO
import xml.etree.ElementTree as ET


@dataclass
class DumpPage:
    title: str
    wiki_page_id: int
    revision_id: Optional[int]
    wikitext: str
    redirect_target: Optional[str] = None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _open_dump(path: Path) -> TextIO:
    if str(path).endswith(".bz2"):
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("rt", encoding="utf-8", errors="replace")


def iter_dump_pages(path: Path) -> Iterator[DumpPage]:
    """Yield main-namespace-ish pages from a pages-articles dump."""
    with _open_dump(path) as handle:
        context = ET.iterparse(handle, events=("end",))
        for _event, elem in context:
            if _local(elem.tag) != "page":
                continue
            title = None
            page_id = None
            rev_id = None
            text = ""
            redirect = None
            for child in elem:
                name = _local(child.tag)
                if name == "title":
                    title = (child.text or "").strip()
                elif name == "id" and page_id is None:
                    try:
                        page_id = int(child.text or "0")
                    except ValueError:
                        page_id = 0
                elif name == "redirect":
                    redirect = child.attrib.get("title")
                elif name == "revision":
                    for rev_child in child:
                        rname = _local(rev_child.tag)
                        if rname == "id" and rev_id is None:
                            try:
                                rev_id = int(rev_child.text or "0")
                            except ValueError:
                                rev_id = None
                        elif rname == "text":
                            text = rev_child.text or ""
            elem.clear()
            if not title or page_id is None:
                continue
            # Skip talk/user/etc. Main namespace titles have no leading Namespace:
            if ":" in title and not title.startswith("Wikipedia:"):
                # Allow City/District subpages; skip Category:, Template:, etc.
                ns = title.split(":", 1)[0]
                if ns in {
                    "Category",
                    "Template",
                    "File",
                    "Image",
                    "Module",
                    "Help",
                    "MediaWiki",
                    "User",
                    "Talk",
                    "Wikivoyage",
                    "Special",
                }:
                    continue
            yield DumpPage(
                title=title,
                wiki_page_id=page_id,
                revision_id=rev_id,
                wikitext=text,
                redirect_target=redirect,
            )
