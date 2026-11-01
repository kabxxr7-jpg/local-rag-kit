"""A small persistent vector store: a faiss index plus two JSON files, all inside one folder.

    meta.json      which embedding model built it, how many dimensions, which settings each file was ingested with
    records.json   the text, file name and page of every vector
    index.faiss    the vectors (cosine similarity: vectors are normalised, the index is an inner product index)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .errors import StoreEmpty, StoreMismatch

FORMAT = 1
FILES = ("meta.json", "records.json", "index.faiss")


@dataclass
class Hit:
    score: float
    chunk_id: str
    source: str
    page: int
    index: int
    text: str


def _normalise(matrix: np.ndarray) -> np.ndarray:
    matrix = np.ascontiguousarray(matrix, dtype="float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


@dataclass
class VectorStore:
    path: Path
    embed_model: str | None = None
    dim: int | None = None
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    records: dict[int, dict[str, Any]] = field(default_factory=dict)
    next_id: int = 1
    _index: Any = None

    # ---- open / create ------------------------------------------------------------------------------------------
    @classmethod
    def open(cls, path: str | os.PathLike) -> "VectorStore":
        """Open the store in ``path``. A folder with no store in it gives an empty, not yet created store."""
        import faiss

        path = Path(path)
        store = cls(path=path)
        meta_file = path / "meta.json"
        if not meta_file.exists():
            return store
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if meta.get("format") != FORMAT:
            raise StoreMismatch(f"The store in '{path}' has format {meta.get('format')!r}; this version reads format {FORMAT}. Rebuild it with: python -m local_rag ingest --rebuild <pdfs>")
        store.embed_model = meta["embed_model"]
        store.dim = int(meta["dim"])
        store.files = meta.get("files", {})
        store.next_id = int(meta.get("next_id", 1))
        raw = json.loads((path / "records.json").read_text(encoding="utf-8"))
        store.records = {int(k): v for k, v in raw.items()}
        store._index = faiss.read_index(str(path / "index.faiss"))
        if store._index.d != store.dim:
            raise StoreMismatch(f"The store in '{path}' is damaged: meta.json says {store.dim} dimensions, the index has {store._index.d}. Rebuild it with --rebuild.")
        return store

    @property
    def exists(self) -> bool:
        return self.dim is not None

    def create(self, embed_model: str, dim: int) -> None:
        import faiss

        self.embed_model = embed_model
        self.dim = dim
        self.files = {}
        self.records = {}
        self.next_id = 1
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))

    def destroy(self) -> None:
        """Delete the three store files (and nothing else in the folder)."""
        for name in FILES:
            (self.path / name).unlink(missing_ok=True)
        self.embed_model = None
        self.dim = None
        self.files = {}
        self.records = {}
        self.next_id = 1
        self._index = None

    # ---- guards -------------------------------------------------------------------------------------------------
    def check_compatible(self, embed_model: str, dim: int | None = None) -> None:
        if not self.exists:
            return
        if embed_model != self.embed_model:
            raise StoreMismatch(
                f"The store was built with the embedding model '{self.embed_model}' ({self.dim} dimensions) but the configured model is '{embed_model}'. "
                f"Vectors from different models cannot be compared. Either set embed_model back to '{self.embed_model}', or rebuild the store: "
                f"python -m local_rag ingest --rebuild <pdfs>"
            )
        if dim is not None and dim != self.dim:
            raise StoreMismatch(
                f"The store holds {self.dim}-dimensional vectors but the embedding model '{embed_model}' now returns {dim}-dimensional ones "
                f"(the model was probably replaced by another build under the same name). Rebuild the store: python -m local_rag ingest --rebuild <pdfs>"
            )

    # ---- write --------------------------------------------------------------------------------------------------
    def remove_source(self, source: str) -> int:
        ids = [i for i, rec in self.records.items() if rec["source"] == source]
        if ids:
            self._index.remove_ids(np.array(ids, dtype="int64"))
            for i in ids:
                del self.records[i]
        self.files.pop(source, None)
        return len(ids)

    def add(self, chunks: list, vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if not chunks:
            return 0
        matrix = _normalise(np.array(vectors, dtype="float32"))
        if matrix.shape[1] != self.dim:
            raise StoreMismatch(f"Cannot add {matrix.shape[1]}-dimensional vectors to a {self.dim}-dimensional store.")
        known = {rec["chunk_id"] for rec in self.records.values()}
        keep = [n for n, c in enumerate(chunks) if c.id not in known]
        if not keep:
            return 0
        ids = np.arange(self.next_id, self.next_id + len(keep), dtype="int64")
        self._index.add_with_ids(matrix[keep], ids)
        for new_id, n in zip(ids.tolist(), keep):
            c = chunks[n]
            self.records[new_id] = {"chunk_id": c.id, "source": c.source, "page": c.page, "index": c.index, "text": c.text}
        self.next_id += len(keep)
        return len(keep)

    def save(self) -> None:
        import faiss

        self.path.mkdir(parents=True, exist_ok=True)
        meta = {"format": FORMAT, "embed_model": self.embed_model, "dim": self.dim, "next_id": self.next_id, "files": self.files}
        for name, payload in (("meta.json", meta), ("records.json", {str(k): v for k, v in self.records.items()})):
            tmp = self.path / (name + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path / name)
        tmp = self.path / "index.faiss.tmp"
        faiss.write_index(self._index, str(tmp))
        os.replace(tmp, self.path / "index.faiss")

    # ---- read ---------------------------------------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.records)

    def search(self, vector: list[float], k: int) -> list[Hit]:
        if not self.exists or len(self.records) == 0:
            raise StoreEmpty("The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>")
        query = _normalise(np.array([vector], dtype="float32"))
        if query.shape[1] != self.dim:
            raise StoreMismatch(
                f"The question was embedded into {query.shape[1]} dimensions but the store holds {self.dim}-dimensional vectors "
                f"(built with '{self.embed_model}'). Rebuild the store: python -m local_rag ingest --rebuild <pdfs>"
            )
        scores, ids = self._index.search(query, min(k, len(self.records)))
        hits = []
        for score, i in zip(scores[0].tolist(), ids[0].tolist()):
            if i < 0:
                continue
            rec = self.records[i]
            hits.append(Hit(float(score), rec["chunk_id"], rec["source"], rec["page"], rec["index"], rec["text"]))
        return hits

    def stats(self) -> dict[str, Any]:
        per_file: dict[str, int] = {}
        for rec in self.records.values():
            per_file[rec["source"]] = per_file.get(rec["source"], 0) + 1
        return {"embed_model": self.embed_model, "dim": self.dim, "chunks": len(self.records), "files": per_file}
