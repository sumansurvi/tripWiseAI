from datetime import datetime, timezone

from sqlalchemy.orm import Session

from tripwise.config import Settings
from tripwise.extract import extract_page
from tripwise.models import Base, Listing, Page, make_engine
from tripwise.persist import content_hash_for, persist_page
from tripwise.pipeline import run_ingestion
from tripwise.source_client import RetrievedPage, WikivoyageClient
from tripwise.validate import validate_extracted_page

from fixtures_util import load_fixture


def _settings(**overrides) -> Settings:
    values = dict(
        database_url="sqlite:///:memory:",
        api_url="https://en.wikivoyage.org/w/api.php",
        user_agent="TripWiseAI-test",
        scope_mode="seeds_and_districts",
        scope_root="Japan",
        seeds=["Tokyo/Shibuya", "Gion"],
        max_depth=0,
        follow_go_next=False,
        allowed_page_types=["country", "region", "city", "district", "park", "unknown"],
        request_delay_seconds=0,
        max_retries=2,
        timeout_seconds=5,
        batch_size=5,
        log_level="INFO",
        log_json=False,
    )
    values.update(overrides)
    return Settings(**values)


def _session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _retrieved(title: str, wiki_id: int, wikitext: str, missing: bool = False) -> RetrievedPage:
    return RetrievedPage(
        requested_title=title,
        title=title,
        wiki_page_id=wiki_id,
        canonical_url=f"https://en.wikivoyage.org/wiki/{title.replace(' ', '_')}",
        revision_id=111,
        revision_timestamp=datetime(2026, 9, 10, tzinfo=timezone.utc),
        sha1="abc",
        wikitext=wikitext,
        missing=missing,
    )


class FakeClient(WikivoyageClient):
    def __init__(self, pages: dict[str, RetrievedPage]):
        self.pages = pages
        self.calls: list[list[str]] = []

    def close(self) -> None:  # noqa: D401
        return

    def fetch_pages(self, titles: list[str]) -> list[RetrievedPage]:
        self.calls.append(list(titles))
        return [self.pages[title] for title in titles]


def test_dedup_unchanged_page_not_duplicated():
    engine, session = _session()
    wikitext = load_fixture("shibuya.wiki")
    extracted = extract_page("Tokyo/Shibuya", wikitext)
    retrieved = _retrieved("Tokyo/Shibuya", 36260, wikitext)
    digest = content_hash_for(wikitext)
    first = persist_page(session, retrieved, extracted, digest)
    session.commit()
    second = persist_page(session, retrieved, extracted, digest)
    session.commit()
    count = session.query(Page).count()
    engine.dispose()
    assert first == "created"
    assert second == "unchanged"
    assert count == 1


def test_changed_revision_reprocessed():
    engine, session = _session()
    original = load_fixture("shibuya.wiki")
    updated = original + "\nUpdated visitor tip.\n"
    retrieved = _retrieved("Tokyo/Shibuya", 36260, original)
    persist_page(session, retrieved, extract_page("Tokyo/Shibuya", original), content_hash_for(original))
    session.commit()
    retrieved.wikitext = updated
    retrieved.revision_id = 222
    outcome = persist_page(session, retrieved, extract_page("Tokyo/Shibuya", updated), content_hash_for(updated))
    session.commit()
    page = session.query(Page).one()
    listing_count = session.query(Listing).count()
    engine.dispose()
    assert outcome == "updated"
    assert page.revision_id == 222
    assert listing_count >= 6


def test_pipeline_skips_missing_and_continues(tmp_path):
    engine, session = _session()
    settings = _settings(data_dir=tmp_path)
    client = FakeClient(
        {
            "Tokyo/Shibuya": _retrieved("Tokyo/Shibuya", 36260, load_fixture("shibuya.wiki")),
            "Gion": _retrieved("Gion", 0, "", missing=True),
        }
    )
    result = run_ingestion(session, settings, client)
    pages = session.query(Page).all()
    engine.dispose()
    assert result.status == "COMPLETED"
    assert result.pages_succeeded == 1
    assert result.pages_skipped == 1
    assert [p.title for p in pages] == ["Tokyo/Shibuya"]


def test_validation_does_not_invent_coordinates():
    wikitext = "{{usabledistrict}}\n'''Nowhere''' has no geo template.\n"
    extracted = extract_page("Nowhere", wikitext)
    assert extracted.latitude is None
    result = validate_extracted_page(
        "Nowhere", 1, "https://en.wikivoyage.org/wiki/Nowhere", wikitext, extracted
    )
    assert result.ok is True
