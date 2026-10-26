"""Human-readable ingest progress lines for the terminal."""

from __future__ import annotations

from typing import Optional, TextIO
import sys


def format_progress_line(
    *,
    pages: int,
    total: Optional[int] = None,
    succeeded: int = 0,
    failed: int = 0,
    skipped: int = 0,
    queue: Optional[int] = None,
    title: str = "",
) -> str:
    """Build a single progress line.

    When ``total`` is set (max_pages or known in-scope count), show ``pages=N/T``.
    Otherwise show ``pages=N`` plus optional ``queue=Q`` for open-ended BFS.
    """
    if total is not None and total > 0:
        pages_part = f"pages={pages}/{total}"
    else:
        pages_part = f"pages={pages}"
    parts = [
        "progress",
        pages_part,
        f"succeeded={succeeded}",
        f"failed={failed}",
        f"skipped={skipped}",
    ]
    if queue is not None:
        parts.append(f"queue={queue}")
    if title:
        parts.append(f"title={title}")
    return " ".join(parts)


def print_progress(
    *,
    pages: int,
    total: Optional[int] = None,
    succeeded: int = 0,
    failed: int = 0,
    skipped: int = 0,
    queue: Optional[int] = None,
    title: str = "",
    file: Optional[TextIO] = None,
) -> str:
    """Print a progress line to stdout (or ``file``) and return it."""
    line = format_progress_line(
        pages=pages,
        total=total,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        queue=queue,
        title=title,
    )
    out = file if file is not None else sys.stdout
    print(line, file=out, flush=True)
    return line
