"""Local matcher run over <data>/profiles/<uuid>.json -> <data>/matches/ or <data>/failed-match/.

  python -m api --data ../../data                  # Bedrock embeddings, needs AWS credentials; fake salary
  python -m api --data ../../data --fake-embed     # deterministic local vectors; the index must be built the same way
                                                   # (python -m indexer --fake-embed)

The salary block is always the fake one ("fake-disabled"); the real model runs with ml/salary/inference.py.
Output never includes profile text.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .embed import BedrockEmbedder, HashEmbedder
from .matcher import PROFILE_KEY_RE, match_profile
from .salary import FakeSalary
from .store import LocalStore


def main() -> None:
    ap = argparse.ArgumentParser(description="Match local profiles against index/vacancies.jsonl")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--ids", nargs="*", help="only these profile UUIDs")
    ap.add_argument("--model", default="cohere.embed-v4:0")
    ap.add_argument("--dimension", type=int, default=1024)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--fake-embed", action="store_true", help="hash-based vectors instead of Bedrock")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    keys = sorted(f"profiles/{p.name}" for p in (args.data / "profiles").glob("*.json"))
    keys = [k for k in keys if PROFILE_KEY_RE.match(k) and (not args.ids or Path(k).stem in set(args.ids))]
    if not keys:
        sys.exit("no profiles to match (expected <data>/profiles/<uuid>.json)")

    embedder = HashEmbedder() if args.fake_embed else BedrockEmbedder(args.model, args.region, args.dimension)
    store, salary = LocalStore(args.data), FakeSalary()
    outcomes = [match_profile(key, store, embedder, salary) for key in keys]
    print(json.dumps({"ok": sum(o.ok for o in outcomes), "failed": sum(not o.ok for o in outcomes)}))


if __name__ == "__main__":
    main()
