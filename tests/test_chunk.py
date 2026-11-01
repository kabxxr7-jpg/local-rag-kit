from __future__ import annotations

from dataclasses import replace

from local_rag.chunk import Page, chunk_id, chunk_pages
from local_rag.config import Config

TEXT_A = " ".join(f"Sentence number {i} is about apples and pears." for i in range(40))
TEXT_B = " ".join(f"Line {i} talks about kettles and tea." for i in range(40))


def test_chunk_id_is_deterministic_and_depends_on_every_part():
    base = chunk_id("a.pdf", 1, 0, "text")
    assert base == chunk_id("a.pdf", 1, 0, "text")
    assert len({base, chunk_id("b.pdf", 1, 0, "text"), chunk_id("a.pdf", 2, 0, "text"), chunk_id("a.pdf", 1, 1, "text"), chunk_id("a.pdf", 1, 0, "other")}) == 5
    assert len(base) == 24


def test_every_chunk_keeps_file_and_one_based_page():
    cfg = Config(chunk_size=300, chunk_overlap=40)
    chunks = chunk_pages([Page("a.pdf", 1, TEXT_A), Page("a.pdf", 2, TEXT_B)], cfg)
    assert {c.page for c in chunks} == {1, 2}
    assert all(c.source == "a.pdf" for c in chunks)
    assert all("apples" in c.text for c in chunks if c.page == 1)
    assert all("kettles" in c.text for c in chunks if c.page == 2)


def test_no_chunk_is_longer_than_chunk_size():
    cfg = Config(chunk_size=300, chunk_overlap=40)
    chunks = chunk_pages([Page("a.pdf", 1, TEXT_A)], cfg)
    assert len(chunks) > 3
    assert max(len(c.text) for c in chunks) <= 300


def test_index_counts_chunks_inside_each_page_from_zero():
    cfg = Config(chunk_size=300, chunk_overlap=40)
    chunks = chunk_pages([Page("a.pdf", 1, TEXT_A), Page("a.pdf", 2, TEXT_B)], cfg)
    for page in (1, 2):
        indexes = [c.index for c in chunks if c.page == page]
        assert indexes == list(range(len(indexes)))


def test_neighbouring_chunks_share_text_when_overlap_is_set():
    with_overlap = chunk_pages([Page("a.pdf", 1, TEXT_A)], Config(chunk_size=300, chunk_overlap=100))
    shared = [a.text[-30:] in b.text for a, b in zip(with_overlap, with_overlap[1:])]
    assert any(shared)
    no_overlap = chunk_pages([Page("a.pdf", 1, TEXT_A)], Config(chunk_size=300, chunk_overlap=0))
    assert not any(a.text[-30:] in b.text for a, b in zip(no_overlap, no_overlap[1:]))


def test_chunk_settings_change_the_number_of_chunks():
    small = chunk_pages([Page("a.pdf", 1, TEXT_A)], Config(chunk_size=200, chunk_overlap=0))
    large = chunk_pages([Page("a.pdf", 1, TEXT_A)], Config(chunk_size=1000, chunk_overlap=0))
    assert len(small) > len(large) >= 2


def test_a_short_page_is_one_chunk():
    chunks = chunk_pages([Page("a.pdf", 3, "One short page.")], Config())
    assert [(c.page, c.index, c.text) for c in chunks] == [(3, 0, "One short page.")]


def test_pages_are_never_mixed_into_one_chunk():
    cfg = replace(Config(), chunk_size=5000, chunk_overlap=0)
    chunks = chunk_pages([Page("a.pdf", 1, "alpha text"), Page("a.pdf", 2, "beta text")], cfg)
    assert [(c.page, c.text) for c in chunks] == [(1, "alpha text"), (2, "beta text")]


def test_identical_text_on_two_pages_gets_two_ids():
    chunks = chunk_pages([Page("a.pdf", 1, "same words"), Page("a.pdf", 2, "same words")], Config())
    assert len({c.id for c in chunks}) == 2


def test_empty_pages_give_no_chunks():
    assert chunk_pages([Page("a.pdf", 1, "   ")], Config()) == []
