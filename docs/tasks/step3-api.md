# Step 3 — matching backend and HTTP API

Branch `feat/step3-api`. Work in `services/api/`, `services/indexer/`, `ml/salary/` (packaging only), `scripts/` and
`infra/`. Read `docs/tasks/README.md`, `contracts/README.md`, `infra/README.md`, and the existing services
(`services/parser`, `services/cv`) and `ml/salary` first; follow their structure, naming and test style.

## Flow

```
Browser ── POST /uploads {filename, size, content_type} ──► Lambda api ──► {job_id, upload: {url, fields}}  (S3 presigned POST to cv/<job_id>.<ext>)
Browser ── S3 POST (the CV) ──► cv/<job_id>.<ext> ──► Lambda cv (exists) ──► profiles/<job_id>.json
                                                                              │ ObjectCreated profiles/*.json
                                                                              ▼
                                                                   Lambda matcher
                                                                     ├─ embed the profile (Bedrock)
                                                                     ├─ top 50 by cosine over index/vacancies.jsonl
                                                                     ├─ salary: SageMaker endpoint (or fake when disabled)
                                                                     └─► matches/<job_id>.json  (match-response.schema.json)
Browser ── GET /jobs/{job_id} ──► Lambda api ──► {state: uploading|parsing|matching|done|failed, result?, error?}

EventBridge (daily, after the scrape) ──► Lambda indexer ──► index/vacancies.jsonl  (processed/*.json + embeddings)
```

## Pieces

- `services/indexer/`: reads every `processed/*.json`, embeds the vacancy text that matters for matching (title +
  requirements' skill names + evidence; keep the function that builds it shared in spirit with the profile side),
  writes `index/vacancies.jsonl` (one line: vacancy doc + `embedding`). Re-embeds only vacancies whose `parse.parsed_at`
  changed since the last index (read the previous index). Embedding model ID is a Terraform variable; default
  `cohere.embed-v4:0` is an **assumption** — say in the README that the ID must be checked in the Bedrock console.
- `services/api/`:
  - `matcher.py` + handler on `profiles/*.json`: load index, embed profile (the profile's skills with levels and
    evidence, seniority, role type), cosine top 50, call salary, assemble the match response, validate against
    `match-response.schema.json` and run the relations from `contracts/README.md` (copy the small functions; do not
    import across services), write `matches/<job_id>.json` or `failed-match/<job_id>.json`.
  - `http.py` + handler for a Lambda function URL (or API Gateway HTTP API; pick one, say why): `POST /uploads`
    validates extension (`.pdf .docx .txt`) and size (≤ 5 MB), returns a presigned POST limited to that key, size and
    content type, expiring in 10 minutes; `GET /jobs/{id}` derives state from which S3 objects exist
    (`cv/` → parsing, `profiles/` → matching, `matches/` → done with the result inlined, `failed-cv/` or
    `failed-match/` → failed with a short error, nothing → uploading for up to 15 minutes after creation, then failed).
    CORS for the web origin as a variable. Job IDs are UUID v4; reject anything else.
- Salary: `ml/salary/package.sh` builds `model.tar.gz` (model + `inference.py` + `features.py` + `requirements.txt`) for
  the SageMaker scikit-learn container. The salary agent noted the container's scikit-learn version may not match the
  pinned 1.9.1; find out from AWS docs which framework versions are available, choose one, and either re-pin and confirm
  the model trains and tests pass with that version, or document exactly why not. Terraform: SageMaker model +
  **serverless** endpoint config + endpoint behind `var.enable_salary_endpoint` (default `false`). When disabled the
  matcher uses a deterministic fake salary block (clearly marked `model_version: "fake-disabled"`) so the chain works
  end to end without SageMaker costs.
- Infra: Lambdas (python3.13 arm64) for indexer, matcher, api; function URL or HTTP API; S3 notification for
  `profiles/*.json` added to the existing single `aws_s3_bucket_notification`; EventBridge rule for the indexer;
  least-privilege IAM (`bedrock:InvokeModel` on the embedding model ARN, `sagemaker:InvokeEndpoint` on the endpoint,
  S3 per prefix); log groups; an S3 lifecycle rule expiring `cv/`, `failed-cv/` and `matches/` after 7 days.
  Extend `scripts/build_lambdas.sh`. Terraform is not installed here: say so; do not claim validation.
- Privacy: no CV text, profile evidence or embeddings in logs.

## Tests

Fakes for S3 (or a local store like the other services), Bedrock embeddings (deterministic vectors) and the salary
endpoint. Cover: top-50 ordering by cosine, the assembled response passing schema + relations, `rel.grid_matches_point`
with the fake salary, every job state transition in `GET /jobs/{id}` including the 15-minute timeout, upload validation
(extension, size, bad job ID), indexer re-embedding only changed vacancies, and that logs contain no profile evidence.

## Done when

`pytest` passes in every service directory and in `ml/salary`, `python contracts/check.py` passes,
`scripts/build_lambdas.sh` builds all zips, and the report lists verified and not-verified items, including anything
about SageMaker container versions that could not be confirmed.
