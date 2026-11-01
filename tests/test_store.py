from __future__ import annotations

import json

import numpy as np
import pytest

from local_rag.chunk import Chunk
from local_rag.errors import StoreEmpty, StoreMismatch
from local_rag.store import VectorStore


def chunk(n: int, source: str = "a.pdf", page: int = 1, text: str | None = None) -> Chunk:
    return Chunk(f"id{n}-{source}", source, page, n, text or f"text {n}")


def unit(dim: int, hot: int) -> list[float]:
    v = [0.0] * dim
    v[hot] = 1.0
    return v


@pytest.fixture
def store(tmp_path):
    s = VectorStore.open(tmp_path / "s")
    s.create("model-a", 4)
    return s


def test_a_folder_without_a_store_opens_as_empty(tmp_path):
    s = VectorStore.open(tmp_path / "nothing")
    assert not s.exists and len(s) == 0


def test_search_returns_best_first_with_cosine_scores_and_metadata(store):
    store.add([chunk(0, page=1), chunk(1, page=2), chunk(2, page=3)], [unit(4, 0), unit(4, 1), [1.0, 1.0, 0.0, 0.0]])
    hits = store.search(unit(4, 0), 3)
    assert [h.page for h in hits] == [1, 3, 2]
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(2 ** -0.5, abs=1e-5)
    assert hits[2].score == pytest.approx(0.0, abs=1e-6)
    assert (hits[0].source, hits[0].index, hits[0].text) == ("a.pdf", 0, "text 0")


def test_scores_do_not_depend_on_vector_length(store):
    store.add([chunk(0)], [[10.0, 0.0, 0.0, 0.0]])
    assert store.search([0.001, 0, 0, 0], 1)[0].score == pytest.approx(1.0)


def test_k_larger_than_the_store_returns_everything(store):
    store.add([chunk(0), chunk(1)], [unit(4, 0), unit(4, 1)])
    assert len(store.search(unit(4, 0), 50)) == 2


def test_save_and_open_round_trip(store, tmp_path):
    store.add([chunk(0, text="hello"), chunk(1, page=7)], [unit(4, 0), unit(4, 1)])
    store.files["a.pdf"] = {"sha256": "x"}
    store.save()
    again = VectorStore.open(tmp_path / "s")
    assert again.embed_model == "model-a" and again.dim == 4 and len(again) == 2
    assert again.files == {"a.pdf": {"sha256": "x"}}
    assert again.search(unit(4, 1), 1)[0].page == 7
    assert sorted(p.name for p in (tmp_path / "s").iterdir()) == ["index.faiss", "meta.json", "records.json"]


def test_adding_the_same_chunk_twice_stores_it_once(store):
    c = chunk(0)
    assert store.add([c], [unit(4, 0)]) == 1
    assert store.add([c], [unit(4, 0)]) == 0
    assert len(store) == 1


def test_remove_source_removes_vectors_and_records_but_only_that_file(store):
    store.add([chunk(0, "a.pdf"), chunk(1, "a.pdf"), chunk(0, "b.pdf")], [unit(4, 0), unit(4, 1), unit(4, 2)])
    store.files["a.pdf"] = {}
    assert store.remove_source("a.pdf") == 2
    assert len(store) == 1 and "a.pdf" not in store.files
    assert [h.source for h in store.search(unit(4, 0), 5)] == ["b.pdf"]
    assert store.remove_source("a.pdf") == 0


def test_ids_are_not_reused_after_a_removal(store):
    store.add([chunk(0, "a.pdf")], [unit(4, 0)])
    store.remove_source("a.pdf")
    store.add([chunk(0, "b.pdf")], [unit(4, 1)])
    assert list(store.records) == [2]


def test_search_with_wrong_dimension_is_a_plain_error_not_a_crash(store):
    store.add([chunk(0)], [unit(4, 0)])
    with pytest.raises(StoreMismatch, match=r"embedded into 8 dimensions.*holds 4-dimensional.*--rebuild"):
        store.search(unit(8, 0), 1)


def test_adding_vectors_of_the_wrong_dimension_is_refused(store):
    with pytest.raises(StoreMismatch, match="8-dimensional vectors to a 4-dimensional store"):
        store.add([chunk(0)], [unit(8, 0)])


def test_add_requires_matching_lengths(store):
    with pytest.raises(ValueError):
        store.add([chunk(0), chunk(1)], [unit(4, 0)])


def test_check_compatible_names_both_models_and_the_way_out(store):
    store.add([chunk(0)], [unit(4, 0)])
    store.check_compatible("model-a")
    store.check_compatible("model-a", 4)
    with pytest.raises(StoreMismatch, match=r"built with the embedding model 'model-a' \(4 dimensions\).*'model-b'.*--rebuild"):
        store.check_compatible("model-b")
    with pytest.raises(StoreMismatch, match="4-dimensional vectors but .* returns 9-dimensional"):
        store.check_compatible("model-a", 9)


def test_check_compatible_is_silent_for_a_store_that_does_not_exist_yet(tmp_path):
    VectorStore.open(tmp_path / "new").check_compatible("anything", 3)


def test_empty_store_says_to_ingest_first(store, tmp_path):
    with pytest.raises(StoreEmpty, match="Ingest some PDFs first"):
        store.search(unit(4, 0), 1)
    with pytest.raises(StoreEmpty):
        VectorStore.open(tmp_path / "none").search(unit(4, 0), 1)


def test_destroy_deletes_only_the_three_store_files(store, tmp_path):
    store.add([chunk(0)], [unit(4, 0)])
    store.save()
    (tmp_path / "s" / "keep.txt").write_text("mine")
    store.destroy()
    assert [p.name for p in (tmp_path / "s").iterdir()] == ["keep.txt"]
    assert not store.exists and len(store) == 0


def test_unknown_format_is_refused_with_a_way_out(store, tmp_path):
    store.add([chunk(0)], [unit(4, 0)])
    store.save()
    meta = json.loads((tmp_path / "s" / "meta.json").read_text())
    meta["format"] = 99
    (tmp_path / "s" / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(StoreMismatch, match="format 99"):
        VectorStore.open(tmp_path / "s")


def test_index_that_disagrees_with_meta_is_reported_as_damaged(store, tmp_path):
    store.add([chunk(0)], [unit(4, 0)])
    store.save()
    meta = json.loads((tmp_path / "s" / "meta.json").read_text())
    meta["dim"] = 5
    (tmp_path / "s" / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(StoreMismatch, match="damaged"):
        VectorStore.open(tmp_path / "s")


def test_stats_counts_chunks_per_file(store):
    store.add([chunk(0, "a.pdf"), chunk(1, "a.pdf"), chunk(0, "b.pdf")], [unit(4, 0), unit(4, 1), unit(4, 2)])
    assert store.stats() == {"embed_model": "model-a", "dim": 4, "chunks": 3, "files": {"a.pdf": 2, "b.pdf": 1}}


def test_zero_vector_does_not_produce_nan(store):
    store.add([chunk(0)], [[0.0, 0.0, 0.0, 0.0]])
    assert not np.isnan(store.search([0.0, 0.0, 0.0, 0.0], 1)[0].score)
