# IT CV Analyzer

Upload a CV, see which skills it is missing for IT vacancies, and move sliders to see how coverage and the salary estimate change.

Live demo: https://it-cv-analyzer.vercel.app

The demo runs entirely in the browser: the CV is parsed locally (PDF, DOCX, TXT) and never leaves the page. It compares the CV with about 1,770 parsed vacancies from jobs.dou.ua across 30 IT categories and estimates salary with a model trained on the open DOU salary survey. The vacancy data in the demo is anonymised: no company names, no titles, no quotes or links, only grade, required skills, years, English level and location.

A Job Squad learning project: the full pipeline is built as the set of AWS services that DOU AI/ML vacancies mention most often (Lambda, S3, Bedrock, SageMaker, Terraform). The live demo is the static build of the same frontend.

## Layout

```
contracts/          JSON Schemas, skill vocabulary, examples, check.py
infra/              Terraform (see infra/README.md for the diagram and deploy steps)
scripts/            build_lambdas.sh: Lambda zips for python3.13 arm64
services/scraper/   Lambda: DOU vacancies → S3 raw/dou-<id>.html
services/parser/    Lambda: raw/ → Claude Haiku 5.5 on Bedrock → processed/dou-<id>.json (vacancy.schema.json)
services/cv/        Lambda: CV from S3 → profile (profile.schema.json)
services/indexer/   Lambda: processed/ → index/vacancies.jsonl with embeddings (daily)
services/api/       Lambdas: matcher (profile → top 50 + salary → matches/) and the HTTP API (uploads, job status)
ml/salary/          model training on the DOU salary survey, SageMaker
web/                React + TypeScript, sliders
eval/               hand-labelled 20–30 vacancies and a script comparing them with the LLM parse
docs/tasks/         briefs the steps were built from; ui-reference.md has the palette and UI patterns
```

## Steps

| Step | What | Status |
|---|---|---|
| 0 | contracts | done |
| 1 | scraper + vacancy parsing + eval | code and tests done; not deployed; eval labels kept out of git |
| 2 | CV parsing | code and tests done; not deployed |
| 3 | matching and API (indexer, matcher, function URL API, SageMaker packaging) | code and tests done; not deployed; SageMaker endpoint off by default |
| 4 | frontend: upload, results, sliders | done on the mock API; HTTP client is a stub |
| 5 | salary model | trained and evaluated locally |
| 6 | hints | ranked one-step hints in the frontend; the LLM "explain" button is not started |

## Data

- Vacancies: jobs.dou.ua, AI/ML category.
- Salaries: open DOU salary survey, github.com/devua/csv, `salaries/2026_june_raw.csv` (14,361 responses).

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r services/parser/requirements.txt -r contracts/requirements.txt pytest

python contracts/check.py
(cd services/scraper && python -m pytest -q && python -m scraper --out ../../data --limit 5)
(cd services/parser && python -m pytest -q && python -m parser --data ../../data --limit 1 --dry-run)
```

`python -m parser` without `--dry-run` calls Claude on Bedrock and needs AWS credentials.

## Static demo

```bash
python scripts/build_static_data.py --data data --model-dir ml/salary/model --out web/public/data --public
cd web && npm ci && npm run build:static   # web/dist, deploy as a static site
```

`--public` anonymises the vacancies (`scripts/public_data.py`). `web/public/data/` is not committed.
