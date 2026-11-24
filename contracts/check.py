"""Contract checks.

1. skills.json: IDs are unique, every parent points to an existing ID, no alias belongs to two skills.
2. Every file in examples/ validates against its JSON Schema (by name: vacancy.example.json -> vacancy.schema.json).
3. Every skill ID inside the examples exists in skills.json (the schema checks only the ID format).
4. fixtures/coverage-golden.json matches what coverage_reference.py computes now.
5. The examples satisfy the cross-field relations in contracts/README.md (profile and match-response).

Run: python contracts/check.py  (requires: pip install -r contracts/requirements.txt)
Exits with code 1 if there are errors.
"""

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from coverage_reference import golden_is_current

ROOT = Path(__file__).resolve().parent
SCHEMA_FILES = ["common", "vacancy", "profile", "match-response"]


def load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_skills(skills_doc) -> tuple[set[str], list[str]]:
    errors = []
    ids = [s["id"] for s in skills_doc["skills"]]
    seen = set()
    for sid in ids:
        if sid in seen:
            errors.append(f"skills.json: duplicate id {sid!r}")
        seen.add(sid)

    alias_owner: dict[str, str] = {}
    for s in skills_doc["skills"]:
        parent = s.get("parent")
        if parent is not None and parent not in seen:
            errors.append(f"skills.json: {s['id']!r} points to missing parent {parent!r}")
        for alias in s["aliases"]:
            if alias != alias.lower():
                errors.append(f"skills.json: alias {alias!r} of {s['id']!r} is not lowercase")
            owner = alias_owner.setdefault(alias, s["id"])
            if owner != s["id"]:
                errors.append(f"skills.json: alias {alias!r} belongs to both {owner!r} and {s['id']!r}")
    return seen, errors


def build_registry() -> Registry:
    registry = Registry()
    for name in SCHEMA_FILES:
        schema = load(ROOT / f"{name}.schema.json")
        resource = Resource.from_contents(schema)
        registry = registry.with_resource(schema["$id"], resource)
    return registry


def collect_skill_ids(node, path="$"):
    """Yield every skill ID from requirements[].any_of and skills[].id, with its JSON path for error messages."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if key == "any_of" and isinstance(value, list):
                for i, sid in enumerate(value):
                    yield f"{child}[{i}]", sid
            elif key == "skills" and isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict) and "id" in item:
                        yield f"{child}[{i}].id", item["id"]
            else:
                yield from collect_skill_ids(value, child)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from collect_skill_ids(item, f"{path}[{i}]")


def grid_key_experience(years: float) -> str:
    """Grid lookup key for experience: nearest whole year, half rounds up, clamped to 0..15 (contracts/README.md)."""
    return str(min(15, max(0, int(years + 0.5))))


def profile_relation_errors(name: str, profile: dict) -> list[str]:
    errors = []
    ids = [s["id"] for s in profile["skills"]]
    for sid in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"{name}: rel.unique_skills: {sid!r} appears more than once")
    for s in profile["skills"]:
        if s["level"] >= 2 and not (s["evidence"] or "").strip():
            errors.append(f"{name}: rel.skill_evidence: {s['id']!r} at level {s['level']} has no evidence")
    return errors


def match_relation_errors(name: str, doc: dict) -> list[str]:
    """rel.grid_matches_point: at the profile's own position every grid row reads salary.point."""
    errors = profile_relation_errors(name, doc["profile"])
    salary, profile = doc["salary"], doc["profile"]
    grid, point = salary["grid"], salary["point"]
    opening = {"experience_years": grid_key_experience(profile["experience_years"])}
    if profile["english"] is not None:
        opening["english"] = profile["english"]
    if profile["salary_features"]["company_type"] is not None:
        opening["company_type"] = profile["salary_features"]["company_type"]
    if len(profile["salary_features"]["domains"]) == 1:
        opening["domains"] = profile["salary_features"]["domains"][0]
    for row, key in opening.items():
        value = grid[row].get(key)
        if value is None:
            errors.append(f"{name}: rel.grid_matches_point: grid.{row} has no key {key!r} for the profile")
        elif abs(value - point) > 0.5:
            errors.append(f"{name}: rel.grid_matches_point: grid.{row}[{key!r}] = {value}, point = {point}")
    return errors


RELATION_CHECKS = {"profile": profile_relation_errors, "match-response": match_relation_errors}


def main() -> int:
    skill_ids, errors = check_skills(load(ROOT / "skills.json"))
    registry = build_registry()

    examples = sorted((ROOT / "examples").glob("*.example.json"))
    if not examples:
        errors.append("examples/: no *.example.json files")

    for example_path in examples:
        kind = example_path.name.removesuffix(".example.json")
        schema_path = ROOT / f"{kind}.schema.json"
        if not schema_path.exists():
            errors.append(f"{example_path.name}: schema {schema_path.name} not found")
            continue

        validator = Draft202012Validator(load(schema_path), registry=registry, format_checker=FormatChecker())
        doc = load(example_path)
        for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
            where = "/".join(str(p) for p in err.absolute_path) or "(root)"
            errors.append(f"{example_path.name}: {where}: {err.message}")

        if kind in RELATION_CHECKS:
            errors += RELATION_CHECKS[kind](example_path.name, doc)

        for where, sid in collect_skill_ids(doc):
            if sid not in skill_ids:
                errors.append(f"{example_path.name}: {where}: skill {sid!r} is not in skills.json")

    errors += golden_is_current()

    for e in errors:
        print("ERROR", e)
    print(f"skills: {len(skill_ids)}, examples: {len(examples)}, errors: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
