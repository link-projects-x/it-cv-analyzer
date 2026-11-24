"""Combine LLM output and IDs into a contract-valid profile document."""

from __future__ import annotations

from datetime import datetime, timezone

from . import contracts
from .prompt import PROMPT_VERSION
from .relations import relation_errors

EVIDENCE_MAX = 300  # contracts/common.schema.json -> evidence.maxLength
UNMAPPED_TEXT_MAX = 120  # contracts/common.schema.json -> unmapped.items.text.maxLength


class InvalidProfile(ValueError):
    """errors: full messages, written to failed-cv/ (they may quote CV text).
    codes: "<path>: <keyword>" and relation messages, safe to log."""

    def __init__(self, errors: list[str], codes: list[str], doc: dict):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.codes = codes
        self.doc = doc


def assemble(
    profile_id: str,
    llm_data: dict,
    model: str,
    created_at: datetime | None = None,
) -> dict:
    now = (created_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    skills, unknown = _clean_skills(llm_data.get("skills", []))
    salary = dict(llm_data["salary_features"])
    salary["domains"] = sorted(set(salary.get("domains") or []))

    doc = {
        "schema_version": "1.0",
        "id": profile_id,
        "created_at": now,
        "skills": skills,
        "experience_years": llm_data["experience_years"],
        "english": llm_data["english"],
        "seniority": llm_data["seniority"],
        "role_type": llm_data["role_type"],
        "salary_features": salary,
        "unmapped": _dedupe_unmapped(list(llm_data.get("unmapped", [])) + unknown),
        "parse": {"model": model, "prompt_version": PROMPT_VERSION, "parsed_at": now},
    }

    errors = contracts.validation_errors("profile", doc)
    if errors:
        raise InvalidProfile(errors, contracts.validation_codes("profile", doc), doc)
    errors = relation_errors(doc)
    if errors:
        raise InvalidProfile(errors, errors, doc)
    return doc


def _clean_skills(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Move unknown skill IDs to unmapped (structured outputs should prevent them; this covers a model that ignores the
    enum), cut evidence to the contract limit, turn empty evidence into null. Duplicates stay: rel.unique_skills
    reports them."""
    known = contracts.skill_ids()
    cleaned, unknown = [], []
    for item in items:
        if item.get("id") not in known:
            unknown.append({"text": str(item.get("id", ""))})
            continue
        evidence = (item.get("evidence") or "").strip()[:EVIDENCE_MAX] or None
        cleaned.append({"id": item["id"], "level": item["level"], "evidence": evidence})
    return cleaned, unknown


def _dedupe_unmapped(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        text = item["text"].strip()[:UNMAPPED_TEXT_MAX]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append({"text": text})
    return out
