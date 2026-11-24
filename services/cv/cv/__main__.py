"""Local run over <data>/cv/<uuid>.<pdf|docx|txt>.

  python -m cv --data ../../data --limit 5              # Claude on Bedrock, needs AWS credentials
  python -m cv --data ../../data --limit 5 --dry-run    # extract text, print sizes only, no LLM call

The local run keeps the CV files unless --delete-cv is given. Output never includes CV text.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .extract import ExtractError, extract
from .llm import BedrockClaude
from .pipeline import CV_KEY_RE, LocalStore, parse_cv
from .prompt import output_schema, system_prompt, user_message


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse local CVs into profiles/")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--ids", nargs="*", help="only these profile UUIDs")
    ap.add_argument("--skip-done", action="store_true", help="skip IDs that already have profiles/<id>.json")
    ap.add_argument("--delete-cv", action="store_true", help="delete cv/<id>.* after a successful parse")
    ap.add_argument("--model", default="anthropic.claude-haiku-5-5")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    keys = sorted(f"cv/{p.name}" for p in (args.data / "cv").glob("*") if CV_KEY_RE.match(f"cv/{p.name}"))
    if args.ids:
        keys = [k for k in keys if Path(k).stem in set(args.ids)]
    if args.skip_done:
        keys = [k for k in keys if not (args.data / "profiles" / f"{Path(k).stem}.json").exists()]
    keys = keys[: args.limit]
    if not keys:
        sys.exit("no CVs to parse (expected <data>/cv/<uuid>.<pdf|docx|txt>)")

    if args.dry_run:
        print(f"system prompt: {len(system_prompt())} chars")
        print(f"output schema: {len(json.dumps(output_schema()))} chars")
        for key in keys:
            fmt = key.rsplit(".", 1)[1]
            data = (args.data / key).read_bytes()
            try:
                cv = extract(data, fmt)
            except ExtractError as exc:
                print(f"{key}: {len(data)} bytes, ExtractError: {exc}")
                continue
            print(f"{key}: {len(data)} bytes, {cv.chars} chars, truncated={cv.truncated}, "
                  f"user message {len(user_message(cv.text))} chars")
        return

    store = LocalStore(args.data)
    llm = BedrockClaude(model=args.model, region=args.region, effort=args.effort)
    totals = {"ok": 0, "failed": 0, "in": 0, "out": 0, "cache_read": 0}
    for key in keys:
        o = parse_cv(key, store, llm, delete_source=args.delete_cv)
        totals["ok" if o.ok else "failed"] += 1
        totals["in"] += o.input_tokens
        totals["out"] += o.output_tokens
        totals["cache_read"] += o.cache_read_tokens
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
