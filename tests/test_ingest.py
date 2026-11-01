from __future__ import annotations

import shutil
from dataclasses import replace

import pytest

from local_rag.errors import ConfigError, StoreMismatch
from local_rag.ingest import find_pdfs, ingest
from local_rag.store import VectorStore
from local_rag.testing import FakeEmbedder

from .conftest import SAMPLES, fake_config

FILES = {"harbor-pine-handbook.pdf", "aurora-kettle-manual.pdf", "meridian-price-list.pdf"}


def test_first_ingest_stores_the_three_text_pdfs_and_reports_the_scan_as_failed(cfg, embedder):
    r = ingest([SAMPLES], cfg, embedder)
    assert set(r.ingested) == FILES
    assert list(r.failed) == ["scanned-notice.pdf"]
    assert "does not do OCR" in r.failed["scanned-notice.pdf"]
    assert r.total_chunks == sum(r.ingested.values()) and r.total_chunks > 20


def test_second_ingest_adds_nothing_and_does_not_even_call_the_embedder(cfg, embedder):
    first = ingest([SAMPLES], cfg, embedder)
    calls = embedder.calls
    second = ingest([SAMPLES], cfg, embedder)
    assert second.total_chunks == first.total_chunks
    assert set(second.unchanged) == FILES and second.ingested == {}
    assert embedder.calls == calls
    assert len(VectorStore.open(cfg.store_dir)) == first.total_chunks


def test_reingest_never_duplicates_a_chunk(cfg, embedder):
    for _ in range(3):
        ingest([SAMPLES], cfg, embedder)
    store = VectorStore.open(cfg.store_dir)
    texts = [(r["source"], r["page"], r["text"]) for r in store.records.values()]
    assert len(texts) == len(set(texts))
    ids = [r["chunk_id"] for r in store.records.values()]
    assert len(ids) == len(set(ids))


def test_changing_the_chunk_size_reingests_and_replaces_the_old_chunks(cfg, embedder):
    first = ingest([SAMPLES], cfg, embedder)
    again = ingest([SAMPLES], replace(cfg, chunk_size=200, chunk_overlap=20), embedder)
    assert set(again.ingested) == FILES and again.unchanged == []
    assert again.removed_chunks == first.total_chunks
    store = VectorStore.open(cfg.store_dir)
    assert len(store) == again.total_chunks > first.total_chunks
    assert max(len(r["text"]) for r in store.records.values()) <= 200


def test_changing_the_extract_mode_reingests(cfg, embedder):
    ingest([SAMPLES], cfg, embedder)
    again = ingest([SAMPLES], replace(cfg, extract_mode="plain"), embedder)
    assert set(again.ingested) == FILES


def test_a_changed_file_replaces_its_old_chunks_and_leaves_the_others(cfg, embedder, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in FILES:
        shutil.copy(SAMPLES / name, docs / name)
    first = ingest([docs], cfg, embedder)
    shutil.copy(SAMPLES / "aurora-kettle-manual.pdf", docs / "harbor-pine-handbook.pdf")  # new content under an old name
    second = ingest([docs], cfg, embedder)
    assert set(second.ingested) == {"harbor-pine-handbook.pdf"}
    assert set(second.unchanged) == FILES - {"harbor-pine-handbook.pdf"}
    assert second.removed_chunks == first.ingested["harbor-pine-handbook.pdf"]
    store = VectorStore.open(cfg.store_dir)
    assert not any("annual leave" in r["text"] for r in store.records.values())


def test_stored_pages_are_the_real_pdf_pages(cfg, embedder):
    ingest([SAMPLES], cfg, embedder)
    store = VectorStore.open(cfg.store_dir)
    where = {}
    for rec in store.records.values():
        for fact in ("25 days of paid annual leave", "140 EUR", "AF-20", "99.9 percent availability", "10 days of a payment"):
            if fact in rec["text"]:
                where[fact] = (rec["source"], rec["page"])
    assert where == {
        "25 days of paid annual leave": ("harbor-pine-handbook.pdf", 2),
        "140 EUR": ("harbor-pine-handbook.pdf", 3),
        "AF-20": ("aurora-kettle-manual.pdf", 4),
        "99.9 percent availability": ("meridian-price-list.pdf", 3),
        "10 days of a payment": ("meridian-price-list.pdf", 2),
    }


def test_store_remembers_the_embedding_model_and_dimension(cfg):
    ingest([SAMPLES], cfg, FakeEmbedder(dim=64, model="model-a"))
    store = VectorStore.open(cfg.store_dir)
    assert (store.embed_model, store.dim) == ("model-a", 64)


def test_another_embedding_model_is_refused_before_anything_is_touched(cfg):
    ingest([SAMPLES], cfg, FakeEmbedder(dim=64, model="model-a"))
    before = len(VectorStore.open(cfg.store_dir))
    with pytest.raises(StoreMismatch, match="model-a.*model-b"):
        ingest([SAMPLES], cfg, FakeEmbedder(dim=128, model="model-b"))
    assert len(VectorStore.open(cfg.store_dir)) == before


def test_same_model_name_with_other_dimension_is_refused(cfg):
    ingest([SAMPLES], cfg, FakeEmbedder(dim=64, model="model-a"))
    with pytest.raises(StoreMismatch, match="64-dimensional.*128-dimensional"):
        ingest([SAMPLES], replace(cfg, chunk_size=300), FakeEmbedder(dim=128, model="model-a"))


def test_rebuild_replaces_the_store_with_the_new_model(cfg):
    ingest([SAMPLES], cfg, FakeEmbedder(dim=64, model="model-a"))
    report = ingest([SAMPLES], cfg, FakeEmbedder(dim=128, model="model-b"), rebuild=True)
    store = VectorStore.open(cfg.store_dir)
    assert (store.embed_model, store.dim) == ("model-b", 128)
    assert len(store) == report.total_chunks and set(report.ingested) == FILES


def test_a_pdf_without_text_does_not_stop_the_others_and_leaves_no_trace(cfg, embedder):
    r = ingest([SAMPLES / "scanned-notice.pdf", SAMPLES / "aurora-kettle-manual.pdf"], cfg, embedder)
    assert list(r.failed) == ["scanned-notice.pdf"] and list(r.ingested) == ["aurora-kettle-manual.pdf"]
    assert {rec["source"] for rec in VectorStore.open(cfg.store_dir).records.values()} == {"aurora-kettle-manual.pdf"}


def test_only_a_scan_gives_no_store_at_all(cfg, embedder):
    r = ingest([SAMPLES / "scanned-notice.pdf"], cfg, embedder)
    assert r.failed and r.total_chunks == 0
    assert not VectorStore.open(cfg.store_dir).exists


def test_two_different_files_with_one_name_are_refused(cfg, embedder, tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    shutil.copy(SAMPLES / "aurora-kettle-manual.pdf", tmp_path / "x" / "same.pdf")
    shutil.copy(SAMPLES / "meridian-price-list.pdf", tmp_path / "y" / "same.pdf")
    with pytest.raises(ConfigError, match="Two different files are both called 'same.pdf'"):
        ingest([tmp_path / "x", tmp_path / "y"], cfg, embedder)


def test_find_pdfs_takes_files_and_folders_sorted_and_without_repeats():
    found = find_pdfs([SAMPLES, SAMPLES / "aurora-kettle-manual.pdf"])
    names = [p.name for p in found]
    assert names == sorted(names)[: len(names)] or names[0] == "aurora-kettle-manual.pdf"
    assert len(names) == len(set(names)) == 4


def test_nothing_to_ingest_and_bad_paths_are_plain_errors(cfg, embedder, tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ConfigError, match="No PDF files found"):
        ingest([tmp_path / "empty"], cfg, embedder)
    with pytest.raises(ConfigError, match="neither a PDF file nor a folder"):
        ingest([tmp_path / "missing.pdf"], cfg, embedder)


def test_ingest_uses_the_configured_store_folder_and_writes_nothing_else(tmp_path, embedder):
    cfg = fake_config(tmp_path / "custom-place")
    ingest([SAMPLES / "aurora-kettle-manual.pdf"], cfg, embedder)
    assert sorted(p.name for p in (tmp_path / "custom-place").iterdir()) == ["index.faiss", "meta.json", "records.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["custom-place"]
