"""Lambda entry point. Triggered daily by EventBridge, after the scrape.

Environment:
  BUCKET               S3 bucket (required)
  EMBEDDING_MODEL_ID   Bedrock embedding model ID, default cohere.embed-v4:0 (assumption: check it in the console)
  EMBEDDING_DIMENSION  output_dimension for the embedding call, default 1024
  AWS_REGION           set by Lambda
"""

from __future__ import annotations

import logging
import os

from .embed import BedrockEmbedder
from .index import S3Store, build_index

logging.getLogger().setLevel(logging.INFO)


def lambda_handler(event, context):
    embedder = BedrockEmbedder(
        model_id=os.environ.get("EMBEDDING_MODEL_ID", "cohere.embed-v4:0"),
        region=os.environ["AWS_REGION"],
        dimension=int(os.environ.get("EMBEDDING_DIMENSION", "1024")),
    )
    result = build_index(S3Store(bucket=os.environ["BUCKET"]), embedder)
    return {
        "total": result.total,
        "embedded": len(result.embedded),
        "reused": result.reused,
        "invalid": len(result.invalid),
        "removed": result.removed,
    }
