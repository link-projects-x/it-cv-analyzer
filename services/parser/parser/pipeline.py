"""raw/dou-<id>.html → processed/dou-<id>.json, or failed/dou-<id>.json with the reason."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .assemble import InvalidVacancy, assemble
from .extract import ExtractError, extract
from .llm import Llm, LlmError
from .prompt import output_schema, system_prompt, user_message

log = logging.getLogger(__name__)
RAW_KEY_RE = re.compile(r"^raw/(dou-\d+)\.html$")


class Store(Protocol):
    def get_html(self, key: str) -> tuple[str, dict[str, str]]: ...
    def put_json(self, key: str, doc: dict) -> None: ...


@dataclass(frozen=True)
class Outcome:
    vacancy_id: str
    ok: bool
    key: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


def parse_raw(key: str, store: Store, llm: Llm) -> Outcome:
    match = RAW_KEY_RE.match(key)
    if not match:
        raise ValueError(f"not a raw vacancy key: {key}")
    vacancy_id = match.group(1)

    html, meta = store.get_html(key)
    try:
        page = extract(html)
        result = llm.extract(
            system=system_prompt(),
            user=user_message(page.title, page.company, page.salary_text, page.text),
            schema=output_schema(),
        )
        doc = assemble(
            vacancy_id=vacancy_id,
            url=meta["url"],
            scraped_at=meta["scraped-at"],
            page=page,
            llm_data=result.data,
            model=result.model,
        )
    except (ExtractError, LlmError, InvalidVacancy, KeyError) as exc:
        failed_key = f"failed/{vacancy_id}.json"
        store.put_json(
            failed_key,
            {
                "id": vacancy_id,
                "raw_key": key,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "doc": getattr(exc, "doc", None),
            },
        )
        log.warning("%s failed: %s: %s", vacancy_id, type(exc).__name__, exc)
        return Outcome(vacancy_id, ok=False, key=failed_key)

    out_key = f"processed/{vacancy_id}.json"
    store.put_json(out_key, doc)
    log.info(
        "%s ok: %d requirements, tokens in=%d out=%d cache_read=%d",
        vacancy_id,
        len(doc["requirements"]),
        result.input_tokens,
        result.output_tokens,
        result.cache_read_tokens,
    )
    return Outcome(vacancy_id, True, out_key, result.input_tokens, result.output_tokens, result.cache_read_tokens)


class S3Store:
    def __init__(self, bucket: str, s3_client=None):
        if s3_client is None:
            import boto3

            s3_client = boto3.client("s3")
        self._s3 = s3_client
        self._bucket = bucket

    def get_html(self, key: str) -> tuple[str, dict[str, str]]:
        obj = self._s3.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read().decode("utf-8"), obj.get("Metadata", {})

    def put_json(self, key: str, doc: dict) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )


class LocalStore:
    """Mirrors the S3 layout under a local directory; metadata comes from the scraper's .meta.json sidecar."""

    def __init__(self, root: Path):
        self._root = root

    def get_html(self, key: str) -> tuple[str, dict[str, str]]:
        path = self._root / key
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        return path.read_text(encoding="utf-8"), meta

    def put_json(self, key: str, doc: dict) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
