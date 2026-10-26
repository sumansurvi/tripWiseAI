"""Tests for human-readable ingest progress lines."""

from io import StringIO

from tripwise.progress import format_progress_line, print_progress


def test_format_progress_with_total():
    line = format_progress_line(
        pages=12,
        total=50,
        succeeded=11,
        failed=0,
        skipped=1,
        queue=28,
        title="Delhi",
    )
    assert line == (
        "progress pages=12/50 succeeded=11 failed=0 skipped=1 queue=28 title=Delhi"
    )


def test_format_progress_open_ended_bfs():
    line = format_progress_line(
        pages=3,
        succeeded=3,
        failed=0,
        skipped=0,
        queue=15,
        title="India",
    )
    assert line.startswith("progress pages=3 ")
    assert "queue=15" in line
    assert "/" not in line.split()[1]  # pages=3 has no denominator


def test_print_progress_writes_stdout():
    buf = StringIO()
    returned = print_progress(
        pages=1,
        total=5,
        succeeded=1,
        title="Agra",
        file=buf,
    )
    assert returned.startswith("progress pages=1/5")
    assert buf.getvalue().strip() == returned
