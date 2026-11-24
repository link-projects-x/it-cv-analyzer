"""5-fold CV report: median baseline vs the model, all rows and DS / AI / ML rows, p25-p75 coverage.

    python ml/salary/evaluate.py [--data data/salary]

Split: KFold(5, shuffle=True, random_state=0) over the filtered survey rows. Models are trained on all
categories in each fold; the DS / AI / ML column scores only the test rows of that category.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train as T  # noqa: E402

DS_CATEGORY = "DS / AI / ML / Data Engineering"


def mdae(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.median(np.abs(y - pred)))


def report(X, y, oof) -> str:
    subsets = {"All rows": np.ones(len(y), dtype=bool), "DS / AI / ML rows": (X["category"] == DS_CATEGORY).to_numpy()}
    names = list(subsets)
    lines = [
        f"Rows: {len(y)} total, {int(subsets[names[1]].sum())} DS / AI / ML. "
        f"CV: KFold({T.CV_SPLITS}, shuffle=True, random_state={T.CV_SEED}).",
        "",
        f"| Metric | {names[0]} | {names[1]} |",
        "|---|---|---|",
    ]

    def row(label, fn):
        cells = [fn(mask) for mask in subsets.values()]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    row("Median by category + title, MdAE", lambda m: f"${mdae(y[m], oof['baseline'].to_numpy()[m]):,.0f}")
    row("Gradient boosting (profile features), MdAE", lambda m: f"${mdae(y[m], oof['point'].to_numpy()[m]):,.0f}")
    row(
        "p25-p75 interval coverage (target 50%)",
        lambda m: f"{T.interval_coverage(y[m], oof['p25'].to_numpy()[m], oof['p75'].to_numpy()[m]):.1%}",
    )
    row("y below p25", lambda m: f"{np.mean(y[m] < oof['p25'].to_numpy()[m]):.1%}")
    row("y above p75", lambda m: f"{np.mean(y[m] > oof['p75'].to_numpy()[m]):.1%}")
    row(
        "Median interval width p75 - p25",
        lambda m: f"${np.median(oof['p75'].to_numpy()[m] - oof['p25'].to_numpy()[m]):,.0f}",
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=T.DEFAULT_DATA_DIR)
    args = p.parse_args(argv)

    raw, _ = T.load_survey(args.data)
    X, y = T.prepare(raw)
    oof = T.cross_val_predictions(X, y)
    print(report(X, y, oof))
    return 0


if __name__ == "__main__":
    sys.exit(main())
