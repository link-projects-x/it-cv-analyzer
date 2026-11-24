"""profiles/<uuid>.json -> matches/<uuid>.json (contracts/match-response.schema.json), or failed-match/<uuid>.json.

Steps: load index/vacancies.jsonl (services/indexer), embed the profile, take the 50 vacancies with the highest cosine
similarity, get the salary block, validate the response against the schema and the relations, write it.

A profile is personal data. Logs carry the job ID, counts, the best similarity, the salary model version and error
types/codes: never profile evidence, the embedding text or vectors, or jsonschema messages (they quote values).
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass

from . import contracts
from .embed import EmbeddingError, Embedder, profile_text
from .relations import relation_errors
from .salary import Salary, SalaryError, salary_input
from .store import Store

log = logging.getLogger(__name__)

PROFILE_KEY_RE = re.compile(r"^profiles/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.json$")
INDEX_KEY = "index/vacancies.jsonl"
TOP_K = 50  # contracts/match-response.schema.json -> vacancies.maxItems


class IndexUnusable(RuntimeError):
    """The vacancy index is missing or does not fit the profile embedding."""


class InvalidMatch(ValueError):
    """errors: full messages, written to failed-match/ (jsonschema messages may quote profile text).
    codes: "<path>: <keyword>" and relation messages, safe to log."""

    def __init__(self, errors: list[str], codes: list[str], doc: dict):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.codes = codes
        self.doc = doc


@dataclass(frozen=True)
class Outcome:
    job_id: str
    ok: bool
    key: str
    vacancies: int = 0


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise IndexUnusable(f"embedding sizes differ: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if norm == 0 else max(-1.0, min(1.0, dot / norm))


def top_matches(query: list[float], entries: list[dict], k: int = TOP_K) -> list[dict]:
    """[{similarity, vacancy}] for the k entries closest to query, similarity descending, ties by vacancy ID."""
    scored = [(cosine(query, e["embedding"]), e["id"], e["vacancy"]) for e in entries]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"similarity": round(sim, 6), "vacancy": vacancy} for sim, _, vacancy in scored[:k]]


def load_index(store: Store, model_id: str) -> list[dict]:
    text = store.get_text(INDEX_KEY)
    if text is None:
        raise IndexUnusable(f"{INDEX_KEY} does not exist; run the indexer")
    entries = [json.loads(line) for line in text.splitlines() if line.strip()]
    models = {e["embedding_model"] for e in entries}
    if models - {model_id}:
        raise IndexUnusable(f"index embedded with {sorted(models)}, matcher uses {model_id}; re-run the indexer")
    return entries


def assemble(profile: dict, vacancies: list[dict], salary: dict) -> dict:
    doc = {"schema_version": "1.0", "profile": profile, "vacancies": vacancies, "salary": salary}
    errors = contracts.validation_errors("match-response", doc)
    if errors:
        raise InvalidMatch(errors, contracts.validation_codes("match-response", doc), doc)
    errors = relation_errors(doc)
    if errors:
        raise InvalidMatch(errors, errors, doc)
    return doc


def match_profile(key: str, store: Store, embedder: Embedder, salary: Salary) -> Outcome:
    m = PROFILE_KEY_RE.match(key)
    if not m:
        raise ValueError("not a profile key; expected profiles/<uuid>.json")
    job_id = m.group(1)

    profile = store.get_json(key)
    if profile is None:
        raise FileNotFoundError(f"{job_id}: profile object is gone")  # raised: the async invocation is retried
    try:
        entries = load_index(store, embedder.model_id)
        [query] = embedder.embed([profile_text(profile, contracts.skill_names())], "search_query")
        vacancies = top_matches(query, entries)
        estimate = salary.estimate(salary_input(profile))
        doc = assemble(profile, vacancies, estimate)
    except (IndexUnusable, EmbeddingError, SalaryError, InvalidMatch, KeyError, TypeError) as exc:
        failed_key = f"failed-match/{job_id}.json"
        store.put_json(
            failed_key,
            {
                "id": job_id,
                "profile_key": key,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "doc": getattr(exc, "doc", None),
            },
        )
        log.warning("%s match failed: %s: %s", job_id, type(exc).__name__, _log_reason(exc))
        return Outcome(job_id, ok=False, key=failed_key)

    out_key = f"matches/{job_id}.json"
    store.put_json(out_key, doc)
    log.info(
        "%s matched: %d of %d vacancies, best similarity %s, salary %s",
        job_id,
        len(vacancies),
        len(entries),
        vacancies[0]["similarity"] if vacancies else None,
        doc["salary"]["model_version"],
    )
    return Outcome(job_id, True, out_key, len(vacancies))


def _log_reason(exc: Exception) -> str:
    """IndexUnusable, EmbeddingError and SalaryError messages are built from sizes, IDs and codes. InvalidMatch messages
    can quote profile text, so only its codes are logged. KeyError and TypeError name a field or a type."""
    if isinstance(exc, InvalidMatch):
        return "; ".join(exc.codes)
    if isinstance(exc, KeyError):
        return f"missing field {exc.args[0]!r}" if exc.args else "missing field"
    if isinstance(exc, TypeError):
        return "unexpected value type"
    return str(exc)
