"""processed/*.json -> index/vacancies.jsonl: one line per vacancy with its embedding.

Line format (read by services/api/api/matcher.py):
  {"id", "parsed_at", "embedding_model", "text_version", "embedding": [float], "vacancy": <vacancy.schema.json doc>}

A vacancy is re-embedded when it is new, when its parse.parsed_at differs from the previous index line, or when the
embedding model or TEXT_VERSION changed. Otherwise the previous embedding is reused. Vacancies that fail
contracts/vacancy.schema.json are left out and logged by ID and error codes. Vacancies removed from processed/ drop
out of the index.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import contracts
from .embed import TEXT_VERSION, Embedder, vacancy_text

log = logging.getLogger(__name__)

INDEX_KEY = "index/vacancies.jsonl"
PROCESSED_PREFIX = "processed/"
PROCESSED_KEY_RE = re.compile(r"^processed/(dou-\d+)\.json$")


class Store(Protocol):
    def list_keys(self, prefix: str) -> list[str]: ...
    def get_text(self, key: str) -> str | None: ...
    def put_text(self, key: str, text: str, content_type: str) -> None: ...


@dataclass
class IndexResult:
    total: int = 0
    embedded: list[str] = field(default_factory=list)
    reused: int = 0
    invalid: list[str] = field(default_factory=list)
    removed: int = 0


def read_index(store: Store) -> dict[str, dict]:
    text = store.get_text(INDEX_KEY)
    if text is None:
        return {}
    entries = {}
    for line in text.splitlines():
        if line.strip():
            entry = json.loads(line)
            entries[entry["id"]] = entry
    return entries


def _reusable(previous: dict | None, parsed_at: str, model_id: str) -> bool:
    return (
        previous is not None
        and previous.get("parsed_at") == parsed_at
        and previous.get("embedding_model") == model_id
        and previous.get("text_version") == TEXT_VERSION
        and bool(previous.get("embedding"))
    )


def build_index(store: Store, embedder: Embedder) -> IndexResult:
    previous = read_index(store)
    result = IndexResult()
    names = contracts.skill_names()

    vacancies: list[dict] = []
    for key in sorted(store.list_keys(PROCESSED_PREFIX)):
        if not PROCESSED_KEY_RE.match(key):
            continue
        text = store.get_text(key)
        if text is None:  # removed between list and get
            continue
        doc = json.loads(text)
        codes = contracts.validation_codes("vacancy", doc)
        if codes:
            result.invalid.append(doc.get("id", key))
            log.warning("%s skipped: invalid vacancy: %s", key, "; ".join(codes))
            continue
        vacancies.append(doc)

    entries: dict[str, dict] = {}
    to_embed: list[dict] = []
    for doc in vacancies:
        parsed_at = doc["parse"]["parsed_at"]
        prev = previous.get(doc["id"])
        entry = {
            "id": doc["id"],
            "parsed_at": parsed_at,
            "embedding_model": embedder.model_id,
            "text_version": TEXT_VERSION,
            "embedding": None,
            "vacancy": doc,
        }
        if _reusable(prev, parsed_at, embedder.model_id):
            entry["embedding"] = prev["embedding"]
            result.reused += 1
        else:
            to_embed.append(entry)
        entries[doc["id"]] = entry

    if to_embed:
        vectors = embedder.embed([vacancy_text(e["vacancy"], names) for e in to_embed], "search_document")
        for entry, vector in zip(to_embed, vectors, strict=True):
            entry["embedding"] = vector
            result.embedded.append(entry["id"])

    result.total = len(entries)
    result.removed = len(set(previous) - set(entries))
    lines = [json.dumps(entries[i], ensure_ascii=False) for i in sorted(entries)]
    store.put_text(INDEX_KEY, "\n".join(lines) + ("\n" if lines else ""), "application/x-ndjson; charset=utf-8")
    log.info(
        "index written: %d vacancies, %d embedded, %d reused, %d invalid, %d removed, model=%s",
        result.total,
        len(result.embedded),
        result.reused,
        len(result.invalid),
        result.removed,
        embedder.model_id,
    )
    return result


class S3Store:
    def __init__(self, bucket: str, s3_client=None):
        if s3_client is None:
            import boto3

            s3_client = boto3.client("s3")
        self._s3 = s3_client
        self._bucket = bucket

    def list_keys(self, prefix: str) -> list[str]:
        keys = []
        for page in self._s3.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def get_text(self, key: str) -> str | None:
        # Existence goes through ListBucket with a prefix: a GetObject on a missing key answers 403 instead of 404
        # unless the role may list the bucket.
        if key not in self.list_keys(key):
            return None
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read().decode("utf-8")

    def put_text(self, key: str, text: str, content_type: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=text.encode("utf-8"), ContentType=content_type)


class LocalStore:
    """Mirrors the S3 layout under a local directory."""

    def __init__(self, root: Path):
        self._root = root

    def list_keys(self, prefix: str) -> list[str]:
        base = self._root / prefix
        if not base.is_dir():
            return []
        return [f"{prefix}{p.name}" for p in base.iterdir() if p.is_file()]

    def get_text(self, key: str) -> str | None:
        path = self._root / key
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put_text(self, key: str, text: str, content_type: str) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
