"""CV file bytes (PDF, DOCX, TXT) → plain text for the LLM.

No OCR: a PDF without a text layer (a scan) is rejected with ExtractError.
Error messages name the format and the exception type only; they never include text from the file.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

FORMATS = ("pdf", "docx", "txt")
MAX_TEXT_CHARS = 20_000  # same cap as the vacancy parser; no CV length statistics yet
MIN_TEXT_CHARS = 50  # non-whitespace characters; below this the file is treated as having no text (a scan, an empty form)


class ExtractError(ValueError):
    pass


@dataclass(frozen=True)
class CvText:
    text: str
    format: str
    chars: int  # length before the cap
    truncated: bool


def extract(data: bytes, fmt: str) -> CvText:
    if fmt not in FORMATS:
        raise ExtractError(f"unsupported format {fmt!r}; expected one of {', '.join(FORMATS)}")
    raw = {"pdf": _pdf_text, "docx": _docx_text, "txt": _txt_text}[fmt](data)
    text = _normalize(raw)
    if len(re.sub(r"\s", "", text)) < MIN_TEXT_CHARS:
        hint = "; a scanned PDF needs OCR, which this step does not do" if fmt == "pdf" else ""
        raise ExtractError(f"{fmt} has no extractable text{hint}")
    return CvText(text=text[:MAX_TEXT_CHARS], format=fmt, chars=len(text), truncated=len(text) > MAX_TEXT_CHARS)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractError("pdf is encrypted")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ExtractError:
        raise
    except Exception as exc:  # pypdf raises several types on broken files
        raise ExtractError(f"pdf could not be read: {type(exc).__name__}") from exc


def _docx_text(data: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # BadZipFile, KeyError, ValueError on broken or non-DOCX files
        raise ExtractError(f"docx could not be read: {type(exc).__name__}") from exc

    lines = [p.text for p in doc.paragraphs]
    # CV templates often put skills and dates into tables; one line per row, cells separated by " | "
    for table in doc.tables:
        for row in table.rows:
            cells = list(dict.fromkeys(c.text.strip() for c in row.cells))  # merged cells repeat
            lines.append(" | ".join(c for c in cells if c))
    return "\n".join(lines)


def _txt_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Ukrainian and Russian TXT files saved on Windows are often cp1251
        try:
            return data.decode("cp1251")
        except UnicodeDecodeError as exc:
            raise ExtractError("txt is neither UTF-8 nor cp1251") from exc


def _normalize(s: str) -> str:
    s = s.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in s.split("\n"))
    s = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", s).strip()
