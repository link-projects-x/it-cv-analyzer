# Salary model (step 5)

Estimates monthly salary in USD for a candidate profile (`contracts/profile.schema.json`) and returns the
`salary` object of `contracts/match-response.schema.json`: `point`, `low`, `high`, `grid`, `model_version`.

Trained on the open DOU salary survey, June 2026. Assumption (the file does not state units): the target column
`ЗАРПЛАТА СУМАРНИЙ ДОХІД в ІТ` holds monthly income in USD.

## Files

| File | What |
|---|---|
| `features.py` | survey row and profile → feature frame; value lists and mappings; used by training and inference |
| `train.py` | trains point, p25 and p75 models; saves `salary-model.joblib` and `metadata.json` |
| `evaluate.py` | 5-fold CV report: baseline vs model, p25–p75 coverage |
| `inference.py` | SageMaker handlers `model_fn`, `input_fn`, `predict_fn`, `output_fn`; also a local CLI |
| `package.sh` | builds `dist/model.tar.gz` for the SageMaker endpoint (model + `code/`) |
| `tests/` | pytest on a synthetic survey frame; no real data needed |

## Run locally

From the repo root, with a Python 3.12 venv (`pip install -r ml/salary/requirements.txt -r contracts/requirements.txt pytest`;
numpy 2.5.1 requires Python >= 3.12 and pandas 2.2.3 has wheels up to Python 3.13):

```bash
# data (gitignored, never commit it)
mkdir -p data/salary
curl -L -o data/salary/2026_june_raw.csv \
  https://raw.githubusercontent.com/devua/csv/master/salaries/2026_june_raw.csv

python ml/salary/train.py                      # -> ml/salary/model/ (gitignored), about 10 s
python ml/salary/evaluate.py                   # prints the CV table below, about 25 s
python ml/salary/inference.py contracts/examples/profile.example.json
python -m pytest ml/salary -q
ml/salary/package.sh                           # -> dist/model.tar.gz
```

`train.py` reads `$SM_CHANNEL_TRAIN` and writes to `$SM_MODEL_DIR` when they are set (SageMaker script mode),
otherwise `data/salary/` and `ml/salary/model/`. `--skip-cv` skips the interval check; `low`/`high` are then `null`.

## Data and features

Rows kept: `Ваша основна зайнятість зараз` = `Працюю в ІТ-сфері / DefTech`, target in [100, 30000], experience not
`-99`. 12,630 of 14,361 rows remain, 410 of them in `DS / AI / ML / Data Engineering`. One target cell uses a
decimal comma (`3657,5`) and is parsed as 3657.5. All categories are kept for training, including those missing
from the profile enum (HR, Marketing, ...).

| Profile field | Feature | Mapping |
|---|---|---|
| `salary_features.category`, `title`, `primary_language`, `company_type`, `company_size`, `residence` | categorical, native in the model | 1:1 with the survey column |
| `salary_features.domains` | 21 features 0/1, one per `common.schema.json → domain` | cell `обрано` = 1, `не обрано` = 0 |
| `experience_years` | number | survey buckets → years (`Менше як 3 місяці` 0.1 … `Понад 20 років` 22) |
| `english` | ordinal 0–5 | `Не знаю взагалі` 0 (training only), A1 Elementary 1, A2 Pre-Intermediate 2, B1 Intermediate 3, B2 Upper-Intermediate 4, C1 and C2 Advanced 5 |

The survey has 23 domain columns; `Різнопланові проєкти, немає одного основного` and `Інше (впишіть свій варіант)`
are not in the contract enum and are not used. Empty `Основна мова програмування` (5,604 raw rows, people who
do not program) stays missing in training; at each split the model sends missing values to the side chosen during training.

A `null` profile field is replaced with the most frequent training value (missing values excluded; `english` → `B2`).
The replaced fields are logged as a warning and appended to `model_version`, e.g.
`salary-hgb-v1-20261031-c9ce3517+imputed:company_size`.

## Model

`HistGradientBoostingRegressor` on `log(salary)`, default hyperparameters, `random_state=0`, categorical features
via `OrdinalEncoder` (unknown and missing → NaN). Monotonic constraints +1 on `experience_years` and
`english_level`, so a slider moving up never lowers the estimate. Without the constraints CV MdAE was $594 (all rows)
and $762 (DS / AI / ML), measured once on the same split.

- `point`: squared-error model, `exp` of the prediction.
- `low` / `high`: quantile models, `quantile=0.25` and `0.75`, `exp` of the prediction (quantiles survive the log).
  `train.py` runs 5-fold CV on them first. Coverage outside 50% ± 10 points → `interval_ok: false` in the
  artifact and `low`/`high` are `null`. Measured coverage: 46.1%, so the interval is returned.
- `grid`: the point model re-run with one input changed: every CEFR value, experience 0…15, every `company_type`
  value, each domain alone in place of the profile's domains. Values are rounded to whole USD.

## CV results

`python ml/salary/evaluate.py`, run on 2026-10-31, `KFold(5, shuffle=True, random_state=0)`; models are trained on
all rows of each fold, the DS / AI / ML column scores only that category's test rows. MdAE = median absolute error.

| Metric | All rows | DS / AI / ML rows |
|---|---|---|
| Median by category + title, MdAE | $700 | $800 |
| Gradient boosting (profile features), MdAE | $599 | $745 |
| p25-p75 interval coverage (target 50%) | 46.1% | 45.9% |
| y below p25 | 27.0% | 25.9% |
| y above p75 | 26.9% | 28.3% |
| Median interval width p75 - p25 | $1,149 | $1,382 |

The task brief reports $676 / $792 for the same median baseline; this run gives $700 / $800 on 12,630 rows. Unknown
why they differ; the brief does not state its row count.

## SageMaker

Targeted container: SageMaker scikit-learn `1.9-0` (`sagemaker-scikit-learn:1.9-0-cpu-py3`; scikit-learn 1.9.0,
pandas 2.2.3, numpy 2.5.1, joblib 1.5.3, Python 3.12, x86 only). Sources read on 2026-10-31: the AWS docs page
"Resources for using Scikit-learn with Amazon SageMaker AI" lists versions up to `1.4-2` only; the SageMaker Python SDK
image config (`sagemaker-core/src/sagemaker/core/image_uri_config/sklearn.json`, `1.9-0` added 2026-09-16) lists
inference versions `0.20.0` … `1.4-2-py312`, `1.9-0`, CPU, registry account `683313688378` in us-east-1;
`aws/deep-learning-containers` `docker/sklearn/1.9-0/uv.lock` gives the package versions and
`.github/config/image/sklearn/sagemaker-1.9-0.yml` gives `arch_type: "x86"`. **Not verified against a live container.**

- `requirements.txt` pins the container's versions. Run on 2026-10-31 in a Python 3.12.16 venv with exactly these pins:
  `pytest ml/salary` 23 passed; `train.py` on the June 2026 survey: 12,630 rows, p25-p75 coverage 46.1% (as above);
  the model from `dist/model.tar.gz`, extracted and imported from `code/`, returned an estimate for the example profile.
  The tests also pass with Python 3.14.6, scikit-learn 1.9.1, pandas 3.1.0.
- Not verified: that the `1.9-0` image exists in the deployment region; that the container installs
  `code/requirements.txt` and imports `code/inference.py` with `SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code`
  (the layout the SageMaker SDK repack produces; assumption); serverless cold start time.
- `output_fn` returns a JSON string. In `sagemaker-containers` `_transformer.py` the value returned by `output_fn`
  goes to Flask unchanged, so the body is the JSON text; assumption: Flask labels a plain string `text/html`. The
  matcher parses the body as JSON without reading the content type.
- `features.py` must be in `code/` next to `inference.py`; the artifact holds only scikit-learn objects and
  plain dicts, so unpickling does not import project modules.
- `package.sh` refuses a model whose `metadata.json` `sklearn_version` differs from the pin.
