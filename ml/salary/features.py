"""DOU salary survey row and candidate profile -> one feature frame.

Training (survey rows) and inference (contracts/profile.schema.json) both go through `feature_frame`,
so the model sees the same columns with the same encoding in both places.

The value lists below are copied from contracts/common.schema.json and contracts/profile.schema.json;
tests/test_salary.py fails when they drift. They are hardcoded so that inference in the SageMaker
container does not need the contracts directory.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

TARGET = "ЗАРПЛАТА СУМАРНИЙ ДОХІД в ІТ"
EMPLOYMENT = "Ваша основна зайнятість зараз"
EMPLOYMENT_KEEP = "Працюю в ІТ-сфері / DefTech"
TARGET_MIN, TARGET_MAX = 100, 30_000

EXPERIENCE_COLUMN = "Загальний стаж роботи за нинішньою ІТ-спеціальністю"
ENGLISH_COLUMN = "Знання англійської мови"
DOMAIN_COLUMN = "У якій сфері проєкт в якому ви зараз працюєте? ({})"
DOMAIN_SELECTED = "обрано"  # the other value in these columns is "не обрано"

# profile.salary_features field -> survey column, copied 1:1.
CATEGORICAL = {
    "category": "Категорії",
    "title": "Title_clean",
    "primary_language": "Основна мова програмування",
    "company_type": "Основний напрям роботи компанії в якій працюєте",
    "company_size": "Кількість спеціалістів у вашій компанії в Україні",
    "residence": "Де ви зараз живете?",
}

# contracts/common.schema.json -> $defs.domain.enum, in the same order.
DOMAINS = [
    "AdTech / Marketing",
    "AI / Data / Analytics",
    "Blockchain / Web3",
    "DefTech / MilTech",
    "E-commerce / Retail / Marketplace",
    "EdTech / Education",
    "Enterprise / SaaS / ERP",
    "Fintech / Banking / Insurance / Capital markets",
    "GameDev",
    "Gambling",
    "GovTech / Legal / Public services",
    "Healthcare / MedTech / Wellbeing / Sports",
    "Hospitality / Travel / HORECA",
    "Industrial / Manufacturing / Energy / Agriculture",
    "Automotive",
    "Embedded / IoT / Hardware / Robotics",
    "Infrastructure / Cloud / Hosting / Telecom",
    "Logistics / Supply Chain / Geospatial",
    "Media / Entertainment / Dating / Consumer apps",
    "Real Estate / PropTech",
    "Security / Cybersecurity",
]

# contracts/profile.schema.json -> salary_features.company_type.enum without null.
COMPANY_TYPES = [
    "Продуктова",
    "Сервісна (аутсорсингова)",
    "Аутстафінгова",
    "Стартап",
    "НЕ ІТ-компанія (банк, телеком, ритейл тощо)",
    "Державне підприємство / установа",
    "Фрилансер",
    "Інша (ГО / агенція / заклад освіти тощо)",
]

CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
CEFR_TO_SURVEY = {
    "A1": "Elementary",
    "A2": "Pre-Intermediate",
    "B1": "Intermediate",
    "B2": "Upper-Intermediate",
    "C1": "Advanced",
    "C2": "Advanced",
}
# Ordinal used as the model feature. "Не знаю взагалі" exists only in the survey.
SURVEY_ENGLISH_LEVEL = {
    "Не знаю взагалі": 0,
    "Elementary": 1,
    "Pre-Intermediate": 2,
    "Intermediate": 3,
    "Upper-Intermediate": 4,
    "Advanced": 5,
}

EXPERIENCE_FIXED = {
    "Менше як 3 місяці": 0.1,
    "3 місяці": 0.25,
    "Пів року": 0.5,
    "1 рік": 1.0,
    "Півтора роки": 1.5,
    "15-20 років": 17.5,
    "Понад 20 років": 22.0,
}
_EXPERIENCE_YEARS = re.compile(r"^(\d+) (рік|роки|років)$")

DOMAIN_FEATURES = [f"domain: {d}" for d in DOMAINS]
CATEGORICAL_FEATURES = list(CATEGORICAL)
NUMERIC_FEATURES = ["experience_years", "english_level"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES + DOMAIN_FEATURES

# Profile fields that may be null; `english` is outside salary_features but is nullable too.
NULLABLE_FIELDS = CATEGORICAL_FEATURES + ["english"]


def parse_experience(value: Any) -> float | None:
    """Survey experience bucket -> years. `-99` and empty -> None. Unknown text raises ValueError."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    if text == "-99":
        return None
    if text in EXPERIENCE_FIXED:
        return EXPERIENCE_FIXED[text]
    m = _EXPERIENCE_YEARS.match(text)
    if m:
        return float(m.group(1))
    raise ValueError(f"unknown experience bucket: {text!r}")


def english_level_from_survey(value: Any) -> float:
    """Survey English answer -> ordinal 0..5; empty -> NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    return float(SURVEY_ENGLISH_LEVEL[str(value)])


def english_level_from_cefr(cefr: str) -> float:
    return float(SURVEY_ENGLISH_LEVEL[CEFR_TO_SURVEY[cefr]])


def parse_target(value: Any) -> float:
    """Salary cell -> float. One cell in the June 2026 file uses a decimal comma ("3657,5")."""
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return np.nan


def filter_survey(raw: pd.DataFrame) -> pd.DataFrame:
    """Rows used for training: employed in IT, target in [100, 30000], known experience."""
    target = raw[TARGET].map(parse_target)
    experience = raw[EXPERIENCE_COLUMN].map(parse_experience)
    keep = (raw[EMPLOYMENT] == EMPLOYMENT_KEEP) & target.between(TARGET_MIN, TARGET_MAX) & experience.notna()
    return raw.loc[keep].reset_index(drop=True)


def survey_target(rows: pd.DataFrame) -> np.ndarray:
    return rows[TARGET].map(parse_target).to_numpy(dtype=float)


def survey_records(rows: pd.DataFrame) -> pd.DataFrame:
    """Survey rows -> frame with one column per FEATURES entry (categoricals as strings or None)."""
    out = pd.DataFrame(index=rows.index)
    for field, column in CATEGORICAL.items():
        out[field] = rows[column].astype(object).where(rows[column].notna(), None)
    out["experience_years"] = rows[EXPERIENCE_COLUMN].map(parse_experience).astype(float)
    out["english_level"] = rows[ENGLISH_COLUMN].map(english_level_from_survey).astype(float)
    for domain, feature in zip(DOMAINS, DOMAIN_FEATURES):
        out[feature] = (rows[DOMAIN_COLUMN.format(domain)] == DOMAIN_SELECTED).astype(float)
    return out[FEATURES].reset_index(drop=True)


def profile_record(profile: dict, fill: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Profile (contracts/profile.schema.json) -> one feature row and the list of fields filled from `fill`.

    `fill` maps each field in NULLABLE_FIELDS to the most frequent training value
    (for `english`, a CEFR code). A null field gets that value and its name goes into the returned list.
    """
    sf = profile["salary_features"]
    imputed: list[str] = []
    row: dict[str, Any] = {}
    for field in CATEGORICAL_FEATURES:
        value = sf.get(field)
        if value is None:
            value = fill[field]
            imputed.append(field)
        row[field] = value

    english = profile.get("english")
    if english is None:
        english = fill["english"]
        imputed.append("english")
    row["english_level"] = english_level_from_cefr(english)
    row["experience_years"] = float(profile["experience_years"])

    selected = set(sf.get("domains") or [])
    unknown = selected - set(DOMAINS)
    if unknown:
        raise ValueError(f"unknown domains: {sorted(unknown)}")
    for domain, feature in zip(DOMAINS, DOMAIN_FEATURES):
        row[feature] = 1.0 if domain in selected else 0.0

    if imputed:
        log.warning("salary profile %s: null fields filled with training mode: %s", profile.get("id"), imputed)
    return row, imputed


def most_frequent_values(records: pd.DataFrame) -> dict[str, Any]:
    """Training mode of each nullable field, ignoring missing values. `english` is returned as CEFR."""
    fill: dict[str, Any] = {}
    for field in CATEGORICAL_FEATURES:
        fill[field] = records[field].dropna().value_counts().index[0]
    level = int(records["english_level"].dropna().value_counts().index[0])
    # The mode is a survey level; pick the lowest CEFR code that maps to it. Level 0 has no CEFR code.
    fill["english"] = next(c for c in CEFR if english_level_from_cefr(c) == max(level, 1))
    return fill


def to_frame(rows: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    """Rows -> frame in FEATURES order with object categoricals and float numerics."""
    frame = pd.DataFrame(rows)[FEATURES].copy()
    for field in CATEGORICAL_FEATURES:
        column = frame[field].astype(object)
        frame[field] = column.where(column.notna(), np.nan)  # None -> NaN, which OrdinalEncoder treats as missing
    for field in NUMERIC_FEATURES + DOMAIN_FEATURES:
        frame[field] = frame[field].astype(float)
    return frame
