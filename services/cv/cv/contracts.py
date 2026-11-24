"""Load the shared contracts and validate documents against them.

In the repo the contracts live in <repo>/contracts. The Lambda build copies them
into the package as cv/contracts_data/. CONTRACTS_DIR overrides both.
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
def skills() -> dict:
    return _load("skills.json")


@cache
def skill_ids() -> frozenset[str]:
    return frozenset(s["id"] for s in skills()["skills"])


@cache
def common_defs() -> dict:
    return _load("common.schema.json")["$defs"]


@cache
def _validator(kind: str) -> Draft202012Validator:
    registry = Registry()
    for name in _SCHEMAS:
        schema = _load(f"{name}.schema.json")
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(_load(f"{kind}.schema.json"), registry=registry, format_checker=FormatChecker())


def validation_errors(kind: str, doc: dict) -> list[str]:
    errors = []
    for err in sorted(_validator(kind).iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{where}: {err.message}")
    return errors


def validation_codes(kind: str, doc: dict) -> list[str]:
    """Like validation_errors, but "<path>: <keyword>" without the offending value, for logs.

    jsonschema messages quote the value ("'...' is too long"); in a profile that value can be CV text."""
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '(root)'}: {err.validator}"
        for err in sorted(_validator(kind).iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]


@cache
def profile_schema() -> dict:
    return _load("profile.schema.json")
