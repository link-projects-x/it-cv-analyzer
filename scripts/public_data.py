"""Anonymise vacancies for the public site: no company, no title text, no quotes or links.

  python scripts/public_data.py web/public/data/vacancies.json   # rewrites the file in place
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Same list as NON_ENGINEERING_TITLE in web/src/local/localApi.ts: these roles are dropped here because the
# generic title below no longer carries the words the browser filter looks for.
NON_ENGINEERING_TITLE = re.compile(
    r"\b(sales|business development|bizdev|account manager|account executive|delivery manager|project manager"
    r"|product manager|product owner|recruit\w*|marketing|marketer|hr|talent acquisition|customer success"
    r"|presale\w*)\b",
    re.IGNORECASE,
)

SENIORITY = {
    "intern": "Intern",
    "junior": "Junior",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead",
    "principal": "Principal",
}


def public_title(category: str | None, seniority: str | None) -> str:
    parts = [SENIORITY.get(seniority or ""), category or "IT", "role"]
    return " ".join(p for p in parts if p)


def anonymise(category: str | None, vacancy: dict, n: int) -> dict:
    v = {k: val for k, val in vacancy.items() if k not in ("parse", "source", "scraped_at")}
    v["id"] = f"v-{n}"
    v["url"] = ""
    v["title"] = public_title(category, v.get("seniority"))
    v["company"] = ""
    v["requirements"] = [{**r, "evidence": ""} for r in v["requirements"]]
    v["english"] = {**v["english"], "evidence": None}
    return v


def anonymise_all(items: list[dict]) -> list[dict]:
    kept = [x for x in items if not NON_ENGINEERING_TITLE.search(x["vacancy"].get("title") or "")]
    return [
        {"category": x["category"], "vacancy": anonymise(x["category"], x["vacancy"], n)}
        for n, x in enumerate(kept, start=1)
    ]


def main() -> None:
    path = Path(sys.argv[1])
    items = json.loads(path.read_text(encoding="utf-8"))
    out = anonymise_all(items)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{path}: {len(items)} -> {len(out)} vacancies")


if __name__ == "__main__":
    main()
