"""Train the salary models on the DOU survey and save them.

Three HistGradientBoostingRegressor models on log(salary): point (squared error), p25 and p75 (quantile loss).
A 5-fold CV of the p25-p75 interval runs before the final fit; when its coverage is outside
50% +- COVERAGE_TOLERANCE, the artifact is marked and inference returns null low/high.

Script mode (SageMaker scikit-learn container):
    training data from $SM_CHANNEL_TRAIN (first *.csv), model to $SM_MODEL_DIR.
Locally:
    python ml/salary/train.py            # data/salary/*.csv -> ml/salary/model/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_DATA_DIR = REPO / "data" / "salary"
DEFAULT_MODEL_DIR = HERE / "model"
DATA_URL = "https://raw.githubusercontent.com/devua/csv/master/salaries/2026_june_raw.csv"
DATA_FILE = "2026_june_raw.csv"
ARTIFACT = "salary-model.joblib"
MODEL_FAMILY = "salary-hgb-v1"

QUANTILES = {"p25": 0.25, "p75": 0.75}
COVERAGE_TOLERANCE = 0.10
CV_SPLITS = 5
CV_SEED = 0
# Salary should not fall when experience or English rises; also keeps the slider grid monotone.
MONOTONIC = {"experience_years": 1, "english_level": 1}


def make_model(loss: str = "squared_error", quantile: float | None = None, **params) -> Pipeline:
    encoder = OrdinalEncoder(
        handle_unknown="use_encoded_value", unknown_value=np.nan, encoded_missing_value=np.nan
    )
    pre = ColumnTransformer(
        [("cat", encoder, F.CATEGORICAL_FEATURES)], remainder="passthrough", verbose_feature_names_out=False
    ).set_output(transform="pandas")
    kwargs = dict(
        loss=loss,
        categorical_features=F.CATEGORICAL_FEATURES,
        monotonic_cst=MONOTONIC,
        random_state=0,
    )
    if quantile is not None:
        kwargs["quantile"] = quantile
    kwargs.update(params)
    return Pipeline([("pre", pre), ("hgb", HistGradientBoostingRegressor(**kwargs))])


def fit_models(X: pd.DataFrame, y: np.ndarray, **params) -> dict[str, Pipeline]:
    log_y = np.log(y)
    models = {"point": make_model(**params).fit(X, log_y)}
    for name, q in QUANTILES.items():
        models[name] = make_model("quantile", q, **params).fit(X, log_y)
    return models


def predict_usd(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
    return np.exp(model.predict(X))


def baseline_predict(train_X: pd.DataFrame, train_y: np.ndarray, test_X: pd.DataFrame) -> np.ndarray:
    """Median salary by (category, title) in the training fold; overall median for unseen pairs."""
    keys = ["category", "title"]
    medians = pd.DataFrame(train_X[keys]).assign(y=train_y).groupby(keys, dropna=False)["y"].median()
    joined = pd.DataFrame(test_X[keys]).join(medians, on=keys)
    return joined["y"].fillna(float(np.median(train_y))).to_numpy()


def cross_val_predictions(X: pd.DataFrame, y: np.ndarray, **params) -> pd.DataFrame:
    """Out-of-fold predictions with KFold(5, shuffle=True, random_state=0)."""
    out = pd.DataFrame(index=X.index, columns=["baseline", "point", "p25", "p75"], dtype=float)
    for train_idx, test_idx in KFold(CV_SPLITS, shuffle=True, random_state=CV_SEED).split(X):
        Xtr, Xte, ytr = X.iloc[train_idx], X.iloc[test_idx], y[train_idx]
        out.iloc[test_idx, out.columns.get_loc("baseline")] = baseline_predict(Xtr, ytr, Xte)
        for name, model in fit_models(Xtr, ytr, **params).items():
            out.iloc[test_idx, out.columns.get_loc(name)] = predict_usd(model, Xte)
    return out


def interval_coverage(y: np.ndarray, low: np.ndarray, high: np.ndarray) -> float:
    return float(np.mean((y >= low) & (y <= high)))


def load_survey(data_dir: Path) -> tuple[pd.DataFrame, str]:
    """Read the first *.csv in data_dir (UTF-8 with BOM). Returns the raw frame and the file's sha256."""
    path = data_dir / DATA_FILE
    if not path.exists():
        found = sorted(data_dir.glob("*.csv"))
        if not found:
            raise FileNotFoundError(f"no CSV in {data_dir}; download {DATA_URL} into data/salary/")
        path = found[0]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str), digest


def prepare(raw: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    rows = F.filter_survey(raw)
    return F.to_frame(F.survey_records(rows)), F.survey_target(rows)


def train(raw: pd.DataFrame, data_sha256: str = "", run_cv: bool = True, **params) -> dict:
    X, y = prepare(raw)
    coverage = None
    if run_cv:
        oof = cross_val_predictions(X, y, **params)
        coverage = interval_coverage(y, oof["p25"].to_numpy(), oof["p75"].to_numpy())
    interval_ok = coverage is not None and abs(coverage - 0.5) <= COVERAGE_TOLERANCE

    stamp = datetime.now(timezone.utc)
    version = f"{MODEL_FAMILY}-{stamp:%Y%m%d}" + (f"-{data_sha256[:8]}" if data_sha256 else "")
    return {
        "models": fit_models(X, y, **params),
        "fill": F.most_frequent_values(X),
        "version": version,
        "interval_ok": interval_ok,
        "cv_interval_coverage": coverage,
        "trained_at": stamp.isoformat(),
        "trained_rows": int(len(y)),
        "data_sha256": data_sha256,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "features": F.FEATURES,
        "params": params,
    }


def save(artifact: dict, model_dir: Path) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / ARTIFACT
    joblib.dump(artifact, path)
    meta = {k: v for k, v in artifact.items() if k != "models"}
    (model_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--train", type=Path, default=Path(os.environ.get("SM_CHANNEL_TRAIN", DEFAULT_DATA_DIR)))
    p.add_argument("--model-dir", type=Path, default=Path(os.environ.get("SM_MODEL_DIR", DEFAULT_MODEL_DIR)))
    p.add_argument("--skip-cv", action="store_true", help="skip the interval CV; low/high will be null")
    args, _unknown = p.parse_known_args(argv)  # SageMaker may pass extra hyperparameters

    raw, digest = load_survey(args.train)
    artifact = train(raw, data_sha256=digest, run_cv=not args.skip_cv)
    path = save(artifact, args.model_dir)
    print(
        f"rows={artifact['trained_rows']} version={artifact['version']} "
        f"cv_interval_coverage={artifact['cv_interval_coverage']} interval_ok={artifact['interval_ok']} -> {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
