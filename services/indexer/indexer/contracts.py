"""Load the shared contracts and validate vacancies against them. A copy of services/cv/cv/contracts.py, cut to what
the indexer uses; services do not import each other.

In the repo the contracts live in <repo>/contracts. The Lambda build copies them
into the package as indexer/contracts_data/. CONTRACTS_DIR overrides both.
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

_SCHEMAS = ("common", "vacancy", "profile", "match-response")


def contracts_dir() -> Path:
    if env := os.environ.get("CONTRACTS_DIR"):
        return Path(env)
    packaged = Path(__file__).resolve().parent / "contracts_data"
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[3] / "contracts"


def _load(name: str):
    with (contracts_dir() / name).open(encoding="utf-8") as f:
        return json.load(f)


@cache
def skill_names() -> dict[str, str]:
    return {s["id"]: s["name"] for s in _load("skills.json")["skills"]}


@cache
def _validator(kind: str) -> Draft202012Validator:
    registry = Registry()
    for name in _SCHEMAS:
        schema = _load(f"{name}.schema.json")
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(_load(f"{kind}.schema.json"), registry=registry, format_checker=FormatChecker())


def validation_codes(kind: str, doc: dict) -> list[str]:
    """"<path>: <keyword>" per schema error, without the offending value."""
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '(root)'}: {err.validator}"
        for err in sorted(_validator(kind).iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]
