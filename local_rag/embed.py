"""Embedding. The real embedder talks to Ollama through langchain-ollama; the fake one lives in testing.py."""
from __future__ import annotations

from typing import Protocol

from .config import Config
from .ollama_util import explain_ollama_errors

BATCH = 16


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    def __init__(self, cfg: Config):
        from langchain_ollama import OllamaEmbeddings

        self.model = cfg.embed_model
        self._host = cfg.ollama_host
        self._doc_prefix = cfg.embed_doc_prefix
        self._query_prefix = cfg.embed_query_prefix
        extra = {"dimensions": cfg.embed_dimensions} if cfg.embed_dimensions > 0 else {}
        self._inner = OllamaEmbeddings(model=cfg.embed_model, base_url=cfg.ollama_host, client_kwargs={"timeout": cfg.request_timeout}, **extra)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        with explain_ollama_errors(self._host, self.model):
            for start in range(0, len(texts), BATCH):
                batch = [self._doc_prefix + t for t in texts[start : start + BATCH]]
                out.extend(self._inner.embed_documents(batch))
        return out

    def embed_query(self, text: str) -> list[float]:
        with explain_ollama_errors(self._host, self.model):
            return self._inner.embed_query(self._query_prefix + text)


def get_embedder(cfg: Config) -> Embedder:
    if cfg.embedder == "fake":
        from .testing import FakeEmbedder

        return FakeEmbedder(dim=cfg.fake_dim, model=cfg.embed_model)
    return OllamaEmbedder(cfg)
