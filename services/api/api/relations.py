"""Cross-field rules a match response must satisfy (contracts/README.md -> Relations).

Copied from contracts/check.py (profile relations and rel.grid_matches_point); services do not import contracts code.
Messages name skill IDs, grid rows, keys and numbers only, never evidence text: the messages go to the logs.
"""

from __future__ import annotations

from collections import Counter
from typing import Callable

Relation = Callable[[dict], list[str]]

GRID_TOLERANCE = 0.5  # contracts/README.md: every grid row reads salary.point (±0.5)


def grid_key_experience(years: float) -> str:
    """Grid lookup key for experience: nearest whole year, half rounds up, clamped to 0..15 (contracts/README.md)."""
    return str(min(15, max(0, int(years + 0.5))))


def skill_evidence(doc: dict) -> list[str]:
    return [
        f"profile/skills/{i} ({s['id']}) at level {s['level']} has no evidence"
        for i, s in enumerate(doc["profile"]["skills"])
        if s["level"] >= 2 and not (s["evidence"] or "").strip()
    ]


def unique_skills(doc: dict) -> list[str]:
    counts = Counter(s["id"] for s in doc["profile"]["skills"])
    return [f"skill {sid} appears {n} times" for sid, n in sorted(counts.items()) if n > 1]


def grid_matches_point(doc: dict) -> list[str]:
    """At the profile's own position every grid row reads salary.point."""
    profile, salary = doc["profile"], doc["salary"]
    grid, point = salary["grid"], salary["point"]
    opening = {"experience_years": grid_key_experience(profile["experience_years"])}
    if profile["english"] is not None:
        opening["english"] = profile["english"]
    if profile["salary_features"]["company_type"] is not None:
        opening["company_type"] = profile["salary_features"]["company_type"]
    if len(profile["salary_features"]["domains"]) == 1:
        opening["domains"] = profile["salary_features"]["domains"][0]
    errors = []
    for row, key in opening.items():
        value = grid[row].get(key)
        if value is None:
            errors.append(f"grid.{row} has no key {key!r} for the profile")
        elif abs(value - point) > GRID_TOLERANCE:
            errors.append(f"grid.{row}[{key!r}] = {value}, point = {point}")
    return errors


RELATIONS: dict[str, Relation] = {
    "rel.skill_evidence": skill_evidence,
    "rel.unique_skills": unique_skills,
    "rel.grid_matches_point": grid_matches_point,
}


def relation_errors(doc: dict) -> list[str]:
    """Run every relation. Call only on a schema-valid doc: relations index fields the schema guarantees."""
    return [f"{name}: {msg}" for name, rel in RELATIONS.items() for msg in rel(doc)]
