"""Lambda entry point. Triggered by S3 ObjectCreated on raw/*.html.

Environment:
  BUCKET      S3 bucket (required)
  MODEL_ID    Bedrock model ID, default anthropic.claude-haiku-5-5
  AWS_REGION  set by Lambda; the Bedrock Mantle endpoint is built from it
  EFFORT      output_config.effort, default "low"
"""

from __future__ import annotations

import logging
import os
import urllib.parse

from .llm import BedrockClaude
from .pipeline import S3Store, parse_raw

logging.getLogger().setLevel(logging.INFO)

_llm = None  # reused across warm invocations


def _get_llm() -> BedrockClaude:
    global _llm
    if _llm is None:
        _llm = BedrockClaude(
            model=os.environ.get("MODEL_ID", "anthropic.claude-haiku-5-5"),
            region=os.environ["AWS_REGION"],
            effort=os.environ.get("EFFORT", "low"),
        )
    return _llm


def lambda_handler(event, context):
    store = S3Store(bucket=os.environ["BUCKET"])
    outcomes = []
    for record in event.get("Records", []):
        # S3 event keys are URL-encoded
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        outcomes.append(parse_raw(key, store, _get_llm()))
    return {"ok": sum(o.ok for o in outcomes), "failed": sum(not o.ok for o in outcomes)}
