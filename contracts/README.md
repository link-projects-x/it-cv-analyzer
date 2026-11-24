# Contracts v1.0

Shared data formats for every part of the project. Change them only through a PR reviewed by all four of us.

| File | Written by | Read by |
|---|---|---|
| `skills.json` | by hand | vacancy parser, CV parser, frontend |
| `vacancy.schema.json` | `services/parser` | `services/api`, frontend |
| `profile.schema.json` | `services/cv` | `services/api`, `ml/salary`, frontend |
| `match-response.schema.json` | `services/api` | frontend |
| `common.schema.json` | — | the other schemas via `$ref` |

Check: `pip install -r contracts/requirements.txt && python contracts/check.py`.
Without the `[format-nongpl]` extra, `date-time` and `uri` fields are not validated.

## Decisions

**Skills.** Only IDs from `skills.json`. A skill missing from the vocabulary goes to `unmapped` and does not count in matching. Review `unmapped` weekly and extend the vocabulary.

**Levels 0–3** (same scale for vacancies and CVs):

| Level | CV | Wording in a vacancy |
|---|---|---|
| 0 | no experience | — |
| 1 | course, tutorial | familiarity, understanding, знання |
| 2 | pet project, non-production | experience with, hands-on, досвід |
| 3 | production | production, commercial, N years in X |

**Hierarchy.** A skill may have a `parent` (`aws-bedrock` → `aws`). The parent's level in a profile is the maximum of its own level and its children's levels. A vacancy requiring `aws` at level 2 is satisfied by a candidate with `aws-bedrock` at level 2.

**Alternatives.** "AWS, Azure or GCP" → one requirement with `any_of: ["aws", "azure", "gcp"]`. The best of the options counts.

**Required vs optional.** `required: false` when the skill is listed under nice to have / will be a plus / буде перевагою.

**Experience.** "3+ years" → `min_years: 3, max_years: null`. "3–5 years" → `3, 5`. Not stated → both `null`.

**English** in CEFR: Pre-Intermediate → A2, Intermediate → B1, Upper-Intermediate and B2+ → B2, Advanced and Fluent → C1, Native → C2. `ml/salary` maps it back to the DOU survey values (Elementary … Advanced).

**Salary model inputs** (`profile.salary_features`) — values copied 1:1 from the DOU survey columns (June 2026), in Ukrainian as in the CSV. `null` means the CV has no data.

**Salary in the API response** — USD per month. Assumption: the survey column «ЗАРПЛАТА СУМАРНИЙ ДОХІД в ІТ» holds monthly income in USD; the file does not state units.

**evidence.** A short quote from the source text for every value produced by the LLM. Used in eval to see what the model based the value on.

**Relations (vacancy).** Cross-field rules JSON Schema cannot express. `services/parser/parser/relations.py` checks
them after schema validation; a broken one sends the vacancy to `failed/` with the relation's name.

| Relation | Rule |
|---|---|
| `rel.experience_range` | `max_years ≥ min_years` when both are set |
| `rel.salary_range` | a salary object has `from` or `to`; `to ≥ from` when both are set |
| `rel.requirement_evidence` | every requirement has non-empty `evidence` |
| `rel.english_evidence` | `english.evidence` is non-empty when `english.min_level` is set |

**Relations (profile).** Checked by `services/cv/cv/relations.py`; a broken one sends the CV to `failed-cv/`.

| Relation | Rule |
|---|---|
| `rel.skill_evidence` | a skill at level 2 or 3 has non-empty `evidence` |
| `rel.unique_skills` | a skill ID appears once in `skills` |

**Relations (match response).**

| Relation | Rule |
|---|---|
| `rel.grid_matches_point` | at the profile's own position every grid row reads `salary.point` (±0.5): `english`, `experience_years` (rounded as below), `company_type` when set, `domains` when the profile has exactly one |

`check.py` runs the profile and match-response relations on the examples.

**Salary grid.**
- Experience key: the nearest whole year, half rounds up (`floor(x + 0.5)`), clamped to 0–15. The experience slider
  opens at that position, and `salary.point` is computed at that key, not at the raw value: the model gives 2.5 years
  the same estimate as 2, so a raw-value point would differ from `grid.experience_years["3"]`. Experience above 15
  years is estimated as 15.
- C1 and C2 both map to the survey's single "Advanced" level, so `grid.english.C1 == grid.english.C2`. The frontend shows
  both; moving between them does not change the estimate.
- When the model fills a missing profile field, the filled field names are appended to `model_version`
  (`…+imputed:company_size`).

**schema_version.** Currently `"1.0"`. An incompatible format change → `"2.0"` and all consumers updated in the same PR.

## Coverage formula (v2, skill years)

Computed by the frontend on every slider move. Skill sliders hold **years with the skill** (0–10, step 0.5).
Coverage of one vacancy:

```
need(req)   = req.min_years                                     — when the vacancy ties years to this skill
            = base * inherit_factor                             — otherwise
base        = vacancy.experience.min_years                      — when stated and > 0
            = grade_years[vacancy.seniority]                    — else, when the grade is known
            = default_years                                     — else
score(req)  = max over skill in req.any_of: 0 if years(skill) = 0, else 1 if need = 0, else min(1, years / need)
weight(req) = 2 if req.required else 1

skills_part = Σ weight(req) * score(req)
skills_max  = Σ weight(req)

exp_part = 2 * min(1, experience_years / min_years)      — only if min_years is not null
eng_part = 1 * (1 if english ≥ min_level else index(english) / index(min_level))
                                                          — only if min_level is not null
                                                          — index: A1=1 … C2=6

coverage = (skills_part + exp_part + eng_part) / (skills_max + 2 + 1)   — drop the parts that were skipped
fits     = coverage ≥ 0.8
```

Where the numbers come from (`coverage.json → skill_years`):

- `grade_years`: 25th percentile of total experience by title in the DOU salary survey, June 2026, 12,630 rows after
  the `ml/salary` filters: Intern 0.1, Junior 1, Middle 3, Senior 5, Lead 5, Principal 8.
- `default_years` = 1, the Junior value: a vacancy that states neither years nor grade.
- `inherit_factor`: years asked per skill divided by the vacancy's total years, median over parsed vacancies that
  state both (see the value and its count in `coverage.json → skill_years._source`).
- Assumption: a skill without its own years needs the role's years times `inherit_factor`. Vacancies state years
  for a specific skill in 34.7% of cases (630 of 1,813, 2026-11-21); the rest inherit.

v1 used levels 0–3 (tried / pet project / production) from the vacancy wording. It is replaced because 2 and 5 years
of production experience both read as level 3, and the CV parser had no way to tell a pet project from production.

`years(skill)` is the profile value after applying the hierarchy (a parent takes the max of its children); a skill
missing from the profile → 0.

`min_years` of `null` or `0` skips the experience part. A profile without English scores index 0.
A vacancy with no requirements, no `min_years` and no English has `coverage = null` (nothing to score) and `fits = false`.

`similarity` from the API is not part of the formula; it only orders the selection of 50 vacancies.

`fits` compares with a tolerance: `coverage ≥ fits_threshold − 1e-12`, so 0.8 computed as 0.7999999999999999 still fits.

Slider visibility is decided once, on the opening profile: a skill gets a slider when moving it from 0 to 3 changes the
coverage of at least one loaded vacancy. Sliders do not appear or disappear while the user moves others.

Weights, threshold and slider ranges live in `coverage.json`. The values (2/1, 2 for experience, 1 for English,
threshold 0.8) are starting values from the mockup, not fitted to data.

**Reference and parity.** `coverage_reference.py` is the reference implementation. It writes
`fixtures/coverage-golden.json` (inputs and expected `coverage` / `fits` for 15 cases). Every other implementation,
the TypeScript one in `web/` included, must reproduce the golden file within `1e-9`. `check.py` fails when the golden file
no longer matches the reference, so a change to `coverage.json` or the formula needs
`python contracts/coverage_reference.py --write-golden` in the same PR.

## Examples

`examples/*.example.json` are synthetic: company `Example Co`, IDs 100001–100002, numbers in `salary.grid` are illustrative. The frontend can use `match-response.example.json` until the API exists.
