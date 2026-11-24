"""Cross-field rules a parsed vacancy must satisfy.

JSON Schema checks each field on its own; these compare fields with each other.
Each relation has a name that appears in the error, so failed/ shows which rule broke.
The list is documented in contracts/README.md -> Relations.
"""

from __future__ import annotations

from typing import Callable

Relation = Callable[[dict], list[str]]


def experience_range(doc: dict) -> list[str]:
    lo, hi = doc["experience"]["min_years"], doc["experience"]["max_years"]
    if lo is not None and hi is not None and hi < lo:
        return [f"max_years {hi} < min_years {lo}"]
    return []


def salary_range(doc: dict) -> list[str]:
    s = doc["salary"]
    if s is None:
        return []
    if s["from"] is None and s["to"] is None:
        return ["salary object with neither from nor to; use null when the vacancy states no salary"]
    if s["from"] is not None and s["to"] is not None and s["to"] < s["from"]:
        return [f"salary to {s['to']} < from {s['from']}"]
    return []


def requirement_evidence(doc: dict) -> list[str]:
    return [
        f"requirements/{i} ({', '.join(r['any_of'])}) has empty evidence"
        for i, r in enumerate(doc["requirements"])
        if not r["evidence"].strip()
    ]


def english_evidence(doc: dict) -> list[str]:
    e = doc["english"]
    if e["min_level"] is not None and not (e["evidence"] or "").strip():
        return [f"english.min_level {e['min_level']} has no evidence"]
    return []


RELATIONS: dict[str, Relation] = {
    "rel.experience_range": experience_range,
    "rel.salary_range": salary_range,
    "rel.requirement_evidence": requirement_evidence,
    "rel.english_evidence": english_evidence,
}


def relation_errors(doc: dict) -> list[str]:
    """Run every relation. Call only on a schema-valid doc: relations index fields the schema guarantees."""
    return [f"{name}: {msg}" for name, rel in RELATIONS.items() for msg in rel(doc)]
