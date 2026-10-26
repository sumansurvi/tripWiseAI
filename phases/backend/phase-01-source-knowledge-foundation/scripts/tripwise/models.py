from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    license_name: Mapped[Optional[str]] = mapped_column(Text)
    license_url: Mapped[Optional[str]] = mapped_column(Text)
    attribution_template: Mapped[Optional[str]] = mapped_column(Text)

    pages: Mapped[List["Page"]] = relationship(back_populates="source")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0)
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    pages_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(BigInteger)

    errors: Mapped[List["IngestionError"]] = relationship(back_populates="run")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("source_id", "wiki_page_id", name="uq_pages_source_wiki"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    wiki_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    page_type: Mapped[Optional[str]] = mapped_column(Text)
    article_status: Mapped[Optional[str]] = mapped_column(Text)
    parent_title: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    revision_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    revision_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    raw_wikitext: Mapped[str] = mapped_column(Text, nullable=False)
    lead_text: Mapped[Optional[str]] = mapped_column(Text)
    license: Mapped[Optional[str]] = mapped_column(Text)
    attribution: Mapped[Optional[str]] = mapped_column(Text)
    is_huge_city: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped[Source] = relationship(back_populates="pages")
    sections: Mapped[List["PageSection"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )
    listings: Mapped[List["Listing"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class PageSection(Base):
    __tablename__ = "page_sections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    heading_level: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    subsection_title: Mapped[Optional[str]] = mapped_column(Text)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    wikitext: Mapped[Optional[str]] = mapped_column(Text)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)

    page: Mapped[Page] = relationship(back_populates="sections")
    listings: Mapped[List["Listing"]] = relationship(back_populates="section")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("page_sections.id", ondelete="SET NULL")
    )
    listing_kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text)
    alt_name: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    directions: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    url: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)
    hours: Mapped[Optional[str]] = mapped_column(Text)
    price_raw: Mapped[Optional[str]] = mapped_column(Text)
    lastedit: Mapped[Optional[str]] = mapped_column(Text)
    wikidata_id: Mapped[Optional[str]] = mapped_column(Text)
    wikipedia_title: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    page: Mapped[Page] = relationship(back_populates="listings")
    section: Mapped[Optional[PageSection]] = relationship(back_populates="listings")


class PageRelationship(Base):
    __tablename__ = "page_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_title", "to_title", "relationship_type", name="uq_rel_from_to_type"
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_page_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE")
    )
    from_title: Mapped[str] = mapped_column(Text, nullable=False)
    to_title: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)


class IngestionError(Base):
    __tablename__ = "ingestion_errors"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    wiki_page_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    page_title: Mapped[Optional[str]] = mapped_column(Text)
    operation: Mapped[Optional[str]] = mapped_column(Text)
    error_type: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[IngestionRun] = relationship(back_populates="errors")


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(database_url: str) -> None:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
