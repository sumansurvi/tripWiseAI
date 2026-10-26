from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from tripwise.config import Settings
from tripwise.discovery import QueueItem, maybe_enqueue_children, seed_queue
from tripwise.extract import extract_page
from tripwise.logging_utils import log_event
from tripwise.models import IngestionError, IngestionRun
from tripwise.persist import content_hash_for, persist_page
from tripwise.export_json import export_page_json
from tripwise.progress import print_progress
from tripwise.source_client import (
    PermanentSourceError,
    RetrievedPage,
    TransientSourceError,
    WikivoyageClient,
)
from tripwise.validate import validate_extracted_page

logger = logging.getLogger("tripwise.ingest.pipeline")


@dataclass
class RunResult:
    run_id: str
    status: str
    pages_discovered: int
    pages_processed: int
    pages_succeeded: int
    pages_failed: int
    pages_skipped: int
    records_created: int
    records_updated: int
    records_unchanged: int
    duration_ms: int


@dataclass
class _Counters:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    processed: int = 0


def _emit_api_progress(
    settings: Settings,
    counters: _Counters,
    state,
    title: str,
) -> None:
    decided = counters.succeeded + counters.failed + counters.skipped
    print_progress(
        pages=decided,
        total=settings.max_pages if settings.max_pages else None,
        succeeded=counters.succeeded,
        failed=counters.failed,
        skipped=counters.skipped,
        queue=len(state.queued),
        title=title,
    )


def run_ingestion(session: Session, settings: Settings, client: WikivoyageClient) -> RunResult:
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    run_id = str(uuid.uuid4())
    run = IngestionRun(
        id=run_id,
        source="en.wikivoyage",
        scope={
            "mode": settings.scope_mode,
            "root": settings.scope_root,
            "seeds": settings.seeds,
            "max_depth": settings.max_depth,
            "follow_go_next": settings.follow_go_next,
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
        "ingestion_started",
        run_id=run_id,
        operation="ingest",
        status="RUNNING",
    )

    state = seed_queue(settings.seeds)
    counters = _Counters()

    try:
        while state.queued:
            if settings.max_pages and counters.succeeded >= settings.max_pages:
                log_event(
                    logger,
                    logging.INFO,
                    "max_pages_reached",
                    run_id=run_id,
                    operation="ingest",
                    status="stop",
                )
                break
            batch_items = [state.queued.popleft()]
            while state.queued and len(batch_items) < settings.batch_size:
                if settings.max_pages and counters.succeeded + len(batch_items) >= settings.max_pages:
                    break
                batch_items.append(state.queued.popleft())
            counters.processed += len(batch_items)
            retrieve_t0 = time.perf_counter()
            try:
                retrieved_pages = client.fetch_pages([item.title for item in batch_items])
            except (TransientSourceError, PermanentSourceError, Exception) as exc:
                counters.failed += len(batch_items)
                error_type = type(exc).__name__
                for item in batch_items:
                    _record_error(session, run_id, item.title, "retrieve", error_type, str(exc))
                    _emit_api_progress(settings, counters, state, item.title)
                log_event(
                    logger,
                    logging.ERROR,
                    "page_failed",
                    run_id=run_id,
                    page_title=batch_items[0].title,
                    operation="retrieve",
                    status="error",
                    error_type=error_type,
                    duration_ms=int((time.perf_counter() - retrieve_t0) * 1000),
                )
                continue

            retrieved_by_request = {page.requested_title: page for page in retrieved_pages}
            for item in batch_items:
                retrieved = retrieved_by_request.get(item.title)
                if retrieved is None:
                    retrieved = next((p for p in retrieved_pages if p.title == item.title), None)
                _ingest_one(
                    session=session,
                    settings=settings,
                    state=state,
                    run_id=run_id,
                    item=item,
                    retrieved=retrieved,
                    counters=counters,
                )

        duration_ms = int((time.perf_counter() - t0) * 1000)
        if counters.failed and counters.succeeded:
            status = "PARTIAL"
        elif counters.failed and not counters.succeeded:
            status = "FAILED"
        else:
            status = "COMPLETED"

        run.pages_discovered = len(state.discovered)
        run.pages_processed = counters.processed
        run.pages_succeeded = counters.succeeded
        run.pages_failed = counters.failed
        run.pages_skipped = counters.skipped
        run.records_created = counters.created
        run.records_updated = counters.updated
        run.records_unchanged = counters.unchanged
        run.duration_ms = duration_ms
        run.completed_at = datetime.now(timezone.utc)
        run.status = status
        session.commit()

        log_event(
            logger,
            logging.INFO,
            "ingestion_completed",
            run_id=run_id,
            operation="ingest",
            status=status,
            duration_ms=duration_ms,
        )
        return RunResult(
            run_id=run_id,
            status=status,
            pages_discovered=len(state.discovered),
            pages_processed=counters.processed,
            pages_succeeded=counters.succeeded,
            pages_failed=counters.failed,
            pages_skipped=counters.skipped,
            records_created=counters.created,
            records_updated=counters.updated,
            records_unchanged=counters.unchanged,
            duration_ms=duration_ms,
        )
    except Exception:
        run.status = "FAILED"
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = int((time.perf_counter() - t0) * 1000)
        session.commit()
        raise


def _ingest_one(
    session: Session,
    settings: Settings,
    state,
    run_id: str,
    item: QueueItem,
    retrieved: RetrievedPage | None,
    counters: _Counters,
) -> None:
    page_t0 = time.perf_counter()
    progress_title = item.title
    try:
        if retrieved is None:
            counters.skipped += 1
            log_event(
                logger,
                logging.WARNING,
                "page_skipped",
                run_id=run_id,
                page_title=item.title,
                operation="retrieve",
                status="empty",
            )
            return

        progress_title = retrieved.title
        if retrieved.missing:
            counters.skipped += 1
            _record_error(
                session,
                run_id,
                item.title,
                "retrieve",
                "missing_page",
                "Title does not exist on English Wikivoyage",
            )
            log_event(
                logger,
                logging.WARNING,
                "page_skipped",
                run_id=run_id,
                page_title=item.title,
                operation="retrieve",
                status="missing",
            )
            return

        try:
            extracted = extract_page(retrieved.title, retrieved.wikitext)
            log_event(
                logger,
                logging.INFO,
                "page_parsed",
                run_id=run_id,
                page_id=retrieved.wiki_page_id,
                page_title=retrieved.title,
                operation="parse",
                status="ok",
            )
            validation = validate_extracted_page(
                retrieved.title,
                retrieved.wiki_page_id,
                retrieved.canonical_url,
                retrieved.wikitext,
                extracted,
            )
            log_event(
                logger,
                logging.INFO,
                "page_validated",
                run_id=run_id,
                page_id=retrieved.wiki_page_id,
                page_title=retrieved.title,
                operation="validate",
                status="ok" if validation.ok else "failed",
            )
            if not validation.ok:
                counters.failed += 1
                messages = "; ".join(i.message for i in validation.issues if i.fatal)
                _record_error(session, run_id, retrieved.title, "validate", "ValidationError", messages)
                log_event(
                    logger,
                    logging.ERROR,
                    "page_failed",
                    run_id=run_id,
                    page_id=retrieved.wiki_page_id,
                    page_title=retrieved.title,
                    operation="validate",
                    status="error",
                    error_type="ValidationError",
                )
                return

            if extracted.page_type in set(settings.skip_page_types):
                counters.skipped += 1
                log_event(
                    logger,
                    logging.WARNING,
                    "page_skipped",
                    run_id=run_id,
                    page_title=retrieved.title,
                    operation="filter",
                    status="skip_page_type",
                )
                return

            if extracted.page_type not in settings.allowed_page_types:
                counters.skipped += 1
                log_event(
                    logger,
                    logging.WARNING,
                    "page_skipped",
                    run_id=run_id,
                    page_title=retrieved.title,
                    operation="filter",
                    status="page_type",
                )
                return

            digest = content_hash_for(retrieved.wikitext)
            outcome = persist_page(session, retrieved, extracted, digest)
            session.commit()
            export_page_json(retrieved, extracted, data_dir=settings.data_dir)
            if outcome == "created":
                counters.created += 1
            elif outcome == "updated":
                counters.updated += 1
            else:
                counters.unchanged += 1
            counters.succeeded += 1
            log_event(
                logger,
                logging.INFO,
                "page_persisted",
                run_id=run_id,
                page_id=retrieved.wiki_page_id,
                page_title=retrieved.title,
                operation="persist",
                status=outcome,
                duration_ms=int((time.perf_counter() - page_t0) * 1000),
            )
            log_event(
                logger,
                logging.INFO,
                "page_json_exported",
                run_id=run_id,
                page_id=retrieved.wiki_page_id,
                page_title=retrieved.title,
                operation="export_json",
                status="ok",
            )
            maybe_enqueue_children(
                state,
                extracted,
                current_depth=item.depth,
                max_depth=settings.max_depth,
                follow_go_next=settings.follow_go_next,
                scope_mode=settings.scope_mode,
                allowed_page_types=settings.allowed_page_types,
            )
        except Exception as exc:  # noqa: BLE001 — isolate page failures
            session.rollback()
            counters.failed += 1
            _record_error(session, run_id, retrieved.title, "extract_persist", type(exc).__name__, str(exc))
            log_event(
                logger,
                logging.ERROR,
                "page_failed",
                run_id=run_id,
                page_title=retrieved.title,
                operation="extract_persist",
                status="error",
                error_type=type(exc).__name__,
                duration_ms=int((time.perf_counter() - page_t0) * 1000),
            )
    finally:
        _emit_api_progress(settings, counters, state, progress_title)


def _record_error(
    session: Session,
    run_id: str,
    title: str,
    operation: str,
    error_type: str,
    message: str,
) -> None:
    session.add(
        IngestionError(
            id=str(uuid.uuid4()),
            run_id=run_id,
            page_title=title,
            operation=operation,
            error_type=error_type,
            error_message=message[:2000],
            created_at=datetime.now(timezone.utc),
        )
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
