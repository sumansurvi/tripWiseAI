"""SQLAlchemy models for rag_documents / rag_chunks (pgvector)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from tripwise_p3.config import DEFAULT_EMBEDDING_DIM


class Base(DeclarativeBase):
    pass


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # chunk_id
    title: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[Optional[str]] = mapped_column(Text)
    heading_path: Mapped[Optional[str]] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    wiki_page_id: Mapped[Optional[int]] = mapped_column(Integer)
    revision_id: Mapped[Optional[int]] = mapped_column(Integer)
    license: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    chunks: Mapped[List["RagChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # same as chunk_id (1:1)
    document_id: Mapped[str] = mapped_column(
        Text, ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[Optional[str]] = mapped_column(Text)
    heading_path: Mapped[Optional[str]] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    wiki_page_id: Mapped[Optional[int]] = mapped_column(Integer)
    revision_id: Mapped[Optional[int]] = mapped_column(Integer)
    license: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    embedding = mapped_column(Vector(DEFAULT_EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    document: Mapped["RagDocument"] = relationship(back_populates="chunks")


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def init_db(database_url: str, embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> None:
    """Enable pgvector and create rag_* tables.

    ``embedding_dim`` must match the Vector() column used at model definition time
    (default 768). Changing dim requires a migration / table rebuild.
    """
    if embedding_dim != DEFAULT_EMBEDDING_DIM:
        raise ValueError(
            f"GEMINI_EMBEDDING_DIM={embedding_dim} but models use Vector({DEFAULT_EMBEDDING_DIM}). "
            "Update DEFAULT_EMBEDDING_DIM in tripwise_p3.config / models if you change the model."
        )
    engine = make_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:  # noqa: BLE001 — surface actionable Postgres setup help
        msg = str(exc)
        engine.dispose()
        if "vector.control" in msg or "UndefinedFile" in msg:
            raise RuntimeError(
                "pgvector is not installed for this Postgres server.\n"
                "Homebrew's `brew install pgvector` only targets Postgres 17/18.\n"
                "For postgresql@14, build from source:\n"
                "  git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector\n"
                "  cd /tmp/pgvector && make PG_CONFIG=/opt/homebrew/opt/postgresql@14/bin/pg_config\n"
                "  make PG_CONFIG=/opt/homebrew/opt/postgresql@14/bin/pg_config install\n"
                "Then as a superuser:  psql -d tripwise_p1 -c 'CREATE EXTENSION vector;'\n"
                "See the Phase 3 section of README.md"
            ) from exc
        if "InsufficientPrivilege" in msg or "permission denied" in msg.lower():
            raise RuntimeError(
                "User lacks permission to CREATE EXTENSION vector.\n"
                "Run once as a Postgres superuser, then retry init-db:\n"
                "  psql -d tripwise_p1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
            ) from exc
        raise
    Base.metadata.create_all(engine)
    engine.dispose()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
