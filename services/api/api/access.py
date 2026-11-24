"""Who may call the HTTP API, and how much.

Access codes. Every request carries `Authorization: Bearer <code>`. The Lambda holds only SHA-256 hashes of the
codes (env ACCESS_CODES = "label:sha256hex,label:sha256hex"), one per person, so one code can be revoked without
touching the others. Comparison is constant-time. With no codes configured every request is refused (fail closed).
New codes: scripts/new_access_code.py.

Quotas. Each created upload writes an empty marker quota/<YYYY-MM-DD>/<label>/<job_id>.json; POST /uploads counts the
markers for today (UTC) per label and in total and answers 429 above DAILY_UPLOADS_PER_CODE / DAILY_UPLOADS_TOTAL.
Two simultaneous requests can both pass the check, so a limit can be overshot by the number of parallel requests;
the Lambda's reserved concurrency (infra) caps that.

The code itself is never logged; the label is.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger(__name__)

LABEL_RE = re.compile(r"^[a-z0-9-]{1,32}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_DAILY_PER_CODE = 10
DEFAULT_DAILY_TOTAL = 40


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AccessPolicy:
    codes: tuple[tuple[str, str], ...]  # (label, sha256 hex)
    daily_per_code: int = DEFAULT_DAILY_PER_CODE
    daily_total: int = DEFAULT_DAILY_TOTAL

    @classmethod
    def from_env(cls, env) -> "AccessPolicy":
        codes = []
        for item in (env.get("ACCESS_CODES") or "").split(","):
            item = item.strip()
            if not item:
                continue
            label, _, digest = item.partition(":")
            if not LABEL_RE.match(label) or not HASH_RE.match(digest):
                # Skipped rather than fatal, so one bad entry does not lock everyone out; the label alone is logged
                log.warning("ACCESS_CODES entry skipped: label %r or hash is malformed", label[:32])
                continue
            codes.append((label, digest))
        if not codes:
            log.warning("ACCESS_CODES is empty: every API request will be refused")
        return cls(
            codes=tuple(codes),
            daily_per_code=int(env.get("DAILY_UPLOADS_PER_CODE") or DEFAULT_DAILY_PER_CODE),
            daily_total=int(env.get("DAILY_UPLOADS_TOTAL") or DEFAULT_DAILY_TOTAL),
        )

    def label_for(self, event: dict) -> str | None:
        """Label of the code in the Authorization header, or None. Function URL events carry lowercase header names."""
        header = (event.get("headers") or {}).get("authorization", "")
        scheme, _, code = header.partition(" ")
        if scheme.lower() != "bearer" or not code.strip():
            return None
        digest = hash_code(code.strip())
        found = None
        for label, stored in self.codes:  # no early exit, so timing does not tell which entry matched
            if hmac.compare_digest(digest, stored):
                found = label
        return found


def quota_prefix(now: datetime, label: str | None = None) -> str:
    day = now.strftime("%Y-%m-%d")
    return f"quota/{day}/" if label is None else f"quota/{day}/{label}/"


def quota_key(now: datetime, label: str, job_id: str) -> str:
    return f"{quota_prefix(now, label)}{job_id}.json"
