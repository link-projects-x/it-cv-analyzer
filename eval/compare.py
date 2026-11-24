"""Compare LLM-parsed vacancies (data/processed) with hand labels (eval/labels).

  python eval/compare.py --data data

Only labels with "_done": true are scored, so half-filled templates do not skew the numbers.

Metrics
  skills        micro precision / recall / F1 over the set of skill IDs per vacancy (union of any_of)
  required      share of skills found by both where the `required` flag agrees
  min_level     share of skills found by both where min_level agrees exactly
  min_years, english, seniority, role_type   exact match share
  salary        exact match of (from, to, currency, period), or both null
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def skill_map(doc: dict) -> dict[str, tuple[bool, int]]:
    """skill ID -> (required, min_level). A skill in several items keeps the strictest values."""
    out: dict[str, tuple[bool, int]] = {}
    for req in doc["requirements"]:
        for sid in req["any_of"]:
            prev = out.get(sid, (False, 0))
            out[sid] = (prev[0] or req["required"], max(prev[1], req["min_level"]))
    return out


def salary_key(s):
    return None if s is None else (s["from"], s["to"], s["currency"], s["period"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--labels", type=Path, default=ROOT / "eval" / "labels")
    ap.add_argument("--show", type=int, default=5, help="print skill diffs for the N worst vacancies")
    args = ap.parse_args()

    tp = fp = fn = 0
    req_agree = level_agree = both = 0
    exact = {"min_years": 0, "english": 0, "seniority": 0, "role_type": 0, "salary": 0}
    scored, missing, diffs = 0, [], []

    for label_path in sorted(args.labels.glob("dou-*.json")):
        gold = json.loads(label_path.read_text(encoding="utf-8"))
        if not gold.get("_done"):
            continue
        pred_path = args.data / "processed" / label_path.name
        if not pred_path.exists():
            missing.append(label_path.stem)
            continue
        pred = json.loads(pred_path.read_text(encoding="utf-8"))
        scored += 1

        g, p = skill_map(gold), skill_map(pred)
        common = g.keys() & p.keys()
        tp += len(common)
        fp += len(p.keys() - g.keys())
        fn += len(g.keys() - p.keys())
        both += len(common)
        req_agree += sum(g[s][0] == p[s][0] for s in common)
        level_agree += sum(g[s][1] == p[s][1] for s in common)
        diffs.append((len(p.keys() ^ g.keys()), label_path.stem, sorted(p.keys() - g.keys()), sorted(g.keys() - p.keys())))

        exact["min_years"] += gold["experience"]["min_years"] == pred["experience"]["min_years"]
        exact["english"] += gold["english"]["min_level"] == pred["english"]["min_level"]
        exact["seniority"] += gold["seniority"] == pred["seniority"]
        exact["role_type"] += gold["role_type"] == pred["role_type"]
        exact["salary"] += salary_key(gold["salary"]) == salary_key(pred["salary"])

    if not scored:
        raise SystemExit("no labels with \"_done\": true that have a processed/ counterpart")

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    print(f"vacancies scored: {scored}" + (f"  (no processed/ for: {', '.join(missing)})" if missing else ""))
    print(f"skills     precision {precision:.2f}  recall {recall:.2f}  F1 {f1:.2f}  (tp {tp}, fp {fp}, fn {fn})")
    if both:
        print(f"required   {req_agree / both:.2f}   min_level {level_agree / both:.2f}   (over {both} shared skills)")
    for k, v in exact.items():
        print(f"{k:<10} {v / scored:.2f}")

    print("\nlargest skill differences (extra = LLM only, missed = label only):")
    for n, vid, extra, missed in sorted(diffs, reverse=True)[: args.show]:
        print(f"  {vid}: extra {extra}  missed {missed}")


if __name__ == "__main__":
    main()
