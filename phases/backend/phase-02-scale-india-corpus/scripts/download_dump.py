#!/usr/bin/env python3
"""List or download enwikivoyage pages-articles dumps from dumps.wikimedia.org."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

DUMP_INDEX = "https://dumps.wikimedia.org/enwikivoyage/latest/"
DEFAULT_FILE = "enwikivoyage-latest-pages-articles.xml.bz2"
USER_AGENT = (
    "TripWiseAI/0.1 (https://github.com/sumansurvi/tripWiseAI; "
    "travel-research portfolio project)"
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Download enwikivoyage dump")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the default dump URL and exit",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/dumps") / DEFAULT_FILE,
        help="Output path (default: data/dumps/enwikivoyage-latest-pages-articles.xml.bz2)",
    )
    parser.add_argument(
        "--url",
        default=DUMP_INDEX + DEFAULT_FILE,
        help="Dump file URL",
    )
    args = parser.parse_args(argv)

    if args.list:
        print(args.url)
        print(
            "Note: --list only prints the URL. Run without --list to download "
            "(~100+ MB for pages-articles). Prefer ingest-api for day-to-day Phase 2; "
            "use ingest-dump only after a complete local file exists."
        )
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    req = Request(args.url, headers={"User-Agent": USER_AGENT})
    print(f"Downloading {args.url} → {args.out}")
    with urlopen(req, timeout=120) as resp, args.out.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    print(f"saved {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
