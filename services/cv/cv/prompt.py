"""System prompt and output schema for the CV-parsing LLM call.

The output schema covers only the fields the LLM fills. schema_version, id,
created_at and parse metadata are added in assemble.py.

Structured outputs accept a subset of JSON Schema: no minimum/maximum, no
minLength/maxLength, no oneOf (use anyOf), additionalProperties must be false on
every object. Constraints dropped here are enforced afterwards by validating the
assembled document against contracts/profile.schema.json.
"""

from __future__ import annotations

from functools import cache

from . import contracts

PROMPT_VERSION = "profile-v1"

SALARY_FEATURES = ("category", "title", "primary_language", "company_type", "company_size", "domains", "residence")


def salary_feature_values(name: str) -> list[str]:
    """Non-null enum values of profile.salary_features.<name>, in contract order."""
    prop = contracts.profile_schema()["properties"]["salary_features"]["properties"][name]
    return [v for v in prop["enum"] if v is not None]


def _nullable_enum(values: list) -> dict:
    return {"anyOf": [{"enum": values}, {"type": "null"}]}


@cache
def output_schema() -> dict:
    defs = contracts.common_defs()
    skill_enum = sorted(contracts.skill_ids())

    salary_props = {name: _nullable_enum(salary_feature_values(name)) for name in SALARY_FEATURES if name != "domains"}
    salary_props["domains"] = {"type": "array", "items": {"enum": defs["domain"]["enum"]}}

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["skills", "experience_years", "english", "seniority", "role_type", "salary_features", "unmapped"],
        "properties": {
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "level", "evidence"],
                    "properties": {
                        "id": {"enum": skill_enum},
                        "level": {"enum": [1, 2, 3]},
                        "evidence": {"type": ["string", "null"]},
                    },
                },
            },
            "experience_years": {"type": "number"},
            "english": _nullable_enum(defs["cefr"]["enum"]),
            "seniority": {"enum": defs["seniority"]["enum"]},
            "role_type": {"enum": defs["roleType"]["enum"]},
            "salary_features": {
                "type": "object",
                "additionalProperties": False,
                "required": list(SALARY_FEATURES),
                "properties": {name: salary_props[name] for name in SALARY_FEATURES},
            },
            "unmapped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text"],
                    "properties": {"text": {"type": "string"}},
                },
            },
        },
    }


def _enum_lines(name: str) -> str:
    return "; ".join(salary_feature_values(name))


@cache
def system_prompt() -> str:
    vocab_lines = []
    for s in contracts.skills()["skills"]:
        parent = f" (child of {s['parent']})" if s.get("parent") else ""
        vocab_lines.append(f"- {s['id']}: {s['name']}{parent}; aliases: {', '.join(s['aliases'])}")
    vocabulary = "\n".join(vocab_lines)

    return f"""You extract a structured candidate profile from a CV (resume) of an IT specialist.
CVs are written in English, Ukrainian or Russian. Return JSON that matches the provided schema.

## Skills
Use only skill IDs from the vocabulary below. Match by meaning, not only by alias.
Put a technical skill that the CV clearly claims but that is missing from the vocabulary into `unmapped` with its
original name. Do not put soft skills, degrees, spoken languages or domain knowledge into `unmapped`.
Prefer the most specific ID the text supports: "Amazon Bedrock" -> aws-bedrock, "AWS" alone -> aws.
List each skill ID once, with the highest level the CV supports.

Vocabulary:
{vocabulary}

## Levels
- 3: used in production or commercial work: a job, a paid client project, a product with real users.
- 2: pet project, hackathon, thesis, open-source side project, any non-production use.
- 1: course, tutorial, certificate, study task, or the skill is only listed without any context.
Do not give level 3 without a job or commercial project that uses the skill. Skip skills the CV does not mention.

## Evidence
`evidence`: the shortest quote from the CV (max ~200 characters) that supports the skill and its level. Copy it, do not
paraphrase. Required for levels 2 and 3; null is allowed only for level 1. Never quote names, emails, phone numbers,
addresses or links.

## Experience
`experience_years`: years of work in the candidate's current IT specialty, summed over jobs, overlapping periods counted
once. Use the CV's own total ("5+ years") when stated; otherwise compute from job dates. Exclude non-IT jobs.
Round to one decimal. No work experience -> 0.

## English
Map to CEFR: Elementary -> A1, Pre-Intermediate -> A2, Intermediate -> B1, Upper-Intermediate / B2+ -> B2,
Advanced / Fluent -> C1, Native / Proficient -> C2. Not stated -> null.

## Seniority and role
`seniority` from the current or most recent title first, then from experience; "Strong Junior" -> junior,
"Middle+" -> middle, "Staff"/"Principal" -> principal. Not inferable -> unknown.
`role_type`: ai-engineer (LLM, GenAI, agents, AI automation), ml-engineer (training classical/deep models),
cv-engineer (computer vision), data-scientist, mlops (ML platform, model serving infra), other (everything else,
including software engineering, QA, data engineering, management).

## Salary features
Values for a salary model trained on the DOU salary survey. Pick a value only when the CV supports it; otherwise null.
Copy values exactly as listed.
- category: {_enum_lines("category")}
- title (current or most recent position level): {_enum_lines("title")}
- primary_language (the main programming language of the current job): {_enum_lines("primary_language")}
- company_type (current or most recent employer): {_enum_lines("company_type")}
- company_size (specialists in Ukraine at the current employer): {_enum_lines("company_size")}
- residence: {_enum_lines("residence")}
- domains: product areas of the candidate's projects, from the enum; empty list if unclear.
"""


def user_message(text: str) -> str:
    return f"CV text:\n{text}"
