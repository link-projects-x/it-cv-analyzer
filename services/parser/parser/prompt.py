"""System prompt and output schema for the vacancy-parsing LLM call.

The output schema covers only the fields the LLM fills. id, url, title, company,
location and parse metadata are added in assemble.py.

Structured outputs accept a subset of JSON Schema: no minimum/maximum, no
minLength/maxLength, no oneOf (use anyOf), additionalProperties must be false on
every object. Constraints dropped here are enforced afterwards by validating the
assembled document against contracts/vacancy.schema.json.
"""

from __future__ import annotations

from functools import cache

from . import contracts

PROMPT_VERSION = "vacancy-v1"


@cache
def output_schema() -> dict:
    defs = contracts.common_defs()
    skill_enum = sorted(contracts.skill_ids())
    nullable_str = {"type": ["string", "null"]}

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["seniority", "role_type", "requirements", "experience", "english", "salary", "domains", "unmapped"],
        "properties": {
            "seniority": {"enum": defs["seniority"]["enum"]},
            "role_type": {"enum": defs["roleType"]["enum"]},
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["any_of", "min_level", "min_years", "required", "evidence"],
                    "properties": {
                        "any_of": {"type": "array", "items": {"enum": skill_enum}},
                        "min_level": {"enum": [1, 2, 3]},
                        "min_years": {"type": ["number", "null"]},
                        "required": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                },
            },
            "experience": {
                "type": "object",
                "additionalProperties": False,
                "required": ["min_years", "max_years"],
                "properties": {
                    "min_years": {"type": ["number", "null"]},
                    "max_years": {"type": ["number", "null"]},
                },
            },
            "english": {
                "type": "object",
                "additionalProperties": False,
                "required": ["min_level", "evidence"],
                "properties": {
                    "min_level": {"anyOf": [{"enum": defs["cefr"]["enum"]}, {"type": "null"}]},
                    "evidence": nullable_str,
                },
            },
            "salary": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["from", "to", "currency", "period"],
                        "properties": {
                            "from": {"type": ["number", "null"]},
                            "to": {"type": ["number", "null"]},
                            "currency": {"enum": ["USD", "EUR", "UAH"]},
                            "period": {"enum": ["month", "year", "hour"]},
                        },
                    },
                ]
            },
            "domains": {"type": "array", "items": {"enum": defs["domain"]["enum"]}},
            "unmapped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "required"],
                    "properties": {"text": {"type": "string"}, "required": {"type": "boolean"}},
                },
            },
        },
    }


@cache
def system_prompt() -> str:
    vocab_lines = []
    for s in contracts.skills()["skills"]:
        parent = f" (child of {s['parent']})" if s.get("parent") else ""
        vocab_lines.append(f"- {s['id']}: {s['name']}{parent}; aliases: {', '.join(s['aliases'])}")
    vocabulary = "\n".join(vocab_lines)

    return f"""You extract structured requirements from IT job vacancies posted on DOU (jobs.dou.ua).
Vacancies are written in English, Ukrainian or Russian. Return JSON that matches the provided schema.

## Skills
Use only skill IDs from the vocabulary below. Match by meaning, not only by alias.
Put a skill that is clearly required but missing from the vocabulary into `unmapped` with its original name.
Do not put soft skills, degrees or domain knowledge into `unmapped`.
Prefer the most specific ID the text supports: "Amazon Bedrock" -> aws-bedrock, "AWS" alone -> aws.

Vocabulary:
{vocabulary}

## Requirements
- One item per requirement. When the vacancy offers alternatives ("AWS, Azure or GCP", "PyTorch or TensorFlow"),
  put them into one item's `any_of`. A single skill -> `any_of` with one ID.
- `required`: false if the item is under "nice to have", "will be a plus", "буде перевагою", "бажано", "плюсом";
  true otherwise.
- `min_level`:
  1 - familiarity, understanding, basic knowledge, знання, розуміння;
  2 - experience with, hands-on, worked with, досвід роботи з;
  3 - production / commercial experience, "N+ years of X", deep expertise, strong.
- `min_years`: years the vacancy asks for THIS skill, only when the text ties a number to it
  ("3+ years with React" -> 3, "2-4 years of Go" -> 2, "від 2 років досвіду з Python" -> 2). A years figure for the
  role as a whole ("5+ years of commercial experience") goes to `experience`, not here. Otherwise null.
- `evidence`: the shortest quote from the vacancy (max ~200 characters) that supports the item. Copy it, do not paraphrase.
- Skip skills mentioned only when describing the company or product, not as a requirement of the candidate.

## Experience
Total years required for the role. "3+ years" -> min 3, max null. "3-5 years" -> min 3, max 5.
Not stated -> both null. If several numbers are given for different skills, use the one for overall experience.

## English
Map to CEFR: Elementary -> A1, Pre-Intermediate -> A2, Intermediate -> B1, Upper-Intermediate / B2+ -> B2,
Advanced / Fluent -> C1, Native / Proficient -> C2. Not stated -> null for both fields.
When `min_level` is set, `evidence` is the quote it comes from; without a quote, set both to null.

## Seniority and role
`seniority` from the title first, then the text; "Strong Junior" -> junior, "Middle+" -> middle, "Staff"/"Principal" -> principal.
Not inferable -> unknown.
`role_type`: ai-engineer (LLM, GenAI, agents, AI automation), ml-engineer (training classical/deep models),
cv-engineer (computer vision), data-scientist, mlops (ML platform, model serving infra), other (non-engineering roles,
QA, sales, management, data engineering, design).

## Salary
Only if the vacancy states a number. Monthly unless the text says otherwise. A salary line given separately from the text
is authoritative. Not stated -> null. Never return a salary object without numbers: no `from` and no `to` -> `salary` is null.

## Domains
Project domains from the enum when the vacancy names the product area. Empty list if unclear.
"""


def user_message(title: str, company: str, salary_text: str | None, text: str) -> str:
    salary_line = f"Salary line: {salary_text}\n" if salary_text else ""
    return f"Title: {title}\nCompany: {company}\n{salary_line}\nVacancy text:\n{text}"
