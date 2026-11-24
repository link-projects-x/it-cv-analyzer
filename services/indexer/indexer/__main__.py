"""Local run over <data>/processed/*.json -> <data>/index/vacancies.jsonl.

  python -m indexer --data ../../data                 # Bedrock embeddings, needs AWS credentials
  python -m indexer --data ../../data --fake-embed    # deterministic local vectors, no AWS call
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .embed import BedrockEmbedder, HashEmbedder
from .index import LocalStore, build_index


def main() -> None:
    ap = argparse.ArgumentParser(description="Build index/vacancies.jsonl from processed/")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--model", default="cohere.embed-v4:0")
    ap.add_argument("--dimension", type=int, default=1024)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--fake-embed", action="store_true", help="hash-based vectors instead of Bedrock")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    embedder = HashEmbedder() if args.fake_embed else BedrockEmbedder(args.model, args.region, args.dimension)
    result = build_index(LocalStore(args.data), embedder)
    print(json.dumps({"total": result.total, "embedded": len(result.embedded), "reused": result.reused,
                      "invalid": len(result.invalid), "removed": result.removed}))


if __name__ == "__main__":
    main()
