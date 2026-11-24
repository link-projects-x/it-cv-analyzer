"""Scrape run shared by the Lambda handler and the local CLI.

Downloads every vacancy in the category that is not stored yet and writes it as
raw/dou-<id>.html. Already stored vacancies are skipped, so a daily run only
downloads new ones and the parser (triggered per new object) only parses new ones.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from .dou import DouClient, VacancyRef

log = logging.getLogger(__name__)


class RawStore(Protocol):
    def exists(self, key: str) -> bool: ...
    def put_html(self, key: str, body: bytes, metadata: dict[str, str]) -> None: ...


@dataclass
class RunResult:
    listed: int = 0
    skipped_existing: int = 0
    stored: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    stopped_early: bool = False


def raw_key(vacancy_id: str) -> str:
    return f"raw/{vacancy_id}.html"


def scrape(
    client: DouClient,
    store: RawStore,
    category: str,
    max_new: int,
    time_left_seconds: Callable[[], float] = lambda: float("inf"),
    min_time_left_seconds: float = 30.0,
) -> RunResult:
    result = RunResult()
    refs: list[VacancyRef] = client.list_vacancies(category)
    result.listed = len(refs)

    for ref in refs:
        if len(result.stored) >= max_new or time_left_seconds() < min_time_left_seconds:
            result.stopped_early = True
            break

        key = raw_key(ref.id)
        if store.exists(key):
            result.skipped_existing += 1
            continue

        try:
            body = client.fetch_vacancy(ref)
        except Exception as exc:  # one broken page must not stop the run
            log.warning("fetch failed for %s: %s", ref.url, exc)
            result.failed[ref.id] = str(exc)
            continue

        store.put_html(
            key,
            body,
            metadata={
                "url": ref.url,
                "scraped-at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "category": category,
            },
        )
        result.stored.append(ref.id)

    log.info(
        "listed=%d skipped=%d stored=%d failed=%d stopped_early=%s",
        result.listed,
        result.skipped_existing,
        len(result.stored),
        len(result.failed),
        result.stopped_early,
    )
    return result


def monotonic_deadline(seconds: float) -> Callable[[], float]:
    deadline = time.monotonic() + seconds
    return lambda: deadline - time.monotonic()
