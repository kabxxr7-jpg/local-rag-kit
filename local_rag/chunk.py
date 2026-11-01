"""Chunking. Pages are split one at a time so that every chunk knows its page without guessing."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import Config


@dataclass(frozen=True)
class Page:
    source: str  # file name, for example "handbook.pdf"
    page: int  # 1-based, as printed by a PDF viewer
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    page: int
    index: int  # position inside the page, starting at 0
    text: str


def chunk_id(source: str, page: int, index: int, text: str) -> str:
    """Same input, same id: this is what makes a second ingest of the same file a no-op."""
    return hashlib.sha256(f"{source}\x00{page}\x00{index}\x00{text}".encode("utf-8")).hexdigest()[:24]


def make_splitter(cfg: Config):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_pages(pages: list[Page], cfg: Config) -> list[Chunk]:
    splitter = make_splitter(cfg)
    chunks: list[Chunk] = []
    for page in pages:
        for index, piece in enumerate(splitter.split_text(page.text)):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(Chunk(chunk_id(page.source, page.page, index, piece), page.source, page.page, index, piece))
    return chunks
