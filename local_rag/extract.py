"""Text extraction with pypdf. Page numbers are kept: every extracted page knows its 1-based number.

OCR is not part of this kit: a PDF whose pages are pictures of text has nothing to extract and raises NoTextError.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .chunk import Page
from .clean import clean_text
from .errors import NoTextError


@dataclass
class Extraction:
    source: str
    page_count: int
    pages: list[Page] = field(default_factory=list)  # cleaned, only pages that have text
    empty_pages: list[int] = field(default_factory=list)  # 1-based numbers of pages with no extractable text


def _matrix_apply(cm: list[float], tm: list[float]) -> tuple[float, float]:
    """Position of a text fragment on the page: the text matrix combined with the current transformation matrix."""
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
    return x, y


def _lines_from_fragments(frags: list[tuple[float, float, str]], tolerance: float = 2.0) -> list[str]:
    lines: list[list[tuple[float, float, str]]] = []
    for frag in sorted(frags, key=lambda f: (-f[1], f[0])):
        if lines and abs(lines[-1][0][1] - frag[1]) <= tolerance:
            lines[-1].append(frag)
        else:
            lines.append([frag])
    return [" ".join(t.strip() for _, _, t in sorted(line, key=lambda f: f[0]) if t.strip()) for line in lines]


def _extract_columns(page) -> str:
    """Read a two column page column by column (left first), using where each fragment sits on the page.
    The split is the middle of the page, so a heading across both columns lands in the left column (known limit)."""
    frags: list[tuple[float, float, str]] = []

    def visitor(text, cm, tm, font_dict, font_size):  # noqa: ANN001 - signature fixed by pypdf
        if text and text.strip():
            x, y = _matrix_apply(cm, tm)
            frags.append((x, y, text))

    page.extract_text(visitor_text=visitor)
    middle = float(page.mediabox.width) / 2
    left = [f for f in frags if f[0] < middle]
    right = [f for f in frags if f[0] >= middle]
    return "\n".join(_lines_from_fragments(left)) + "\n\n" + "\n".join(_lines_from_fragments(right))


def extract_page_text(page, mode: str) -> str:
    if mode == "plain":
        return page.extract_text() or ""
    if mode == "layout":
        return page.extract_text(extraction_mode="layout") or ""
    if mode == "columns":
        return _extract_columns(page)
    raise ValueError(f"unknown extract mode {mode!r}")


def extract_pdf(path: str | Path, mode: str = "plain") -> Extraction:
    from pypdf import PdfReader

    path = Path(path)
    reader = PdfReader(str(path))
    result = Extraction(source=path.name, page_count=len(reader.pages))
    for number, page in enumerate(reader.pages, start=1):
        text = clean_text(extract_page_text(page, mode))
        if text:
            result.pages.append(Page(path.name, number, text))
        else:
            result.empty_pages.append(number)
    if not result.pages:
        raise NoTextError(
            f"'{path.name}' has {result.page_count} page(s) but none has extractable text. It is probably a scan or a picture of text. "
            f"This kit does not do OCR: run the file through an OCR tool first, then ingest the searchable PDF."
        )
    return result
