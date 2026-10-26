"""Phase 4 orchestrator unit tests (no live Wikimedia / Gemini)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

PHASE4_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PHASE1_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "phase-01-source-knowledge-foundation"
    / "scripts"
)
sys.path.insert(0, str(PHASE4_SCRIPTS))
sys.path.insert(0, str(PHASE1_SCRIPTS))

from tripwise_p4.config import Settings
from tripwise_p4.lock import has_running_ingestion
from tripwise_p4.orchestrator import build_stage_commands, run_tick


def _settings() -> Settings:
    root = Path(__file__).resolve().parents[4]  # repo root
    return Settings(
        database_url="postgresql://unused",
        scheduler_cron="0 3 * * *",
        scheduler_max_pages=5,
        log_level="WARNING",
        project_root=root,
    )


def test_build_stage_commands_includes_max_pages():
    settings = _settings()
    stages = build_stage_commands(settings, python_exe="python")
    assert len(stages) == 2
    assert stages[0][-2:] == ["--max-pages", "5"]
    assert stages[1][-1] == "embed"


def test_skip_when_running_ingestion():
    session = MagicMock()
    overlapping = MagicMock()
    overlapping.id = "run-busy"
    # has_running_ingestion uses session.scalar
    session.scalar.return_value = overlapping

    calls: list = []

    def run_cmd(argv, cwd):
        calls.append(argv)
        return 0

    result = run_tick(session, _settings(), run_cmd=run_cmd)
    assert result.status == "SKIPPED"
    assert result.exit_code == 0
    assert calls == []
    session.add.assert_not_called()


def test_ordered_stages_and_complete(monkeypatch):
    from tripwise_p4 import orchestrator as orch

    session = MagicMock()
    session.scalar.return_value = None  # no overlap

    fake_run = MagicMock()
    fake_run.id = "sched-1"

    monkeypatch.setattr(
        orch,
        "start_scheduler_run",
        lambda session, scope: fake_run,
    )
    finished = []

    def finish(session, run, *, status, duration_ms):
        finished.append(status)

    monkeypatch.setattr(orch, "finish_scheduler_run", finish)

    seen: list[str] = []

    def run_cmd(argv, cwd):
        seen.append(argv[-1] if argv[-1] != "5" else argv[-3])
        # last token: ingest-api or embed
        return 0

    # Better: track by presence of ingest-api / embed
    seen.clear()

    def run_cmd2(argv, cwd):
        joined = " ".join(argv)
        if "ingest-api" in joined:
            seen.append("ingest-api")
        elif "embed" in joined:
            seen.append("embed")
        return 0

    result = run_tick(session, _settings(), run_cmd=run_cmd2)
    assert result.status == "COMPLETED"
    assert seen == ["ingest-api", "embed"]
    assert finished == ["COMPLETED"]
    assert result.exit_code == 0


def test_fail_aborts_before_embed(monkeypatch):
    from tripwise_p4 import orchestrator as orch

    session = MagicMock()
    session.scalar.return_value = None
    fake_run = MagicMock()
    fake_run.id = "sched-fail"
    monkeypatch.setattr(
        orch, "start_scheduler_run", lambda session, scope: fake_run
    )
    finished = []
    monkeypatch.setattr(
        orch,
        "finish_scheduler_run",
        lambda session, run, *, status, duration_ms: finished.append(status),
    )

    seen: list[str] = []

    def run_cmd(argv, cwd):
        joined = " ".join(argv)
        if "ingest-api" in joined:
            seen.append("ingest-api")
            return 2
        seen.append("embed")
        return 0

    result = run_tick(session, _settings(), run_cmd=run_cmd)
    assert result.status == "FAILED"
    assert seen == ["ingest-api"]
    assert "embed" not in seen
    assert finished == ["FAILED"]
    assert result.exit_code == 2


def test_has_running_ingestion_query():
    session = MagicMock()
    session.scalar.return_value = None
    assert has_running_ingestion(session) is None
    session.scalar.assert_called_once()
