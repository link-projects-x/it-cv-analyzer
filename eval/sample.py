"""Pick vacancies for hand labelling and write empty label templates.

  python eval/sample.py --data data --n 25

Writes:
  eval/labels/dou-<id>.json   template to fill by hand (kept out of git: it quotes vacancy texts)
  data/eval_texts/dou-<id>.txt vacancy text to read while labelling (not committed: DOU content)

Existing label files are never overwritten. The sample is deterministic for a given --seed and set of raw files.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "parser"))

from parser.extract import extract  # noqa: E402

TEMPLATE = {
    "seniority": "unknown",
    "role_type": "other",
    "requirements": [],
    "experience": {"min_years": None, "max_years": None},
    "english": {"min_level": None, "evidence": None},
    "salary": None,
    "domains": [],
    "unmapped": [],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=20261031)
    args = ap.parse_args()

    raw = sorted((args.data / "raw").glob("dou-*.html"))
    if len(raw) < args.n:
        sys.exit(f"only {len(raw)} raw vacancies in {args.data / 'raw'}, need {args.n}")
    picked = random.Random(args.seed).sample(raw, args.n)

    labels_dir = ROOT / "eval" / "labels"
    texts_dir = args.data / "eval_texts"
    labels_dir.mkdir(parents=True, exist_ok=True)
    texts_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for path in sorted(picked):
        vid = path.stem
        page = extract(path.read_text(encoding="utf-8"))
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        salary = f"Salary line: {page.salary_text}\n" if page.salary_text else ""
        (texts_dir / f"{vid}.txt").write_text(
            f"{meta['url']}\nTitle: {page.title}\nCompany: {page.company}\n{salary}\n{page.text}\n", encoding="utf-8"
        )
        label_path = labels_dir / f"{vid}.json"
        if not label_path.exists():
            label_path.write_text(json.dumps({"_title": page.title, **TEMPLATE}, ensure_ascii=False, indent=2), encoding="utf-8")
            created += 1

    print(f"{args.n} sampled, {created} new label templates in {labels_dir}, texts in {texts_dir}")


if __name__ == "__main__":
    main()
