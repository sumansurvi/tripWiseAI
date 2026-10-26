from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config").is_dir() and (parent / "docs").is_dir():
            return parent
    # phases/backend/<phase>/scripts/.../config.py → repo root
    return here.parents[5]


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
load_dotenv(CONFIG_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_SEEDS = [
    "India",
    "Delhi",
    "Mumbai",
    "Jaipur",
    "Agra",
    "Varanasi",
    "Goa",
    "Delhi/Old Delhi",
    "Delhi/South",
    "Mumbai/South",
    "Mumbai/Fort",
]


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_url: str
    user_agent: str
    scope_mode: str
    scope_root: str
    seeds: list[str] = field(default_factory=list)
    max_depth: int = 1
    follow_go_next: bool = False
    allowed_page_types: list[str] = field(default_factory=list)
    skip_page_types: list[str] = field(default_factory=list)
    max_pages: int = 0  # 0 = unlimited
    request_delay_seconds: float = 1.0
    max_retries: int = 4
    timeout_seconds: float = 45.0
    batch_size: int = 5
    log_level: str = "INFO"
    log_json: bool = True
    # None → the real project data/ dir. Tests must point this at a tmp dir.
    data_dir: Optional[Path] = None


def load_settings() -> Settings:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://tripwise:tripwise@127.0.0.1:5432/tripwise_p1",
    )
    user_agent = os.getenv(
        "WIKIVOYAGE_USER_AGENT",
        "TripWiseAI/0.1 (https://github.com/sumansurvi/tripWiseAI; travel-research portfolio project)",
    )
    scope_mode = os.getenv("TRIPWISE_SCOPE_MODE", "seeds_and_districts").strip().lower()
    scope_root = os.getenv("TRIPWISE_SCOPE_ROOT", "India").strip()
    default_seeds = DEFAULT_SEEDS
    if scope_mode == "scope_root":
        default_seeds = [scope_root]
    return Settings(
        database_url=database_url,
        api_url=os.getenv("WIKIVOYAGE_API_URL", "https://en.wikivoyage.org/w/api.php"),
        user_agent=user_agent,
        scope_mode=scope_mode,
        scope_root=scope_root,
        seeds=_csv("TRIPWISE_SEEDS", default_seeds),
        max_depth=int(os.getenv("TRIPWISE_MAX_DEPTH", "1")),
        follow_go_next=_bool("TRIPWISE_FOLLOW_GO_NEXT", False),
        allowed_page_types=[
            t.lower()
            for t in _csv(
                "TRIPWISE_ALLOWED_PAGE_TYPES",
                ["country", "region", "city", "district", "park", "unknown"],
            )
        ],
        skip_page_types=[
            t.lower()
            for t in _csv("TRIPWISE_SKIP_PAGE_TYPES", ["itinerary", "phrasebook"])
        ],
        max_pages=int(os.getenv("TRIPWISE_MAX_PAGES", "0")),
        request_delay_seconds=float(os.getenv("TRIPWISE_REQUEST_DELAY_SECONDS", "1.0")),
        max_retries=int(os.getenv("TRIPWISE_MAX_RETRIES", "4")),
        timeout_seconds=float(os.getenv("TRIPWISE_TIMEOUT_SECONDS", "45")),
        batch_size=int(os.getenv("TRIPWISE_BATCH_SIZE", "5")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_json=_bool("LOG_JSON", True),
    )
