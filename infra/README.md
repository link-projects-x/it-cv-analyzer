# Infrastructure (steps 1-3)

```
EventBridge (daily, 05:00 UTC)
  → Lambda scraper ──► S3 raw/dou-<id>.html  (skips IDs already stored)
                          │ ObjectCreated raw/*.html
                          ▼
                     Lambda parser ──► Claude Haiku 5.5 (Bedrock Mantle)
                          ├──► S3 processed/dou-<id>.json   contracts/vacancy.schema.json
                          └──► S3 failed/dou-<id>.json      reason + partial doc

S3 cv/<uuid>.<pdf|docx|txt>  (step 2)
                          │ ObjectCreated cv/*.pdf, cv/*.docx, cv/*.txt
                          ▼
                     Lambda cv ──► Claude Haiku 5.5 (Bedrock Mantle)
                          ├──► S3 profiles/<uuid>.json      contracts/profile.schema.json; cv/<uuid>.* deleted
                          └──► S3 failed-cv/<uuid>.json     reason + partial doc; cv/<uuid>.* kept

Browser ── POST /uploads ──► Lambda api (function URL) ──► jobs/<uuid>.json + presigned POST for cv/<uuid>.<ext>
Browser ── POST (the CV) ──► S3 cv/<uuid>.<ext> ──► Lambda cv (above) ──► profiles/<uuid>.json   (step 3)
                          │ ObjectCreated profiles/*.json
                          ▼
                     Lambda matcher ──► Bedrock embedding (profile) + cosine over index/vacancies.jsonl
                          │             salary: SageMaker serverless endpoint, or a fake block when disabled
                          ├──► S3 matches/<uuid>.json       contracts/match-response.schema.json
                          └──► S3 failed-match/<uuid>.json  reason + doc
Browser ── GET /jobs/<uuid> ──► Lambda api ──► state from which objects exist; result inlined when done

EventBridge (daily, 06:00 UTC) → Lambda indexer ──► S3 index/vacancies.jsonl  (re-embeds changed vacancies only)
```

The HTTP API is a Lambda function URL, not API Gateway: it is one resource plus two permissions, its CORS
configuration answers the browser's preflight, and the API has two routes that the handler dispatches itself.
API Gateway would add throttling and custom domains; neither is used here. A function URL has no throttling of its own:
an abusive client is limited only by Lambda concurrency and the budget alarm.

## Prerequisites

- Terraform >= 1.6, AWS CLI v2, Python 3 with pip, `zip`.
- AWS credentials for an IAM user or SSO role, not the root user (`aws sts get-caller-identity` works).
- Claude models enabled for the account in the Bedrock console for `var.region`. Anthropic models may ask for a one-time
  use-case form; until access is granted the parser fails with an access error and writes nothing to `processed/`.
- The embedding model in `var.embedding_model_id` enabled in the same region. The default `cohere.embed-v4:0` is an
  assumption taken from the Bedrock user guide page "Cohere Embed v4"; check the ID in the Bedrock console. Some models
  are callable only through an inference profile (`us.cohere.embed-v4:0`); the IAM policy accepts either form.

## Deploy

Access codes first: the API refuses every request until at least one code is configured. One code per person, so one
can be revoked alone. Only the SHA-256 hash goes to AWS; the code is shown once.

```bash
python scripts/new_access_code.py alice      # prints the code and the tfvars line
# infra/terraform.tfvars (gitignored):
#   access_code_hashes = { "alice" = "<sha256>", "bob" = "<sha256>" }
```

```bash
scripts/build_lambdas.sh
cd infra
terraform init
terraform apply -var budget_email=you@example.com -var web_origin=https://<web app origin>
terraform output -raw api_url          # VITE_API_URL for the web app
```

## API protection

The function URL itself is public (`auth NONE`); the function decides who gets in (`services/api/api/access.py`):

- `Authorization: Bearer <code>` on every request; no or wrong code -> 401. No codes configured -> everything 401.
- `daily_uploads_per_code` (default 10) and `daily_uploads_total` (default 40) uploads per UTC day -> 429 above them.
  Counted from `quota/<day>/<label>/` markers; parallel requests can overshoot by their number.
- A job is visible only with the code that created it.
- CORS allows only `web_origin`. CORS does not stop scripts, which is why the code check exists.
- `api_reserved_concurrency`, `cv_reserved_concurrency`, `matcher_reserved_concurrency` cap parallel runs once the
  account's Lambda concurrency limit allows reservations (a new account with a limit of 10 cannot reserve any).
- The monthly budget alert (`budget_limit_usd`) is the last line.

Revoke a code: remove its line from `access_code_hashes` and apply.

The salary endpoint is off by default (`enable_salary_endpoint = false`): the matcher then writes a fixed-formula
salary block with `model_version: "fake-disabled"`, and no SageMaker resource exists. To turn it on, train with the
pinned versions and package the model first (`ml/salary/README.md` → SageMaker), then apply with the flag:

```bash
python ml/salary/train.py && ml/salary/package.sh          # Python 3.12 venv -> dist/model.tar.gz
terraform apply -var budget_email=you@example.com -var enable_salary_endpoint=true
```

`salary_image_uri` defaults to the us-east-1 image; another region needs that region's registry account.

The indexer runs daily after the scrape. Until its first run `index/vacancies.jsonl` does not exist and every match
fails with `IndexUnusable`; to build it right after the first parse:
`aws lambda invoke --function-name dou-cv-analyzer-indexer out.json && cat out.json`.

The budget sends a confirmation email to `budget_email`; alerts arrive only after it is confirmed.

## First run

The first scrape downloads every vacancy in the category, and each new raw object triggers one parser invocation.
To check the chain on a few vacancies first, set `scraper_max_new` to 3, apply, invoke, then raise it back:

```bash
terraform apply -var budget_email=you@example.com -var scraper_max_new=3
aws lambda invoke --function-name dou-cv-analyzer-scraper out.json && cat out.json
aws s3 ls s3://$(terraform output -raw bucket)/processed/
aws logs tail /aws/lambda/dou-cv-analyzer-parser --since 10m
```

## Failure handling

- Parsing errors the code expects (bad page, LLM refusal or cut output, contract violation) → `failed/dou-<id>.json`.
  To retry, delete the raw object and let the next scrape download it again, or run the parser locally with `--ids`.
- CV parsing errors the code expects (no text layer, unreadable file, LLM refusal, contract violation) →
  `failed-cv/<uuid>.json`; the CV stays in `cv/`. Logs carry IDs, sizes, token counts and error types, never CV text.
- Matching errors the code expects (no index, index from another embedding model, bad embedding or salary response,
  contract or relation violation) → `failed-match/<uuid>.json`; `GET /jobs/<uuid>` reports `failed`.
  Logs carry IDs, counts and error codes, never profile evidence or embedding text.
- Unexpected errors (throttling, network) raise; S3 → Lambda is an async invocation, so Lambda retries it twice.
  The `parser-errors` and `matcher-errors` alarms fire at 5 errors per hour.
- An upload that does not reach `cv/` within 15 minutes of `POST /uploads` is reported as `failed`.

## Retention

`cv/`, `failed-cv/`, `matches/`, `failed-match/` and `jobs/` expire after `upload_retention_days` (7). `profiles/` has
no expiry rule. With `cv_delete_after_parse` the CV is deleted right after a successful parse.

## Not validated

Terraform is not installed where this was written: no `terraform validate` or `plan` has been run on these files.
They were parsed with python-hcl2 and every `var.`, `local.`, `data.` and resource reference was checked to exist.

## Cleanup

`terraform destroy` fails while the bucket has objects. Empty it first: `aws s3 rm s3://<bucket> --recursive`.
