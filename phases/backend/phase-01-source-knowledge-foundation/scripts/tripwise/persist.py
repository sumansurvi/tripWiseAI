from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tripwise.cleaning import sha256_text
from tripwise.extract import ExtractedPage
from tripwise.models import Listing, Page, PageRelationship, PageSection, Source
from tripwise.source_client import RetrievedPage

WIKIVOYAGE_SOURCE_ID = "wikivoyage-en"
LICENSE_NAME = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
SOURCE_HOME = "https://en.wikivoyage.org/"


def ensure_source(session: Session) -> Source:
    source = session.get(Source, WIKIVOYAGE_SOURCE_ID)
    if source:
        return source
    source = Source(
        id=WIKIVOYAGE_SOURCE_ID,
        name="English Wikivoyage",
        base_url=SOURCE_HOME,
        license_name=LICENSE_NAME,
        license_url=LICENSE_URL,
        attribution_template=(
            "Text from English Wikivoyage article '{title}' "
            "(https://en.wikivoyage.org/w/index.php?title={title}&oldid={revision_id}), "
            "licensed under CC BY-SA 4.0."
        ),
    )
    session.add(source)
    session.flush()
    return source


def attribution_for(title: str, revision_id: int | None) -> str:
    oldid = revision_id or ""
    encoded = title.replace(" ", "_")
    return (
        f"Text from English Wikivoyage article '{title}' "
        f"(https://en.wikivoyage.org/w/index.php?title={encoded}&oldid={oldid}), "
        "licensed under CC BY-SA 4.0."
    )


def persist_page(
    session: Session,
    retrieved: RetrievedPage,
    extracted: ExtractedPage,
    content_hash: str,
) -> str:
    """Insert or update a page. Returns created|updated|unchanged."""
    now = datetime.now(timezone.utc)
    source = ensure_source(session)
    existing = session.scalar(
        select(Page).where(
            Page.source_id == source.id, Page.wiki_page_id == retrieved.wiki_page_id
        )
    )
    if existing and existing.content_hash == content_hash:
        existing.last_seen_at = now
        existing.retrieved_at = retrieved.revision_timestamp or now
        return "unchanged"

    if existing:
        existing.title = retrieved.title
        existing.canonical_url = retrieved.canonical_url
        existing.page_type = extracted.page_type
        existing.article_status = extracted.article_status
        existing.parent_title = extracted.parent_title
        existing.latitude = extracted.latitude
        existing.longitude = extracted.longitude
        existing.revision_id = retrieved.revision_id
        existing.revision_timestamp = retrieved.revision_timestamp
        existing.retrieved_at = now
        existing.last_seen_at = now
        existing.content_hash = content_hash
        existing.raw_wikitext = retrieved.wikitext
        existing.lead_text = extracted.lead_text or None
        existing.license = LICENSE_NAME
        existing.attribution = attribution_for(retrieved.title, retrieved.revision_id)
        existing.is_huge_city = extracted.is_huge_city
        session.execute(delete(Listing).where(Listing.page_id == existing.id))
        session.execute(delete(PageSection).where(PageSection.page_id == existing.id))
        page = existing
        outcome = "updated"
    else:
        page = Page(
            id=str(uuid.uuid4()),
            source_id=source.id,
            wiki_page_id=retrieved.wiki_page_id,
            title=retrieved.title,
            canonical_url=retrieved.canonical_url,
            page_type=extracted.page_type,
            article_status=extracted.article_status,
            parent_title=extracted.parent_title,
            latitude=extracted.latitude,
            longitude=extracted.longitude,
            revision_id=retrieved.revision_id,
            revision_timestamp=retrieved.revision_timestamp,
            retrieved_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=content_hash,
            raw_wikitext=retrieved.wikitext,
            lead_text=extracted.lead_text or None,
            license=LICENSE_NAME,
            attribution=attribution_for(retrieved.title, retrieved.revision_id),
            is_huge_city=extracted.is_huge_city,
        )
        session.add(page)
        session.flush()
        outcome = "created"

    path_to_section: dict[str, str] = {}
    for section in extracted.sections:
        row = PageSection(
            id=str(uuid.uuid4()),
            page_id=page.id,
            heading_level=section.heading_level,
            section_title=section.section_title,
            subsection_title=section.subsection_title,
            heading_path=section.heading_path,
            sort_order=section.sort_order,
            wikitext=section.wikitext,
            cleaned_text=section.cleaned_text,
            content_hash=section.content_hash,
        )
        session.add(row)
        path_to_section[section.heading_path] = row.id

    session.flush()

    for listing in extracted.listings:
        session.add(
            Listing(
                id=str(uuid.uuid4()),
                page_id=page.id,
                section_id=path_to_section.get(listing.section_path),
                listing_kind=listing.listing_kind,
                name=listing.name,
                alt_name=listing.alt_name,
                description=listing.description,
                address=listing.address,
                directions=listing.directions,
                latitude=listing.latitude,
                longitude=listing.longitude,
                url=listing.url,
                phone=listing.phone,
                hours=listing.hours,
                price_raw=listing.price_raw,
                lastedit=listing.lastedit,
                wikidata_id=listing.wikidata_id,
                wikipedia_title=listing.wikipedia_title,
                extra=listing.extra or None,
                sort_order=listing.sort_order,
            )
        )

    for rel in extracted.relationships:
        found = session.scalar(
            select(PageRelationship).where(
                PageRelationship.from_title == retrieved.title,
                PageRelationship.to_title == rel.to_title,
                PageRelationship.relationship_type == rel.relationship_type,
            )
        )
        if found:
            found.from_page_id = page.id
            continue
        session.add(
            PageRelationship(
                id=str(uuid.uuid4()),
                from_page_id=page.id,
                from_title=retrieved.title,
                to_title=rel.to_title,
                relationship_type=rel.relationship_type,
            )
        )

    return outcome


def content_hash_for(wikitext: str) -> str:
    return sha256_text(wikitext)
