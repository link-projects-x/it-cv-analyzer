import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

import features as F
import inference
import train as T

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA_FILES = ["common", "vacancy", "profile", "match-response"]
SALARY_SCHEMA = {"$ref": "https://dou-cv-analyzer.local/contracts/match-response.schema.json#/properties/salary"}
TINY = dict(max_iter=30, min_samples_leaf=5)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def salary_validator():
    registry = Registry()
    for name in SCHEMA_FILES:
        schema = load_json(CONTRACTS / f"{name}.schema.json")
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(SALARY_SCHEMA, registry=registry, format_checker=FormatChecker())


def errors(validator, doc):
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator.iter_errors(doc)]


def profile_enum(field):
    schema = load_json(CONTRACTS / "profile.schema.json")
    return schema["properties"]["salary_features"]["properties"][field]["enum"]


def synthetic_survey(n=400, seed=0) -> pd.DataFrame:
    """Survey-shaped frame with the raw column names; salary grows with experience and English."""
    rng = np.random.default_rng(seed)
    experience = ["Менше як 3 місяці", "Пів року", "1 рік", "2 роки", "5 років", "10 років", "15-20 років"]
    english = list(F.SURVEY_ENGLISH_LEVEL)
    data = {F.EMPLOYMENT: [F.EMPLOYMENT_KEEP] * n}
    for field, column in F.CATEGORICAL.items():
        values = [v for v in profile_enum(field) if v is not None]
        data[column] = rng.choice(values, n)
    data[F.EXPERIENCE_COLUMN] = rng.choice(experience, n)
    data[F.ENGLISH_COLUMN] = rng.choice(english, n)
    for domain in F.DOMAINS:
        data[F.DOMAIN_COLUMN.format(domain)] = rng.choice(["обрано", "не обрано"], n, p=[0.2, 0.8])
    years = np.array([F.parse_experience(v) for v in data[F.EXPERIENCE_COLUMN]])
    level = np.array([F.SURVEY_ENGLISH_LEVEL[v] for v in data[F.ENGLISH_COLUMN]])
    salary = 800 + 250 * years + 300 * level + rng.normal(0, 200, n)
    data[F.TARGET] = [str(int(max(s, 150))) for s in salary]
    return pd.DataFrame(data)


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    model_dir = tmp_path_factory.mktemp("model")
    T.save(T.train(synthetic_survey(), data_sha256="0" * 64, **TINY), model_dir)
    return inference.model_fn(str(model_dir))


@pytest.fixture
def profile():
    return load_json(CONTRACTS / "examples" / "profile.example.json")


def run(profile, artifact) -> dict:
    body = json.dumps(profile).encode("utf-8")
    prediction = inference.predict_fn(inference.input_fn(body, "application/json"), artifact)
    return json.loads(inference.output_fn(prediction, "application/json"))


# --- mappings ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bucket, years",
    [
        ("Менше як 3 місяці", 0.1),
        ("3 місяці", 0.25),
        ("Пів року", 0.5),
        ("1 рік", 1.0),
        ("Півтора роки", 1.5),
        ("2 роки", 2.0),
        ("4 роки", 4.0),
        ("5 років", 5.0),
        ("14 років", 14.0),
        ("15-20 років", 17.5),
        ("Понад 20 років", 22.0),
    ],
)
def test_experience_buckets(bucket, years):
    assert F.parse_experience(bucket) == years


def test_experience_missing_and_unknown():
    assert F.parse_experience("-99") is None
    assert F.parse_experience(None) is None
    assert F.parse_experience(float("nan")) is None
    with pytest.raises(ValueError):
        F.parse_experience("багато років")


def test_english_mapping():
    assert F.CEFR_TO_SURVEY == {
        "A1": "Elementary",
        "A2": "Pre-Intermediate",
        "B1": "Intermediate",
        "B2": "Upper-Intermediate",
        "C1": "Advanced",
        "C2": "Advanced",
    }
    levels = [F.english_level_from_cefr(c) for c in F.CEFR]
    assert levels == sorted(levels)
    assert F.english_level_from_cefr("C1") == F.english_level_from_cefr("C2")
    # "Не знаю взагалі" is a training-only value: below A1 and unreachable from a profile.
    assert F.english_level_from_survey("Не знаю взагалі") < F.english_level_from_cefr("A1")
    assert "Не знаю взагалі" not in F.CEFR_TO_SURVEY.values()


def test_value_lists_match_contracts():
    common = load_json(CONTRACTS / "common.schema.json")["$defs"]
    assert F.DOMAINS == common["domain"]["enum"]
    assert F.CEFR == common["cefr"]["enum"]
    assert F.COMPANY_TYPES == [v for v in profile_enum("company_type") if v is not None]
    assert set(F.CATEGORICAL) | {"domains"} == set(
        load_json(CONTRACTS / "profile.schema.json")["properties"]["salary_features"]["required"]
    )


def test_survey_rows_filter_and_domains():
    raw = synthetic_survey(n=6)
    raw.loc[0, F.EMPLOYMENT] = "Працюю НЕ в ІТ-сфері, але дотично до ІТ"
    raw.loc[1, F.TARGET] = "99"
    raw.loc[2, F.TARGET] = "30001"
    raw.loc[3, F.TARGET] = "3657,5"
    raw.loc[4, F.EXPERIENCE_COLUMN] = "-99"
    raw.loc[3, F.DOMAIN_COLUMN.format(F.DOMAINS[0])] = "обрано"
    raw.loc[3, F.DOMAIN_COLUMN.format(F.DOMAINS[1])] = "не обрано"
    rows = F.filter_survey(raw)
    assert len(rows) == 2
    assert F.survey_target(rows)[0] == 3657.5
    records = F.survey_records(rows)
    assert records.loc[0, F.DOMAIN_FEATURES[0]] == 1.0
    assert records.loc[0, F.DOMAIN_FEATURES[1]] == 0.0  # "не обрано" is a non-empty cell, not a selection


# --- model output -----------------------------------------------------------------------------------


@pytest.mark.parametrize("interval_ok", [True, False])
def test_output_validates_against_salary_schema(salary_validator, artifact, profile, interval_ok):
    out = run(profile, {**artifact, "interval_ok": interval_ok})
    assert errors(salary_validator, out) == []
    assert out["currency"] == "USD" and out["period"] == "month"
    assert out["model_version"].startswith(artifact["version"])
    if interval_ok:
        assert out["low"] is not None and out["high"] is not None and out["low"] <= out["high"]
    else:
        assert out["low"] is None and out["high"] is None


def test_grid_has_every_key(artifact, profile):
    grid = run(profile, artifact)["grid"]
    assert set(grid["english"]) == set(F.CEFR)
    assert set(grid["experience_years"]) == {str(i) for i in range(16)}
    assert set(grid["company_type"]) == set(F.COMPANY_TYPES)
    assert set(grid["domains"]) == set(F.DOMAINS)


def test_grid_matches_point_at_profile_values(artifact, profile):
    profile["salary_features"]["domains"] = ["GameDev"]
    out = run(profile, artifact)
    assert out["grid"]["english"][profile["english"]] == out["point"]
    assert out["grid"]["experience_years"][str(int(profile["experience_years"]))] == out["point"]
    assert out["grid"]["company_type"][profile["salary_features"]["company_type"]] == out["point"]
    assert out["grid"]["domains"]["GameDev"] == out["point"]


def test_null_fields_filled_and_recorded(salary_validator, artifact, profile):
    nulls = copy.deepcopy(profile)
    nulls["english"] = None
    for field in F.CATEGORICAL:
        nulls["salary_features"][field] = None

    row, imputed = F.profile_record(nulls, artifact["fill"])
    assert sorted(imputed) == sorted(F.NULLABLE_FIELDS)
    for field in F.CATEGORICAL:
        assert row[field] == artifact["fill"][field]
        assert row[field] is not None
    assert artifact["fill"]["english"] in F.CEFR

    out = run(nulls, artifact)
    assert errors(salary_validator, out) == []
    for field in F.NULLABLE_FIELDS:
        assert field in out["model_version"].split("+imputed:")[1].split(",")
    assert out["grid"]["english"][artifact["fill"]["english"]] == out["point"]


def test_no_imputation_suffix_when_profile_is_complete(artifact, profile):
    profile["salary_features"]["company_size"] = "До 200"
    assert run(profile, artifact)["model_version"] == artifact["version"]


def test_unknown_domain_rejected(artifact, profile):
    profile["salary_features"]["domains"] = ["Різнопланові проєкти, немає одного основного"]
    with pytest.raises(ValueError):
        inference.predict_fn(profile, artifact)


def test_train_cli_writes_model(tmp_path):
    data_dir, model_dir = tmp_path / "data", tmp_path / "model"
    data_dir.mkdir()
    synthetic_survey(n=200).to_csv(data_dir / T.DATA_FILE, index=False, encoding="utf-8-sig")
    assert T.main(["--train", str(data_dir), "--model-dir", str(model_dir), "--skip-cv"]) == 0
    assert (model_dir / T.ARTIFACT).exists()
    assert load_json(model_dir / "metadata.json")["interval_ok"] is False
