"""SageMaker inference handlers: profile (contracts/profile.schema.json) -> `salary` object of
contracts/match-response.schema.json.

Local use:
    python ml/salary/inference.py contracts/examples/profile.example.json [--model-dir ml/salary/model]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402

ARTIFACT = "salary-model.joblib"  # same name as train.ARTIFACT; train.py is not imported here
EXPERIENCE_GRID = range(0, 16)


def model_fn(model_dir: str) -> dict:
    return joblib.load(Path(model_dir) / ARTIFACT)


def input_fn(request_body, request_content_type: str = "application/json") -> dict:
    if request_content_type.split(";")[0].strip() != "application/json":
        raise ValueError(f"unsupported content type: {request_content_type}")
    if isinstance(request_body, (bytes, bytearray)):
        request_body = request_body.decode("utf-8")
    return json.loads(request_body)


def _usd(values) -> list[float]:
    return [float(round(v)) for v in values]


def predict_fn(profile: dict, artifact: dict) -> dict:
    base, imputed = F.profile_record(profile, artifact["fill"])

    variants: list[tuple[str, str, dict]] = []
    for cefr in F.CEFR:
        variants.append(("english", cefr, {**base, "english_level": F.english_level_from_cefr(cefr)}))
    for years in EXPERIENCE_GRID:
        variants.append(("experience_years", str(years), {**base, "experience_years": float(years)}))
    for company_type in F.COMPANY_TYPES:
        variants.append(("company_type", company_type, {**base, "company_type": company_type}))
    no_domains = {feature: 0.0 for feature in F.DOMAIN_FEATURES}
    for domain, feature in zip(F.DOMAINS, F.DOMAIN_FEATURES):
        variants.append(("domains", domain, {**base, **no_domains, feature: 1.0}))

    frame = F.to_frame([base] + [row for _, _, row in variants])
    models = artifact["models"]
    point = _usd(np.exp(models["point"].predict(frame)))

    grid: dict[str, dict[str, float]] = {"english": {}, "experience_years": {}, "company_type": {}, "domains": {}}
    for (slider, key, _), value in zip(variants, point[1:]):
        grid[slider][key] = value

    low = high = None
    if artifact.get("interval_ok"):
        first = frame.iloc[:1]
        q25 = float(np.exp(models["p25"].predict(first)[0]))
        q75 = float(np.exp(models["p75"].predict(first)[0]))
        low, high = float(round(min(q25, q75))), float(round(max(q25, q75)))

    version = artifact["version"]
    if imputed:
        version += "+imputed:" + ",".join(imputed)
    return {
        "currency": "USD",
        "period": "month",
        "point": point[0],
        "low": low,
        "high": high,
        "model_version": version,
        "grid": grid,
    }


def output_fn(prediction: dict, accept: str = "application/json"):
    if accept and accept.split(";")[0].strip() not in ("application/json", "*/*"):
        raise ValueError(f"unsupported accept type: {accept}")
    return json.dumps(prediction, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("profile", type=Path)
    p.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parent / "model")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    artifact = model_fn(str(args.model_dir))
    profile = input_fn(args.profile.read_bytes(), "application/json")
    print(json.dumps(json.loads(output_fn(predict_fn(profile, artifact))), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
