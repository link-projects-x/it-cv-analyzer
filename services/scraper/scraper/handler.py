"""Lambda entry point. Triggered daily by EventBridge Scheduler.

Environment:
  BUCKET        S3 bucket for raw/ objects (required)
  CATEGORY      DOU category, default "AI/ML"
  MAX_NEW       max vacancies to download per run, default 300
  DELAY_SECONDS pause between requests to DOU, default 1.0
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict

from .dou import DouClient
from .run import scrape
from .stores import S3RawStore

logging.getLogger().setLevel(logging.INFO)


def lambda_handler(event, context):
    result = scrape(
        client=DouClient(delay_seconds=float(os.environ.get("DELAY_SECONDS", "1.0"))),
        store=S3RawStore(bucket=os.environ["BUCKET"]),
        category=os.environ.get("CATEGORY", "AI/ML"),
        max_new=int(os.environ.get("MAX_NEW", "300")),
        time_left_seconds=lambda: context.get_remaining_time_in_millis() / 1000,
    )
    out = asdict(result)
    out["stored_count"] = len(result.stored)
    return out
