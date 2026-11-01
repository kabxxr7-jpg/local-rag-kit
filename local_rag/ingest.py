"""Ingest PDFs into the store. Running it twice on the same files changes nothing."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .chunk import chunk_pages
from .config import Config
from .embed import Embedder, get_embedder
from .errors import ConfigError, RagError
from .extract import extract_pdf
from .store import VectorStore


@dataclass
class IngestReport:
    ingested: dict[str, int] = field(default_factory=dict)  # file -> chunks stored
    unchanged: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # file -> plain-words reason
    removed_chunks: int = 0
    total_chunks: int = 0
    warnings: list[str] = field(default_factory=list)


def find_pdfs(paths: list[str | Path]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.extend(sorted(p.glob("*.pdf")))
        elif p.is_file():
            found.append(p)
        else:
            raise ConfigError(f"'{raw}' is neither a PDF file nor a folder.")
    names: dict[str, Path] = {}
    for p in found:
        if p.name in names and names[p.name].resolve() != p.resolve():
            raise ConfigError(f"Two different files are both called '{p.name}' ({names[p.name]} and {p}). Citations use the file name, so rename one of them.")
        names[p.name] = p
    return list(names.values())


def _signature(cfg: Config) -> dict[str, object]:
    """The settings that change what the chunks look like. A file is skipped as 'unchanged' only if these match too."""
    return {"chunk_size": cfg.chunk_size, "chunk_overlap": cfg.chunk_overlap, "extract_mode": cfg.extract_mode}


def ingest(paths: list[str | Path], cfg: Config, embedder: Embedder | None = None, rebuild: bool = False) -> IngestReport:
    pdfs = find_pdfs(paths)
    if not pdfs:
        raise ConfigError("No PDF files found in the given path(s).")
    embedder = embedder or get_embedder(cfg)
    store = VectorStore.open(cfg.store_dir)
    report = IngestReport()
    if rebuild:
        store.destroy()
    store.check_compatible(embedder.model)

    changed = False
    for pdf in pdfs:
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        known = store.files.get(pdf.name)
        if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
            report.unchanged.append(pdf.name)
            continue
        try:
            extraction = extract_pdf(pdf, cfg.extract_mode)
        except RagError as exc:
            report.failed[pdf.name] = str(exc)
            continue
        chunks = chunk_pages(extraction.pages, cfg)
        vectors = embedder.embed_documents([c.text for c in chunks])
        if not store.exists:
            store.create(embedder.model, len(vectors[0]))
        store.check_compatible(embedder.model, len(vectors[0]))
        report.removed_chunks += store.remove_source(pdf.name)
        store.add(chunks, vectors)
        store.files[pdf.name] = {"sha256": digest, "signature": _signature(cfg), "pages": extraction.page_count, "chunks": len(chunks)}
        report.ingested[pdf.name] = len(chunks)
        if extraction.empty_pages:
            report.warnings.append(f"{pdf.name}: page(s) {', '.join(map(str, extraction.empty_pages))} have no extractable text and were skipped.")
        changed = True
    if changed or rebuild:
        if store.exists:
            store.save()
    report.total_chunks = len(store)
    return report
