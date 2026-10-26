"""Ingest India-scoped pages from an enwikivoyage pages-articles dump."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set
from urllib.parse import quote

from sqlalchemy.orm import Session

from tripwise.config import Settings
from tripwise.export_json import export_page_json
from tripwise.extract import extract_page
from tripwise.logging_utils import log_event
from tripwise.models import IngestionError, IngestionRun
from tripwise.persist import content_hash_for, persist_page
from tripwise.progress import print_progress
from tripwise.source_client import RetrievedPage
from tripwise.validate import validate_extracted_page

from tripwise_p2.ancestry import extract_is_part_of, is_under_scope, normalize_title
from tripwise_p2.dump_reader import DumpPage, iter_dump_pages

logger = logging.getLogger("tripwise.phase2.dump")


@dataclass
class DumpIngestResult:
    run_id: str
    status: str
    pages_scanned: int
    pages_in_scope: int
    pages_succeeded: int
    pages_failed: int
    pages_skipped: int
    records_created: int
    records_updated: int
    records_unchanged: int
    duration_ms: int


def _canonical_url(title: str) -> str:
    return "https://en.wikivoyage.org/wiki/" + quote(title.replace(" ", "_"), safe=":/()")


def build_parent_map(dump_path: Path, *, max_scan: int = 0) -> Dict[str, Optional[str]]:
    parents: Dict[str, Optional[str]] = {}
    scanned = 0
    for page in iter_dump_pages(dump_path):
        scanned += 1
        title = normalize_title(page.title)
        if page.redirect_target:
            parents[title] = normalize_title(page.redirect_target)
        else:
            parents[title] = extract_is_part_of(page.wikitext)
        if max_scan and scanned >= max_scan:
            break
    return parents


def titles_under_scope(
    parent_by_title: Dict[str, Optional[str]], scope_root: str
) -> Set[str]:
    root = normalize_title(scope_root)
    in_scope: Set[str] = {root}
    for title in parent_by_title:
        if is_under_scope(title, parent_by_title, root):
            in_scope.add(normalize_title(title))
    return in_scope


def run_dump_ingestion(
    session: Session,
    settings: Settings,
    dump_path: Path,
    *,
    max_scan: int = 0,
) -> DumpIngestResult:
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    run_id = str(uuid.uuid4())
    run = IngestionRun(
        id=run_id,
        source="en.wikivoyage.dump",
        scope={
            "mode": "dump",
            "root": settings.scope_root,
            "dump_path": str(dump_path),
            "allowed_page_types": settings.allowed_page_types,
            "skip_page_types": settings.skip_page_types,
            "max_pages": settings.max_pages,
        },
        started_at=started,
        status="RUNNING",
    )
    session.add(run)
    session.commit()

    log_event(
        logger,
        logging.INFO,
        "dump_pass1_started",
        run_id=run_id,
        operation="dump_index",
        status="RUNNING",
    )
    parent_map = build_parent_map(dump_path, max_scan=max_scan)
    in_scope = titles_under_scope(parent_map, settings.scope_root)
    log_event(
        logger,
        logging.INFO,
        "dump_pass1_completed",
        run_id=run_id,
        operation="dump_index",
        status="ok",
    )

    scanned = 0
    succeeded = 0
    failed = 0
    skipped = 0
    created = 0
    updated = 0
    unchanged = 0
    allowed = set(t.lower() for t in settings.allowed_page_types)
    skip_types = set(t.lower() for t in settings.skip_page_types)
    persist_total = settings.max_pages if settings.max_pages else len(in_scope)

    for page in iter_dump_pages(dump_path):
        scanned += 1
        if max_scan and scanned > max_scan:
            break

        title = normalize_title(page.title)
        if title not in in_scope:
            continue
        if page.redirect_target:
            skipped += 1
            print_progress(
                pages=succeeded + failed + skipped,
                total=persist_total,
                succeeded=succeeded,
                failed=failed,
                skipped=skipped,
                title=title,
            )
            continue
        if settings.max_pages and succeeded >= settings.max_pages:
            break

        try:
            outcome = _persist_one(
                session,
                settings,
                page,
                allowed=allowed,
                skip_types=skip_types,
            )
            if outcome == "skipped":
                skipped += 1
            elif outcome == "created":
                created += 1
                succeeded += 1
            elif outcome == "updated":
                updated += 1
                succeeded += 1
            elif outcome == "unchanged":
                unchanged += 1
                succeeded += 1
            else:
                failed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            session.rollback()
            session.add(
                IngestionError(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    wiki_page_id=page.wiki_page_id,
                    page_title=title,
                    operation="dump_persist",
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:2000],
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        print_progress(
            pages=succeeded + failed + skipped,
            total=persist_total,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            title=title,
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    if failed and succeeded:
        status = "PARTIAL"
    elif failed and not succeeded:
        status = "FAILED"
    else:
        status = "COMPLETED"

    run.status = status
    run.pages_discovered = len(in_scope)
    run.pages_processed = scanned
    run.pages_succeeded = succeeded
    run.pages_failed = failed
    run.pages_skipped = skipped
    run.records_created = created
    run.records_updated = updated
    run.records_unchanged = unchanged
    run.duration_ms = duration_ms
    run.completed_at = datetime.now(timezone.utc)
    session.commit()

    log_event(
        logger,
        logging.INFO,
        "dump_ingest_completed",
        run_id=run_id,
        operation="dump_ingest",
        status=status,
        duration_ms=duration_ms,
    )
    return DumpIngestResult(
        run_id=run_id,
        status=status,
        pages_scanned=scanned,
        pages_in_scope=len(in_scope),
        pages_succeeded=succeeded,
        pages_failed=failed,
        pages_skipped=skipped,
        records_created=created,
        records_updated=updated,
        records_unchanged=unchanged,
        duration_ms=duration_ms,
    )


def _persist_one(
    session: Session,
    settings: Settings,
    page: DumpPage,
    *,
    allowed: Set[str],
    skip_types: Set[str],
) -> str:
    title = normalize_title(page.title)
    retrieved = RetrievedPage(
        requested_title=title,
        title=title,
        wiki_page_id=page.wiki_page_id,
        canonical_url=_canonical_url(title),
        revision_id=page.revision_id,
        revision_timestamp=None,
        sha1=None,
        wikitext=page.wikitext,
    )
    extracted = extract_page(title, page.wikitext)
    if extracted.page_type in skip_types:
        return "skipped"
    if extracted.page_type not in allowed and extracted.page_type != "unknown":
        return "skipped"

    validation = validate_extracted_page(
        title,
        page.wiki_page_id,
        retrieved.canonical_url,
        page.wikitext,
        extracted,
    )
    if not validation.ok:
        return "failed"

    digest = content_hash_for(page.wikitext)
    outcome = persist_page(session, retrieved, extracted, digest)
    session.commit()
    export_page_json(retrieved, extracted)
    return outcome
