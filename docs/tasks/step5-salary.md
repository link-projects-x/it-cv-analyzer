# Step 5 — salary model

Branch `feat/step5-salary`. Work in `ml/salary/` only. Read `docs/tasks/README.md` first.

## Goal

A model that estimates monthly salary (USD) for a candidate profile, trained on the open DOU salary survey, plus the
code that turns one profile into the `salary` block of `contracts/match-response.schema.json` (point, low, high, grid).
It must run locally and in the SageMaker scikit-learn container (script mode). Deployment is a later step.

## Data

- `https://raw.githubusercontent.com/devua/csv/master/salaries/2026_june_raw.csv` — 14,361 rows, 40 columns, UTF-8 with BOM.
  Download into `data/salary/` (gitignored); never commit it.
- Target: column `ЗАРПЛАТА СУМАРНИЙ ДОХІД в ІТ`. Assumption (not stated in the file): monthly income in USD.
- Keep rows where `Ваша основна зайнятість зараз` is `Працюю в ІТ-сфері / DefTech` and the target is between 100 and 30,000.

## Features and their mapping from the profile contract

The model reads exactly what `contracts/profile.schema.json` provides. Put the mapping in `features.py`, used by both
training and inference.

| Profile field | Survey column | Mapping |
|---|---|---|
| `salary_features.category` | `Категорії` | 1:1 |
| `salary_features.title` | `Title_clean` | 1:1 |
| `salary_features.primary_language` | `Основна мова програмування` | 1:1 |
| `salary_features.company_type` | `Основний напрям роботи компанії в якій працюєте` | 1:1 |
| `salary_features.company_size` | `Кількість спеціалістів у вашій компанії в Україні` | 1:1 |
| `salary_features.residence` | `Де ви зараз живете?` | 1:1 |
| `salary_features.domains` | 23 columns `У якій сфері проєкт в якому ви зараз працюєте? (<domain>)` | non-empty cell = selected; one 0/1 feature per domain in `contracts/common.schema.json -> domain` |
| `experience_years` | `Загальний стаж роботи за нинішньою ІТ-спеціальністю` | buckets to years: `Менше як 3 місяці` 0.1, `3 місяці` 0.25, `Пів року` 0.5, `1 рік` 1, `Півтора роки` 1.5, `N рік/роки/років` N, `15-20 років` 17.5, `Понад 20 років` 22; drop `-99` |
| `english` (CEFR) | `Знання англійської мови` | A1 Elementary, A2 Pre-Intermediate, B1 Intermediate, B2 Upper-Intermediate, C1 and C2 Advanced; `Не знаю взагалі` only in training |

A `null` in the profile means "no data": substitute the most frequent training value and record that in the output's
`model_version` metadata or logs, not silently.

## Baseline to beat

Measured on 2026-10-31 with 5-fold CV (median absolute error, USD), log target, `HistGradientBoostingRegressor` with
native categorical features over category, title, position, language, specialisation, company type and size, English,
city/residence, employment, plus numeric experience:

| Method | All rows | DS / AI / ML rows |
|---|---|---|
| Median by category + title | $676 | $792 |
| Gradient boosting | $574 | $683 |

Reproduce the median baseline and report your model against it with the same CV split (`KFold(5, shuffle=True,
random_state=0)`). Your feature set is limited to the profile-mapped features above, so numbers may differ; report
them, do not tune toward the table.

## Range

`low` and `high`: 25th and 75th percentile models (`loss="quantile"`). If a quantile model is worse than useless on
CV (coverage of the [p25, p75] interval far from 50%), report it and return `null` for low/high, as the contract allows.

## Grid (`salary.grid`)

For one profile, the estimate when one input changes and everything else stays as in the profile:

- `english`: every CEFR value.
- `experience_years`: keys `"0"` … `"15"`.
- `company_type`: every enum value of `profile.salary_features.company_type` except `null`.
- `domains`: every domain; the profile's domains replaced by that single domain.

This is the same idea as a sweep: re-run the model at other input values.

## Deliverables

- `features.py` — survey row and profile → feature frame, the mappings above.
- `train.py` — trains point and quantile models, saves to `$SM_MODEL_DIR` (default `ml/salary/model/`, gitignored).
  Script-mode compatible: reads training data from `$SM_CHANNEL_TRAIN` when set, otherwise from `data/salary/`.
- `evaluate.py` — CV report: baseline vs model, all rows and DS / AI / ML rows, interval coverage of p25–p75.
- `inference.py` — SageMaker handlers `model_fn`, `input_fn`, `predict_fn`, `output_fn`. Input: a profile
  (`contracts/profile.schema.json`). Output: the `salary` object of `contracts/match-response.schema.json`,
  `currency: "USD"`, `period: "month"`, `model_version` set.
- `requirements.txt` — pin scikit-learn and pandas. Note in the README which SageMaker scikit-learn container version
  you targeted and that it was not verified against a live container.
- `tests/` — pytest: experience bucket parsing, English mapping, a trained tiny model on a synthetic frame produces an
  output that validates against the `salary` sub-schema of `match-response.schema.json` (use `jsonschema` with the
  contracts registry, as `contracts/check.py` does), grid has every required key, null fields are filled.
- `README.md` — how to download data, train, evaluate, run inference locally; the CV results table from `evaluate.py`.

## Done when

`pytest ml/salary` passes, `python ml/salary/evaluate.py` prints the report, and the PR description includes that report.
