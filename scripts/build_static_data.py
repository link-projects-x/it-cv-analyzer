"""Build the data files of the static site (no backend): web/public/data/

  vacancies.json  every parsed vacancy from data/processed/ with its DOU category from the raw .meta.json:
                  [{"category": "Java", "vacancy": {...vacancy.schema.json...}}, ...]
  salary.json     the salary model run over every combination the browser can pick:
                  survey category x title x primary language x experience 0..15 x CEFR.
                  {"model_version", "experience": [0..15], "cefr": [...], "table": {"<cat>|<title>|<lang>":
                  {"point": [[16 x 6]], "low": [[...]], "high": [[...]]}}}; lang "" = the training mode.

  python scripts/build_static_data.py --data data --model-dir ml/salary/model --out web/public/data
  python scripts/build_static_data.py --public   # public deploy: no company, title text, quotes, links or source
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml" / "salary"))
import features as F  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from public_data import anonymise_all  # noqa: E402

PROFILE_SCHEMA = json.loads((ROOT / "contracts" / "profile.schema.json").read_text(encoding="utf-8"))
SF = PROFILE_SCHEMA["properties"]["salary_features"]["properties"]
CATEGORIES = [c for c in SF["category"]["enum"] if c is not None]
TITLES = ["Intern/Trainee", "Junior", "Middle", "Senior", "Lead"]
LANGUAGES = [l for l in SF["primary_language"]["enum"] if l is not None]
EXPERIENCE = list(range(16))


def build_vacancies(data: Path, public: bool = False) -> list[dict]:
    out = []
    for path in sorted((data / "processed").glob("dou-*.json")):
        vacancy = json.loads(path.read_text(encoding="utf-8"))
        meta_path = data / "raw" / f"{path.stem}.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        out.append({"category": meta.get("category"), "vacancy": vacancy})
    return anonymise_all(out) if public else out


def build_salary(model_dir: Path) -> dict:
    artifact = joblib.load(model_dir / "salary-model.joblib")
    fill = artifact["fill"]
    combos = list(itertools.product(CATEGORIES, TITLES, LANGUAGES + [""]))
    rows = []
    for category, title, lang in combos:
        base = {
            "category": category,
            "title": title,
            "primary_language": lang or fill["primary_language"],
            "company_type": fill["company_type"],
            "company_size": fill["company_size"],
            "residence": fill["residence"],
            **{feature: 0.0 for feature in F.DOMAIN_FEATURES},
        }
        for years in EXPERIENCE:
            for cefr in F.CEFR:
                rows.append({**base, "experience_years": float(years), "english_level": F.english_level_from_cefr(cefr)})

    frame = F.to_frame(rows)
    models = artifact["models"]
    point = np.exp(models["point"].predict(frame))
    has_interval = bool(artifact.get("interval_ok"))
    q25 = np.exp(models["p25"].predict(frame)) if has_interval else None
    q75 = np.exp(models["p75"].predict(frame)) if has_interval else None

    per_combo = len(EXPERIENCE) * len(F.CEFR)
    table = {}
    for i, (category, title, lang) in enumerate(combos):
        sl = slice(i * per_combo, (i + 1) * per_combo)

        def grid(values):
            return np.round(values[sl]).astype(int).reshape(len(EXPERIENCE), len(F.CEFR)).tolist()

        entry = {"point": grid(point)}
        if has_interval:
            entry["low"] = grid(np.minimum(q25, q75))
            entry["high"] = grid(np.maximum(q25, q75))
        table[f"{category}|{title}|{lang}"] = entry

    return {
        "model_version": artifact["version"],
        "experience": EXPERIENCE,
        "cefr": F.CEFR,
        "categories": CATEGORIES,
        "titles": TITLES,
        "languages": LANGUAGES,
        "table": table,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--model-dir", type=Path, default=ROOT / "ml" / "salary" / "model")
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "data")
    ap.add_argument("--public", action="store_true", help="anonymise: no company, title text, quotes, links or source site")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    vacancies = build_vacancies(args.data, public=args.public)
    (args.out / "vacancies.json").write_text(json.dumps(vacancies, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    salary = build_salary(args.model_dir)
    (args.out / "salary.json").write_text(json.dumps(salary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    missing = sum(1 for v in vacancies if not v["category"])
    print(f"vacancies: {len(vacancies)} ({missing} without category); salary combos: {len(salary['table'])}")


if __name__ == "__main__":
    main()
