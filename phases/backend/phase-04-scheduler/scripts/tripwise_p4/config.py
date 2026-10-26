"""Phase 4 settings from config/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config").is_dir() and (parent / "docs").is_dir():
            return parent
    return here.parents[5]


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"

load_dotenv(CONFIG_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_CRON = "0 3 * * *"


@dataclass(frozen=True)
class Settings:
    database_url: str
    scheduler_cron: str
    scheduler_max_pages: Optional[int]
    log_level: str
    project_root: Path


def load_settings() -> Settings:
    raw_max = os.getenv("TRIPWISE_SCHEDULER_MAX_PAGES", "").strip()
    max_pages: Optional[int]
    if raw_max:
        max_pages = int(raw_max)
    else:
        max_pages = None
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://tripwise:tripwise@127.0.0.1:5432/tripwise_p1",
        ),
        scheduler_cron=os.getenv("TRIPWISE_SCHEDULER_CRON", DEFAULT_CRON).strip()
        or DEFAULT_CRON,
        scheduler_max_pages=max_pages,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        project_root=PROJECT_ROOT,
    )
