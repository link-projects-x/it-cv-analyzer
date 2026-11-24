"""HTML of a DOU vacancy page → fields that do not need an LLM.

Selectors checked against a live page on 2026-10-31:
  h1.g-h2                  title
  div.l-n a                company (first link)
  span.place               comma-separated cities, "віддалено" for remote
  span.salary              salary string, absent on most vacancies
  .b-typo.vacancy-section  vacancy body
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

REMOTE_WORDS = ("віддалено", "удаленно", "remote")
MAX_TEXT_CHARS = 20_000  # caps prompt size on broken pages; the 241 vacancies on 2026-10-30 averaged 3,803 chars


class ExtractError(ValueError):
    pass


@dataclass(frozen=True)
class PageFields:
    title: str
    company: str
    cities: list[str]
    remote: bool | None
    salary_text: str | None
    text: str


def extract(html: str) -> PageFields:
    soup = BeautifulSoup(html, "html.parser")

    title = _text(soup.select_one("h1.g-h2"))
    company = _text(soup.select_one("div.l-n a"))
    body = soup.select_one(".b-typo.vacancy-section")
    if not title or body is None:
        raise ExtractError("page has no title or vacancy body; DOU markup may have changed")

    cities, remote = _location(_text(soup.select_one("span.place")))
    salary_text = _text(soup.select_one("span.salary")) or None
    text = _body_text(body)[:MAX_TEXT_CHARS]

    return PageFields(
        title=title,
        company=company or "unknown",
        cities=cities,
        remote=remote,
        salary_text=salary_text,
        text=text,
    )


def _text(node) -> str:
    return _normalize(node.get_text(" ", strip=True)) if node is not None else ""


BLOCK_TAGS = ("p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote")


def _body_text(body) -> str:
    """Newlines only at block boundaries, so inline tags (<b>, <a>, <span>) do not split a sentence."""
    for br in body.find_all("br"):
        br.replace_with("\n")
    for tag in body.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    for li in body.find_all("li"):
        li.insert(0, "- ")
    lines = (_normalize(line) for line in body.get_text("").split("\n"))
    return _normalize("\n".join(line for line in lines if line))


def _normalize(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _location(place: str) -> tuple[list[str], bool | None]:
    if not place:
        return [], None
    parts = [p.strip() for p in place.split(",") if p.strip()]
    remote = any(p.lower() in REMOTE_WORDS for p in parts)
    cities = [p for p in parts if p.lower() not in REMOTE_WORDS]
    return cities, remote
