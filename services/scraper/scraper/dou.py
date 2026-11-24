"""DOU jobs client: list vacancy URLs in a category and download vacancy pages.

Uses only the standard library so the Lambda package needs no dependencies.

The list page shows the first 20 vacancies. The rest come from POST /vacancies/xhr-load/,
which needs the csrftoken cookie set by the list page and returns {"html", "num", "last"}.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE = "https://jobs.dou.ua"
USER_AGENT = "dou-cv-analyzer/0.1 (learning project)"
VACANCY_URL_RE = re.compile(r'href="(https://jobs\.dou\.ua/companies/[^"/]+/vacancies/(\d+)/)')
MAX_XHR_PAGES = 50  # 20 + 50 * 40 vacancies is far above the 241 seen on 2026-10-30


@dataclass(frozen=True)
class VacancyRef:
    id: str  # "dou-377767"
    url: str  # canonical URL without query string


class DouClient:
    def __init__(self, delay_seconds: float = 1.0, timeout: float = 20.0):
        self._delay = delay_seconds
        self._timeout = timeout
        self._cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookies))
        self._last_request = 0.0

    def _request(self, url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        wait = self._delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                return resp.read()
        finally:
            self._last_request = time.monotonic()

    def _csrf_token(self) -> str:
        for cookie in self._cookies:
            if cookie.name == "csrftoken":
                return cookie.value
        raise RuntimeError("DOU did not set the csrftoken cookie on the list page")

    def list_vacancies(self, category: str = "AI/ML") -> list[VacancyRef]:
        list_url = f"{BASE}/vacancies/?category={urllib.parse.quote(category, safe='/')}"
        first_page = self._request(list_url).decode("utf-8")
        refs: dict[str, VacancyRef] = {}
        _collect(first_page, refs)

        count = len(refs)
        xhr_url = f"{BASE}/vacancies/xhr-load/?category={urllib.parse.quote(category, safe='/')}"
        for _ in range(MAX_XHR_PAGES):
            body = urllib.parse.urlencode({"csrfmiddlewaretoken": self._csrf_token(), "count": count}).encode()
            payload = json.loads(
                self._request(
                    xhr_url,
                    data=body,
                    headers={"Referer": list_url, "X-Requested-With": "XMLHttpRequest"},
                )
            )
            _collect(payload["html"], refs)
            count += payload["num"]
            if payload["last"]:
                break
        else:
            raise RuntimeError(f"xhr-load did not report last=true after {MAX_XHR_PAGES} pages")

        return list(refs.values())

    def fetch_vacancy(self, ref: VacancyRef) -> bytes:
        return self._request(ref.url)


def _collect(html: str, refs: dict[str, VacancyRef]) -> None:
    for url, num in VACANCY_URL_RE.findall(html):
        vid = f"dou-{num}"
        refs.setdefault(vid, VacancyRef(id=vid, url=url))
