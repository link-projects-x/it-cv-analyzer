"""Cross-field rules a parsed profile must satisfy.

JSON Schema checks each field on its own; these compare fields with each other.
Each relation has a name that appears in the error, so failed-cv/ shows which rule broke.
Proposed for contracts/README.md -> Relations (profile); the vacancy list lives in services/parser/parser/relations.py.

Messages name skill IDs, levels and numbers only, never evidence text: the messages go to the logs.
"""

from __future__ import annotations

from collections import Counter
from typing import Callable

Relation = Callable[[dict], list[str]]

EXPERIENCE_MAX_YEARS = 50


def skill_evidence(doc: dict) -> list[str]:
    return [
        f"skills/{i} ({s['id']}) at level {s['level']} has no evidence"
        for i, s in enumerate(doc["skills"])
        if s["level"] >= 2 and not (s["evidence"] or "").strip()
    ]


def unique_skills(doc: dict) -> list[str]:
    counts = Counter(s["id"] for s in doc["skills"])
    return [f"skill {sid} appears {n} times" for sid, n in sorted(counts.items()) if n > 1]


def experience_bound(doc: dict) -> list[str]:
    years = doc["experience_years"]
    if years > EXPERIENCE_MAX_YEARS:
        return [f"experience_years {years} > {EXPERIENCE_MAX_YEARS}"]
    return []


RELATIONS: dict[str, Relation] = {
    "rel.skill_evidence": skill_evidence,
    "rel.unique_skills": unique_skills,
    "rel.experience_bound": experience_bound,
}


def relation_errors(doc: dict) -> list[str]:
    """Run every relation. Call only on a schema-valid doc: relations index fields the schema guarantees."""
    return [f"{name}: {msg}" for name, rel in RELATIONS.items() for msg in rel(doc)]
