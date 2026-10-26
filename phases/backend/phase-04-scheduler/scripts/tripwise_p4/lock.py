"""Overlap lock + ingestion_run bookkeeping for scheduler ticks."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from tripwise.models import IngestionRun

logger = logging.getLogger("tripwise.phase4.lock")


def has_running_ingestion(session: Session) -> Optional[IngestionRun]:
    """Return the first RUNNING ingestion with no completed_at, else None."""
    return session.scalar(
        select(IngestionRun)
        .where(
            IngestionRun.status == "RUNNING",
            IngestionRun.completed_at.is_(None),
        )
        .limit(1)
    )


def start_scheduler_run(
    session: Session,
    *,
    scope: dict[str, Any],
) -> IngestionRun:
    run = IngestionRun(
        id=str(uuid.uuid4()),
        source="scheduler",
        scope=scope,
        started_at=datetime.now(timezone.utc),
        status="RUNNING",
    )
    session.add(run)
    session.commit()
    return run


def finish_scheduler_run(
    session: Session,
    run: IngestionRun,
    *,
    status: str,
    duration_ms: int,
) -> None:
    run.status = status
    run.completed_at = datetime.now(timezone.utc)
    run.duration_ms = duration_ms
    session.commit()
