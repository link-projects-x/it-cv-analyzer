"""cv/<uuid>.<pdf|docx|txt> → profiles/<uuid>.json, or failed-cv/<uuid>.json with the reason.

A CV is personal data. Logs carry the profile ID, sizes, token counts and error types only: never CV text, LLM
output or exception messages (jsonschema messages quote the offending value). After a successful parse the source
CV object is deleted unless delete_source=False; on failure it stays so the parse can be retried.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .assemble import InvalidProfile, assemble
from .extract import ExtractError, extract
from .llm import Llm, LlmError
from .prompt import output_schema, system_prompt, user_message

log = logging.getLogger(__name__)
CV_KEY_RE = re.compile(r"^cv/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(pdf|docx|txt)$")
MAX_FILE_BYTES = 10 * 1024 * 1024  # assumption: a text CV is well under 10 MB; larger files are rejected before parsing


class Store(Protocol):
    def get_bytes(self, key: str) -> bytes: ...
    def put_json(self, key: str, doc: dict) -> None: ...
    def delete(self, key: str) -> None: ...


@dataclass(frozen=True)
class Outcome:
    profile_id: str
    ok: bool
    key: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


def parse_cv(key: str, store: Store, llm: Llm, delete_source: bool = True) -> Outcome:
    match = CV_KEY_RE.match(key)
    if not match:
        # The key is not echoed: an uploaded file name can contain the candidate's name.
        raise ValueError("not a CV key; expected cv/<uuid>.<pdf|docx|txt>")
    profile_id, fmt = match.groups()

    data = store.get_bytes(key)
    try:
        if len(data) > MAX_FILE_BYTES:
            raise ExtractError(f"file is {len(data)} bytes, limit {MAX_FILE_BYTES}")
        cv = extract(data, fmt)
        log.info("%s extracted: format=%s bytes=%d chars=%d truncated=%s", profile_id, fmt, len(data), cv.chars, cv.truncated)
        result = llm.extract(system=system_prompt(), user=user_message(cv.text), schema=output_schema())
        doc = assemble(profile_id=profile_id, llm_data=result.data, model=result.model)
    except (ExtractError, LlmError, InvalidProfile, KeyError) as exc:
        failed_key = f"failed-cv/{profile_id}.json"
        store.put_json(
            failed_key,
            {
                "id": profile_id,
                "cv_key": key,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "doc": getattr(exc, "doc", None),
            },
        )
        log.warning("%s failed: %s: %s", profile_id, type(exc).__name__, _log_reason(exc))
        return Outcome(profile_id, ok=False, key=failed_key)

    out_key = f"profiles/{profile_id}.json"
    store.put_json(out_key, doc)
    if delete_source:
        store.delete(key)
    log.info(
        "%s ok: %d skills, %d unmapped, source %s, tokens in=%d out=%d cache_read=%d",
        profile_id,
        len(doc["skills"]),
        len(doc["unmapped"]),
        "deleted" if delete_source else "kept",
        result.input_tokens,
        result.output_tokens,
        result.cache_read_tokens,
    )
    return Outcome(profile_id, True, out_key, result.input_tokens, result.output_tokens, result.cache_read_tokens)


def _log_reason(exc: Exception) -> str:
    """ExtractError and LlmError messages are built from types, sizes and stop reasons. InvalidProfile messages can
    quote LLM output, so only its codes are logged. A KeyError names a field of the LLM output."""
    if isinstance(exc, InvalidProfile):
        return "; ".join(exc.codes)
    if isinstance(exc, KeyError):
        return f"missing field {exc.args[0]!r}" if exc.args else "missing field"
    return str(exc)


class S3Store:
    def __init__(self, bucket: str, s3_client=None):
        if s3_client is None:
            import boto3

            s3_client = boto3.client("s3")
        self._s3 = s3_client
        self._bucket = bucket

    def get_bytes(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def put_json(self, key: str, doc: dict) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)


class LocalStore:
    """Mirrors the S3 layout under a local directory."""

    def __init__(self, root: Path):
        self._root = root

    def get_bytes(self, key: str) -> bytes:
        return (self._root / key).read_bytes()

    def put_json(self, key: str, doc: dict) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, key: str) -> None:
        (self._root / key).unlink()
