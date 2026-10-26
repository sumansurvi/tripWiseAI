"""Phase 2 unit tests: ancestry + dump ingest under India scope."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from tripwise.config import Settings
from tripwise.models import Base, Page, make_engine
from tripwise_p2.ancestry import extract_is_part_of, is_under_scope
from tripwise_p2.dump_ingest import run_dump_ingestion
from tripwise_p2.dump_reader import iter_dump_pages

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        api_url="https://en.wikivoyage.org/w/api.php",
        user_agent="TripWiseAI-test",
        scope_mode="scope_root",
        scope_root="India",
        seeds=["India"],
        max_depth=12,
        follow_go_next=False,
        allowed_page_types=[
            "country",
            "region",
            "city",
            "district",
            "park",
            "topic",
            "airport",
            "unknown",
        ],
        skip_page_types=["itinerary", "phrasebook"],
        max_pages=0,
        request_delay_seconds=0,
        max_retries=1,
        timeout_seconds=5,
        batch_size=5,
        log_level="WARNING",
        log_json=False,
    )


def test_is_under_scope_walks_parents():
    parents = {
        "Delhi/Old Delhi": "Delhi",
        "Delhi": "Northern India",
        "Northern India": "India",
        "India": "South Asia",
        "Japan": "East Asia",
    }
    assert is_under_scope("Delhi/Old Delhi", parents, "India")
    assert is_under_scope("India", parents, "India")
    assert not is_under_scope("Japan", parents, "India")


def test_extract_is_part_of():
    assert extract_is_part_of("{{isPartOf|India}}\nHello") == "India"
    assert extract_is_part_of("no template") is None


def test_iter_dump_pages_reads_fixture():
    pages = list(iter_dump_pages(FIXTURES / "india_sample_dump.xml"))
    titles = {p.title for p in pages}
    assert "India" in titles
    assert "Delhi/Old Delhi" in titles
    assert "Japan" in titles


def test_dump_ingest_keeps_india_skips_japan_and_itinerary(tmp_path, monkeypatch):
    import tripwise.export_json as export_json

    monkeypatch.setattr(export_json, "DATA_DIR", tmp_path)

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = run_dump_ingestion(
            session, _settings(), FIXTURES / "india_sample_dump.xml"
        )
        assert result.status == "COMPLETED"
        titles = sorted(session.scalars(select(Page.title)).all())
        assert "India" in titles
        assert "Delhi" in titles
        assert "Delhi/Old Delhi" in titles
        assert "Northern India" in titles
        assert "Japan" not in titles
        assert "Sample itinerary" not in titles
        for page in session.scalars(select(Page)).all():
            assert page.canonical_url.startswith("https://en.wikivoyage.org/wiki/")
    engine.dispose()
