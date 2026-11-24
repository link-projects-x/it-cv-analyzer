"""Lambda entry points. One zip (dist/api.zip), two functions:

  api.handler.match_handler   S3 ObjectCreated on profiles/*.json -> matches/ or failed-match/
  api.handler.http_handler    Lambda function URL: POST /uploads, GET /jobs/{id}

Environment:
  BUCKET               S3 bucket (required, both)
  AWS_REGION           set by Lambda
  EMBEDDING_MODEL_ID   matcher: Bedrock embedding model ID, default cohere.embed-v4:0; must equal the indexer's
  EMBEDDING_DIMENSION  matcher: output_dimension, default 1024; must equal the indexer's
  SALARY_ENDPOINT      matcher: SageMaker endpoint name; empty -> deterministic fake salary ("fake-disabled")
  ACCESS_CODES         api: "label:sha256hex,..."; empty -> every request is refused (access.py)
  DAILY_UPLOADS_PER_CODE, DAILY_UPLOADS_TOTAL   api: daily upload limits, defaults 10 and 40
"""

from __future__ import annotations

import logging
import os
import urllib.parse

from . import http
from .access import AccessPolicy
from .embed import BedrockEmbedder
from .matcher import match_profile
from .salary import FakeSalary, SageMakerSalary
from .store import S3Store

logging.getLogger().setLevel(logging.INFO)

_embedder = None  # reused across warm invocations
_salary = None
_access = None


def _get_embedder() -> BedrockEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = BedrockEmbedder(
            model_id=os.environ.get("EMBEDDING_MODEL_ID", "cohere.embed-v4:0"),
            region=os.environ["AWS_REGION"],
            dimension=int(os.environ.get("EMBEDDING_DIMENSION", "1024")),
        )
    return _embedder


def _get_salary():
    global _salary
    if _salary is None:
        endpoint = os.environ.get("SALARY_ENDPOINT", "").strip()
        _salary = SageMakerSalary(endpoint, os.environ["AWS_REGION"]) if endpoint else FakeSalary()
    return _salary


def match_handler(event, context):
    store = S3Store(bucket=os.environ["BUCKET"])
    outcomes = []
    for record in event.get("Records", []):
        # S3 event keys are URL-encoded
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        outcomes.append(match_profile(key, store, _get_embedder(), _get_salary()))
    return {"ok": sum(o.ok for o in outcomes), "failed": sum(not o.ok for o in outcomes)}


def _get_access() -> AccessPolicy:
    global _access
    if _access is None:
        _access = AccessPolicy.from_env(os.environ)
    return _access


def http_handler(event, context):
    return http.route(event, S3Store(bucket=os.environ["BUCKET"], region=os.environ.get("AWS_REGION")), _get_access())
