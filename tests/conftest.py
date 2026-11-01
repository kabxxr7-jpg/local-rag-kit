from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from local_rag.config import Config
from local_rag.ingest import ingest
from local_rag.testing import FakeEmbedder, FakeLLM

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples" / "pdfs"
SCENARIO_PDFS = ROOT / "scenarios" / "pdfs"
QUESTIONS = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))


def fake_config(store_dir: Path, **changes) -> Config:
    """Offline settings: the fake embedder and fake model, a store in a temp folder. min_score is lower than the real
    default because the hashed bag-of-words scores are on another scale than nomic-embed-text."""
    base = Config(embedder="fake", llm="fake", store_dir=str(store_dir), min_score=0.30, k=4, chunk_size=500, chunk_overlap=80)
    return replace(base, **changes)


@pytest.fixture
def cfg(tmp_path) -> Config:
    return fake_config(tmp_path / "store")


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dim=256)


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def ingested(cfg, embedder):
    """A store with the three fictional PDFs ingested (the scanned one fails on purpose and is reported, not stored)."""
    report = ingest([SAMPLES], cfg, embedder)
    assert set(report.ingested) == {"harbor-pine-handbook.pdf", "aurora-kettle-manual.pdf", "meridian-price-list.pdf"}
    return cfg, embedder, report
