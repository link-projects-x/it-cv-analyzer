"""Local run over <data>/raw/*.html.

  python -m parser --data ../../data --limit 5              # Claude on Bedrock, needs AWS credentials
  python -m parser --data ../../data --limit 5 --llm cli    # claude -p under the logged-in Claude subscription
  python -m parser --data ../../data --limit 5 --llm cli --thinking   # about 8x the output tokens
  python -m parser --data ../../data --limit 5 --dry-run    # print the prompt and schema size, no LLM call
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .extract import extract
from .llm import BedrockClaude, ClaudeCli
from .pipeline import LocalStore, parse_raw
from .prompt import output_schema, system_prompt, user_message


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse local raw vacancies into processed/")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--ids", nargs="*", help="only these vacancy IDs, e.g. dou-377767")
    ap.add_argument("--skip-done", action="store_true", help="skip IDs that already have processed/<id>.json")
    ap.add_argument("--llm", default="bedrock", choices=["bedrock", "cli"])
    ap.add_argument("--model", help="default: anthropic.claude-haiku-5-5 (bedrock), haiku (cli)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--thinking", action="store_true", help="cli only: keep claude -p thinking (off: MAX_THINKING_TOKENS=0)")
    ap.add_argument("--workers", type=int, default=1, help="parallel vacancies; each cli worker runs its own claude -p")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    keys = sorted(f"raw/{p.name}" for p in (args.data / "raw").glob("dou-*.html"))
    if args.ids:
        keys = [k for k in keys if Path(k).stem in set(args.ids)]
    if args.skip_done:
        keys = [k for k in keys if not (args.data / "processed" / f"{Path(k).stem}.json").exists()]
    keys = keys[: args.limit]
    if not keys:
        sys.exit("no raw vacancies to parse")

    if args.dry_run:
        page = extract((args.data / keys[0]).read_text(encoding="utf-8"))
        user = user_message(page.title, page.company, page.salary_text, page.text)
        print(f"system prompt: {len(system_prompt())} chars")
        print(f"output schema: {len(json.dumps(output_schema()))} chars")
        print(f"first user message ({keys[0]}): {len(user)} chars\n")
        print(user[:1500])
        return

    store = LocalStore(args.data)
    if args.llm == "cli":
        llm = ClaudeCli(model=args.model or "haiku", thinking=args.thinking)
    else:
        llm = BedrockClaude(model=args.model or "anthropic.claude-haiku-5-5", region=args.region, effort=args.effort)
    totals = {"ok": 0, "failed": 0, "in": 0, "out": 0, "cache_read": 0}
    started = time.monotonic()
    # parse_raw writes one file per vacancy, so threads do not share output files.
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        outcomes = list(pool.map(lambda key: parse_raw(key, store, llm), keys))
    for o in outcomes:
        totals["ok" if o.ok else "failed"] += 1
        totals["in"] += o.input_tokens
        totals["out"] += o.output_tokens
        totals["cache_read"] += o.cache_read_tokens
    totals["seconds"] = round(time.monotonic() - started)
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
