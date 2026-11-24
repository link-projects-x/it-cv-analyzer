# Step 2 — CV parsing

Branch `feat/step2-cv`. Work in `services/cv/`, `scripts/build_lambdas.sh` and `infra/`. Read `docs/tasks/README.md`,
`contracts/README.md`, and the existing vacancy parser in `services/parser/` first: follow its structure, naming and
test style.

## Goal

A Lambda that turns an uploaded CV into a profile document valid against `contracts/profile.schema.json`, the same way
`services/parser` turns a vacancy page into `vacancy.schema.json`.

```
S3 cv/<uuid>.<pdf|docx|txt>  (ObjectCreated)
  → Lambda cv: text extraction → Claude Haiku 5.5 (structured outputs) → assemble → schema + relations
  → S3 profiles/<uuid>.json, or failed-cv/<uuid>.json with the reason
```

## Pieces

- `services/cv/cv/extract.py` — text from PDF (`pypdf`), DOCX (`python-docx`) and TXT. Reject a file with no
  extractable text (scanned PDF) with a clear error; no OCR in this step. Cap text length like the vacancy parser does.
- `prompt.py` — system prompt and output schema built from the contracts (skill IDs as an enum, CEFR, seniority,
  role type, every `salary_features` enum from `profile.schema.json`). Same structured-outputs limits as the vacancy
  parser: no `minimum`/`maximum`/`minLength`/`maxLength`, `anyOf` instead of `oneOf`, `additionalProperties: false`
  everywhere. Level rules from `contracts/README.md -> Levels`: 3 only for production / commercial use, 2 for pet
  projects, 1 for courses. `evidence` is a short quote from the CV.
- `llm.py` — reuse the vacancy parser's approach (`AnthropicBedrockMantle`, `output_config.format`, effort, refusal and
  max_tokens handling). Duplicating the small class is fine; do not import across services.
- `assemble.py` — add `schema_version`, `id` (the uuid from the key), `created_at`, `parse`; drop unknown skill IDs into
  `unmapped`; validate against `profile.schema.json`; then relations:
  - `rel.skill_evidence`: a skill at level 2 or 3 has non-null, non-empty evidence;
  - `rel.unique_skills`: a skill ID appears once;
  - `rel.experience_bound`: `experience_years` ≤ 50.
  Add these relations to the PR description as a proposed addition to `contracts/README.md` (do not edit contracts).
- `pipeline.py`, `handler.py`, `__main__.py` (local run over a directory, `--dry-run` without LLM) — as in the vacancy
  parser.

## Privacy

A CV is personal data. Never log CV text or LLM output content; log IDs, sizes, token counts and error types only.
After a successful parse, delete the `cv/<uuid>.*` object (configurable, default on). The profile stays.

## Infra

- `scripts/build_lambdas.sh`: build `dist/cv.zip` like `parser.zip` (contracts copied in).
- `infra/`: Lambda `${var.project}-cv` (python3.13, arm64, timeout 120 s), log group, S3 notification on prefix `cv/`
  (keep the existing `raw/` notification in the same `aws_s3_bucket_notification` resource), IAM limited to
  `cv/*` get+delete, `profiles/*` and `failed-cv/*` put, and `bedrock-mantle:CreateInference` as in the parser role.
  Do not run `terraform apply`. If Terraform is available in the session, run `terraform fmt -check` and
  `terraform validate` (with `-backend=false` init) and report the result; if not, say so.

## Tests

Fixtures are synthetic CVs written for the tests (no real person's data): a TXT, a DOCX generated in the test with
`python-docx`, and a PDF with a text layer (generate one with `reportlab` in a dev dependency, or commit a small
synthetic PDF). Cover extraction for each format, the scanned-PDF rejection, schema/relations failures going to
`failed-cv/`, unknown skill IDs going to `unmapped`, the output schema using only supported keywords, and that no CV
text reaches the logs (capture logs in a test).

## Done when

`pytest services/cv` and `pytest services/parser` pass, `scripts/build_lambdas.sh` builds three zips, and the PR
description lists verified and not-verified items.
