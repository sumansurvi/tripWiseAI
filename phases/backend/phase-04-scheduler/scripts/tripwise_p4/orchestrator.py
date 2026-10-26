"""Orchestrate Phase 2 ingest-api → Phase 3 embed under an overlap lock."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from sqlalchemy.orm import Session, sessionmaker

from tripwise_p4.config import Settings
from tripwise_p4.lock import (
    finish_scheduler_run,
    has_running_ingestion,
    start_scheduler_run,
)

logger = logging.getLogger("tripwise.phase4.orchestrator")

RunCmd = Callable[[Sequence[str], Path], int]


@dataclass
class TickResult:
    status: str  # SKIPPED | COMPLETED | FAILED
    run_id: Optional[str]
    stages: List[str]
    message: str
    exit_code: int


def _default_run_cmd(argv: Sequence[str], cwd: Path) -> int:
    logger.info("stage_cmd %s", " ".join(argv))
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd),
        check=False,
    )
    return int(completed.returncode)


def build_stage_commands(
    settings: Settings,
    *,
    python_exe: str = sys.executable,
) -> List[List[str]]:
    root = settings.project_root
    p2 = (
        root
        / "phases"
        / "backend"
        / "phase-02-scale-india-corpus"
        / "scripts"
        / "run_phase2.py"
    )
    p3 = (
        root
        / "phases"
        / "backend"
        / "phase-03-embeddings-vector-store"
        / "scripts"
        / "run_phase3.py"
    )
    ingest = [python_exe, str(p2), "ingest-api"]
    if settings.scheduler_max_pages is not None:
        ingest.extend(["--max-pages", str(settings.scheduler_max_pages)])
    embed = [python_exe, str(p3), "embed"]
    return [ingest, embed]


def run_tick(
    session: Session,
    settings: Settings,
    *,
    run_cmd: Optional[RunCmd] = None,
) -> TickResult:
    """One scheduler tick: lock → P2 ingest-api → P3 embed."""
    cmd_runner = run_cmd or _default_run_cmd
    overlapping = has_running_ingestion(session)
    if overlapping is not None:
        msg = (
            f"Overlap lock: ingestion_run {overlapping.id} still RUNNING; "
            "skipping this tick"
        )
        logger.warning(msg)
        return TickResult(
            status="SKIPPED",
            run_id=None,
            stages=[],
            message=msg,
            exit_code=0,
        )

    stages = build_stage_commands(settings)
    stage_names = ["ingest-api", "embed"]
    scope = {
        "phases": ["phase-02-ingest-api", "phase-03-embed"],
        "max_pages": settings.scheduler_max_pages,
        "cron": settings.scheduler_cron,
    }
    run = start_scheduler_run(session, scope=scope)
    t0 = time.perf_counter()
    completed_stages: List[str] = []

    try:
        for name, argv in zip(stage_names, stages):
            code = cmd_runner(argv, settings.project_root)
            if code != 0:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                finish_scheduler_run(
                    session, run, status="FAILED", duration_ms=duration_ms
                )
                msg = f"Stage {name} failed with exit code {code}"
                logger.error(msg)
                return TickResult(
                    status="FAILED",
                    run_id=run.id,
                    stages=completed_stages,
                    message=msg,
                    exit_code=code if code else 1,
                )
            completed_stages.append(name)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        finish_scheduler_run(
            session, run, status="COMPLETED", duration_ms=duration_ms
        )
        msg = "Scheduler tick completed: ingest-api → embed"
        logger.info(msg)
        return TickResult(
            status="COMPLETED",
            run_id=run.id,
            stages=completed_stages,
            message=msg,
            exit_code=0,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - t0) * 1000)
        finish_scheduler_run(session, run, status="FAILED", duration_ms=duration_ms)
        msg = f"Scheduler tick crashed: {exc}"
        logger.exception(msg)
        return TickResult(
            status="FAILED",
            run_id=run.id,
            stages=completed_stages,
            message=msg,
            exit_code=1,
        )


def run_tick_with_factory(
    factory: sessionmaker,
    settings: Settings,
    *,
    run_cmd: Optional[RunCmd] = None,
) -> TickResult:
    with factory() as session:
        return run_tick(session, settings, run_cmd=run_cmd)
