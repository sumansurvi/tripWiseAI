#!/usr/bin/env python3
"""Phase 4 entrypoint: tick | serve."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PHASE4_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = (
    REPO_ROOT / "phases" / "backend" / "phase-01-source-knowledge-foundation" / "scripts"
)

sys.path.insert(0, str(PHASE4_ROOT / "scripts"))
sys.path.insert(0, str(PHASE1_SCRIPTS))

from tripwise.models import make_session_factory  # noqa: E402
from tripwise_p4.config import load_settings  # noqa: E402
from tripwise_p4.orchestrator import run_tick_with_factory  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TripWise Phase 4 — scheduler (P2 ingest → P3 embed)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tick", help="One-shot refresh under overlap lock")
    sub.add_parser(
        "serve",
        help="Run APScheduler loop (default daily 03:00 via TRIPWISE_SCHEDULER_CRON)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    engine, factory = make_session_factory(settings.database_url)
    try:
        if args.command == "tick":
            result = run_tick_with_factory(factory, settings)
            print(json.dumps(result.__dict__, indent=2))
            return result.exit_code

        if args.command == "serve":
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger

            scheduler = BlockingScheduler()

            def _job() -> None:
                result = run_tick_with_factory(factory, settings)
                logging.getLogger("tripwise.phase4").info(
                    "tick_result status=%s exit=%s msg=%s",
                    result.status,
                    result.exit_code,
                    result.message,
                )

            # Cron: minute hour day month day_of_week
            parts = settings.scheduler_cron.split()
            if len(parts) != 5:
                print(
                    f"Invalid TRIPWISE_SCHEDULER_CRON={settings.scheduler_cron!r}; "
                    "expected 5 fields",
                    file=sys.stderr,
                )
                return 1
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
            scheduler.add_job(_job, trigger, id="tripwise_refresh")
            print(
                f"scheduler listening cron={settings.scheduler_cron!r} "
                "(Ctrl+C to stop)"
            )
            try:
                scheduler.start()
            except (KeyboardInterrupt, SystemExit):
                return 0
            return 0
    finally:
        engine.dispose()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
