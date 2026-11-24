"""HTTP API behind a Lambda function URL (payload format 2.0).

POST /uploads      {"filename", "size", "content_type"}
                   -> 201 {"job_id", "upload": {"url", "fields"}, "expires_in"}
                   The browser sends the CV with a multipart POST to upload.url: every field in upload.fields, then
                   the file as the last field named "file". The policy allows only key cv/<job_id>.<ext>, that
                   Content-Type, 1..size bytes, for UPLOAD_EXPIRES_SECONDS.
GET  /jobs/{id}    -> 200 {"state": "uploading" | "parsing" | "matching"}
                         | {"state": "done", "result": <match-response>}
                         | {"state": "failed", "error": "<short text>"}
Errors             -> 4xx {"error": "<code>", "message": "<text>"}

Every request needs `Authorization: Bearer <access code>` (401 otherwise) and POST /uploads is limited per code and in
total per day (429); see access.py. A job is visible only with the code that created it (404 for another code).

State comes from which S3 objects exist (see job_state). POST writes jobs/<job_id>.json with the creation time and the
file format, so GET can tell an unknown ID (404) from an upload that has not arrived yet. The marker holds no file
name: an uploaded file name often contains the candidate's name. Nothing from the request body is logged.

CORS headers and OPTIONS preflight are handled by the function URL's CORS configuration (infra/lambdas.tf).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from .access import AccessPolicy, quota_key, quota_prefix

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
UPLOAD_EXPIRES_SECONDS = 600
UPLOAD_TIMEOUT = timedelta(minutes=15)
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}
# Browsers report "" or a generic type for files whose type they do not know (often .docx without Office installed)
GENERIC_CONTENT_TYPES = {"", "application/octet-stream"}
JOB_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")  # UUID v4
JOBS_PATH_RE = re.compile(r"^/jobs/([^/]+)$")

FAILED_CV_MESSAGES = {
    "LlmError": "The CV could not be parsed.",
    "InvalidProfile": "The CV could not be turned into a valid profile.",
    "KeyError": "The CV could not be turned into a valid profile.",
}
MATCH_FAILED_MESSAGE = "Matching against vacancies failed."
UPLOAD_TIMEOUT_MESSAGE = "The CV did not arrive within 15 minutes of starting the upload."
ERROR_MAX_CHARS = 200


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _error(status: int, code: str, message: str) -> dict:
    return _response(status, {"error": code, "message": message})


def _body(event: dict) -> object:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


def create_upload(event: dict, store, now: datetime, label: str, access: AccessPolicy) -> dict:
    try:
        body = _body(event)
    except (ValueError, UnicodeDecodeError):
        return _error(400, "invalid_json", "Request body must be a JSON object.")
    if not isinstance(body, dict):
        return _error(400, "invalid_json", "Request body must be a JSON object.")

    filename, size, content_type = body.get("filename"), body.get("size"), body.get("content_type", "")
    if not isinstance(filename, str) or "." not in filename:
        return _error(400, "invalid_filename", "filename with an extension is required.")
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in CONTENT_TYPES:
        return _error(400, "unsupported_extension", "Only .pdf, .docx and .txt files are accepted.")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return _error(400, "invalid_size", "size must be a positive integer number of bytes.")
    if size > MAX_UPLOAD_BYTES:
        return _error(413, "file_too_large", f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not isinstance(content_type, str):
        return _error(400, "invalid_content_type", "content_type must be a string.")
    base_type = content_type.split(";")[0].strip().lower()
    if base_type not in GENERIC_CONTENT_TYPES and base_type != CONTENT_TYPES[ext]:
        return _error(400, "content_type_mismatch", f"content_type does not match a .{ext} file.")

    if store.count(quota_prefix(now, label)) >= access.daily_per_code:
        log.info("upload refused: daily limit for %s", label)
        return _error(429, "daily_limit", f"This access code has used its {access.daily_per_code} uploads for today (UTC).")
    if store.count(quota_prefix(now)) >= access.daily_total:
        log.info("upload refused: daily total limit")
        return _error(429, "daily_limit", "The service has reached today's upload limit (UTC). Try again tomorrow.")

    job_id = str(uuid.uuid4())
    store.put_json(
        f"jobs/{job_id}.json",
        {"id": job_id, "created_at": now.isoformat(timespec="seconds"), "format": ext, "size": size, "owner": label},
    )
    store.put_json(quota_key(now, label, job_id), {})
    upload = store.presigned_post(f"cv/{job_id}.{ext}", CONTENT_TYPES[ext], size, UPLOAD_EXPIRES_SECONDS)
    log.info("%s upload created by %s: format=%s bytes=%d", job_id, label, ext, size)
    return _response(
        201, {"job_id": job_id, "upload": {"url": upload["url"], "fields": upload["fields"]}, "expires_in": UPLOAD_EXPIRES_SECONDS}
    )


def _short_cv_error(failed: dict) -> str:
    """failed-cv/ documents come from services/cv. ExtractError messages are built from the format, sizes and
    exception types (services/cv/cv/extract.py), so they are shown; other errors get a fixed text."""
    error_type = failed.get("error_type", "")
    if error_type == "ExtractError":
        return str(failed.get("error", ""))[:ERROR_MAX_CHARS] or "The file could not be read."
    return FAILED_CV_MESSAGES.get(error_type, "The CV could not be processed.")


def job_state(job_id: str, store, now: datetime, label: str | None = None) -> dict | None:
    """None for an unknown job, and for a job created with another access code (label given and not the owner). Terminal states are checked first. When the CV object is missing, profiles/ is read
    again: services/cv writes the profile before it deletes the CV, so a CV that disappeared between the first
    profiles/ check and the cv/ check has a profile by the second check."""
    marker = store.get_json(f"jobs/{job_id}.json")
    if marker is None:
        return None
    if label is not None and marker.get("owner") != label:
        return None
    result = store.get_json(f"matches/{job_id}.json")
    if result is not None:
        return {"state": "done", "result": result}
    if store.exists(f"failed-match/{job_id}.json"):
        return {"state": "failed", "error": MATCH_FAILED_MESSAGE}
    if store.exists(f"profiles/{job_id}.json"):
        return {"state": "matching"}
    failed_cv = store.get_json(f"failed-cv/{job_id}.json")
    if failed_cv is not None:
        return {"state": "failed", "error": _short_cv_error(failed_cv)}
    if store.exists(f"cv/{job_id}.{marker['format']}"):
        return {"state": "parsing"}
    if store.exists(f"profiles/{job_id}.json"):
        return {"state": "matching"}
    created = datetime.fromisoformat(marker["created_at"])
    if now - created > UPLOAD_TIMEOUT:
        return {"state": "failed", "error": UPLOAD_TIMEOUT_MESSAGE}
    return {"state": "uploading"}


def route(
    event: dict, store, access: AccessPolicy, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> dict:
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")

    if path != "/uploads" and not JOBS_PATH_RE.match(path):
        return _error(404, "not_found", "No such route.")
    label = access.label_for(event)
    if label is None:
        return _error(401, "unauthorized", "A valid access code is required.")

    if path == "/uploads":
        if method != "POST":
            return _error(405, "method_not_allowed", "Use POST.")
        return create_upload(event, store, now(), label, access)

    m = JOBS_PATH_RE.match(path)
    if m:
        if method != "GET":
            return _error(405, "method_not_allowed", "Use GET.")
        job_id = m.group(1)
        if not JOB_ID_RE.match(job_id):
            return _error(400, "invalid_job_id", "Job ID must be a lowercase UUID v4.")
        state = job_state(job_id, store, now(), label)
        if state is None:
            return _error(404, "job_not_found", "No such job.")
        log.info("%s state %s", job_id, state["state"])
        return _response(200, state)

    return _error(404, "not_found", "No such route.")
