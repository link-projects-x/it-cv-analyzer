"""Combine page fields and LLM output into a contract-valid vacancy document."""

from __future__ import annotations

from datetime import datetime, timezone

from . import contracts
from .extract import PageFields
from .prompt import PROMPT_VERSION
from .relations import relation_errors

EVIDENCE_MAX = 300  # contracts/common.schema.json -> evidence.maxLength


class InvalidVacancy(ValueError):
    def __init__(self, errors: list[str], doc: dict):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.doc = doc


def assemble(
    vacancy_id: str,
    url: str,
    scraped_at: str,
    page: PageFields,
    llm_data: dict,
    model: str,
    parsed_at: datetime | None = None,
) -> dict:
    requirements, unknown = _clean_requirements(llm_data.get("requirements", []))
    unmapped = list(llm_data.get("unmapped", [])) + unknown

    english = dict(llm_data["english"])
    if english.get("evidence"):
        english["evidence"] = english["evidence"][:EVIDENCE_MAX]

    doc = {
        "schema_version": "1.0",
        "id": vacancy_id,
        "source": "dou",
        "url": url,
        "title": page.title,
        "company": page.company,
        "scraped_at": scraped_at,
        "seniority": llm_data["seniority"],
        "role_type": llm_data["role_type"],
        "requirements": requirements,
        "experience": llm_data["experience"],
        "english": english,
        "salary": llm_data["salary"],
        "domains": sorted(set(llm_data.get("domains", []))),
        "location": {"remote": page.remote, "cities": page.cities},
        "unmapped": _dedupe_unmapped(unmapped),
        "parse": {
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "parsed_at": (parsed_at or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        },
    }

    errors = contracts.validation_errors("vacancy", doc) or relation_errors(doc)
    if errors:
        raise InvalidVacancy(errors, doc)
    return doc


def _clean_requirements(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop unknown skill IDs (structured outputs should prevent them; this covers a model that ignores the enum),
    dedupe any_of, drop items left empty, cut evidence to the contract limit."""
    known = contracts.skill_ids()
    cleaned, unknown = [], []
    for item in items:
        ids = list(dict.fromkeys(item.get("any_of", [])))
        bad = [i for i in ids if i not in known]
        unknown += [{"text": i, "required": bool(item.get("required", True))} for i in bad]
        ids = [i for i in ids if i in known]
        if not ids:
            continue
        cleaned.append(
            {
                "any_of": ids,
                "min_level": item["min_level"],
                "min_years": item.get("min_years"),
                "required": item["required"],
                "evidence": (item.get("evidence") or "")[:EVIDENCE_MAX],
            }
        )
    return cleaned, unknown


def _dedupe_unmapped(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        text = item["text"].strip()[:120]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append({"text": text, "required": bool(item.get("required", True))})
    return out
