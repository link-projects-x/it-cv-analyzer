"""Local run: python -m scraper --out ../../data --limit 5"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .dou import DouClient
from .run import scrape
from .stores import LocalRawStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Download DOU vacancies into <out>/raw/")
    parser.add_argument("--out", type=Path, required=True, help="data directory, e.g. ../../data")
    parser.add_argument("--category", default="AI/ML")
    parser.add_argument("--limit", type=int, default=5, help="max new vacancies to download")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = scrape(
        client=DouClient(delay_seconds=args.delay),
        store=LocalRawStore(args.out),
        category=args.category,
        max_new=args.limit,
    )
    print(f"listed={result.listed} skipped={result.skipped_existing} stored={len(result.stored)} failed={len(result.failed)}")


if __name__ == "__main__":
    main()
