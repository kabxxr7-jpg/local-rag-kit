from __future__ import annotations

from dataclasses import replace

import pytest

from local_rag.ask import ask, retrieve
from local_rag.errors import StoreEmpty, StoreMismatch
from local_rag.ingest import ingest
from local_rag.prompt import REFUSAL_TEXT, SYSTEM
from local_rag.store import VectorStore
from local_rag.testing import FakeEmbedder, FakeLLM

from .conftest import SAMPLES, fake_config

LEAVE = "How many days of paid annual leave does each employee get per year?"
KETTLE = "What is the maximum fill level of the Aurora AK-200?"


def run(cfg, embedder, question, llm=None, **changes):
    return ask(question, replace(cfg, **changes) if changes else cfg, embedder=embedder, llm=llm or FakeLLM())


def test_a_question_the_documents_answer_gets_the_fact_and_its_page(ingested):
    cfg, emb, _ = ingested
    r = run(cfg, emb, LEAVE)
    assert not r.refused and r.reason is None
    assert "25 days" in r.answer
    assert r.citations[0] == ("harbor-pine-handbook.pdf", 2)


def test_each_known_fact_is_retrieved_from_the_right_file_and_page(ingested):
    cfg, emb, _ = ingested
    expected = {
        LEAVE: ("harbor-pine-handbook.pdf", 2),
        KETTLE: ("aurora-kettle-manual.pdf", 1),
        "How much does the Pro plan cost per month?": ("meridian-price-list.pdf", 1),
        "What is the code for ordering a spare limescale filter?": ("aurora-kettle-manual.pdf", 4),
        "In which countries are the data centres located?": ("meridian-price-list.pdf", 3),
        "Who is the trust person for raising harassment concerns?": ("harbor-pine-handbook.pdf", 4),
    }
    for question, where in expected.items():
        hits = retrieve(question, cfg, VectorStore.open(cfg.store_dir), emb)
        assert (hits[0].source, hits[0].page) == where, question


def test_below_the_threshold_the_answer_is_the_fixed_refusal_and_the_model_is_never_asked(ingested):
    cfg, emb, _ = ingested
    llm = FakeLLM()
    r = ask("What is the capital of Portugal?", cfg, embedder=emb, llm=llm)
    assert r.refused and r.reason == "below_threshold"
    assert r.answer == REFUSAL_TEXT == "I could not find an answer to that in the ingested documents."
    assert llm.prompts == [] and r.citations == [] and r.kept == []
    assert r.best_score is not None and r.best_score < cfg.min_score


def test_the_threshold_decides_both_ways(ingested):
    cfg, emb, _ = ingested
    best = run(cfg, emb, LEAVE).best_score
    assert best is not None
    assert run(cfg, emb, LEAVE, min_score=best - 0.01).refused is False
    assert run(cfg, emb, LEAVE, min_score=best + 0.01).refused is True
    assert run(cfg, emb, LEAVE, min_score=best).refused is False  # equal to the threshold is allowed


def test_passages_below_the_threshold_never_reach_the_prompt(ingested):
    cfg, emb, _ = ingested
    llm = FakeLLM()
    r = ask(LEAVE, replace(cfg, k=4), embedder=emb, llm=llm)
    assert len(r.hits) == 4
    usable = [h for h in r.hits if h.score >= cfg.min_score]
    assert 0 < len(usable) < 4
    assert r.kept == usable
    prompt = llm.prompts[0][1]
    for h in r.hits:
        assert (h.text in prompt) == (h.score >= cfg.min_score)


def test_the_prompt_the_model_sees_contains_the_best_passage_first(ingested):
    cfg, emb, _ = ingested
    llm = FakeLLM()
    r = ask(LEAVE, cfg, embedder=emb, llm=llm)
    system, user = llm.prompts[0]
    assert system == SYSTEM
    assert r.hits[0].text in user
    assert user.index(r.hits[0].text) < user.index(r.kept[-1].text) or len(r.kept) == 1
    assert "[1] (harbor-pine-handbook.pdf, page 2)" in user
    assert user.endswith(f"Question: {LEAVE}\nAnswer:")


def test_citations_are_the_files_and_pages_of_the_passages_in_the_prompt_without_repeats(ingested):
    cfg, emb, _ = ingested
    r = run(cfg, emb, LEAVE, k=8, min_score=0.0)
    pages = [(h.source, h.page) for h in r.kept]
    assert r.citations == list(dict.fromkeys(pages))
    assert len(r.citations) < len(pages) or len(set(pages)) == len(pages)


def test_when_the_model_declines_the_result_is_a_refusal_without_citations(ingested):
    cfg, emb, _ = ingested
    r = ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(reply="Well. " + REFUSAL_TEXT.upper()))
    assert r.refused and r.reason == "model_declined" and r.answer == REFUSAL_TEXT and r.citations == []


def test_a_reply_that_merely_mentions_other_words_is_an_answer(ingested):
    cfg, emb, _ = ingested
    r = ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(reply="25 days."))
    assert not r.refused and r.answer == "25 days." and r.citations


def test_too_many_passages_are_trimmed_visibly_and_the_citations_follow(ingested):
    cfg, emb, _ = ingested
    r = run(cfg, emb, LEAVE, k=8, min_score=0.0, num_ctx=700, num_predict=100)
    assert r.dropped and r.kept
    assert r.kept + r.dropped == r.hits
    assert r.est_tokens is not None and r.est_tokens <= r.budget_tokens
    assert any("Context trimmed" in w and "num_ctx=700" in w for w in r.warnings)
    cited = set(r.citations)
    assert cited == {(h.source, h.page) for h in r.kept}


def test_a_prompt_that_fits_has_no_warning(ingested):
    cfg, emb, _ = ingested
    r = run(cfg, emb, LEAVE)
    assert r.dropped == [] and r.warnings == []


def test_refuse_on_overflow_does_not_ask_the_model(ingested):
    cfg, emb, _ = ingested
    llm = FakeLLM()
    r = ask(LEAVE, replace(cfg, k=8, min_score=0.0, num_ctx=700, num_predict=100, on_overflow="refuse"), embedder=emb, llm=llm)
    assert r.refused and r.reason == "context_too_large" and llm.prompts == []
    assert any("do not fit into num_ctx=700" in w for w in r.warnings)


def test_a_server_that_reports_far_fewer_tokens_than_the_prompt_has_is_flagged(ingested):
    cfg, emb, _ = ingested
    r = ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(prompt_tokens=120))
    assert any("probably cut the prompt" in w and "120 tokens" in w for w in r.warnings)


def test_a_server_that_reports_the_window_size_is_flagged(ingested):
    cfg, emb, _ = ingested
    r = ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(prompt_tokens=cfg.num_ctx))
    assert any("probably cut the prompt" in w for w in r.warnings)
    r = ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(prompt_tokens=cfg.num_ctx - 8))
    assert any("probably cut the prompt" in w for w in r.warnings)


def test_a_plausible_token_count_is_not_flagged(ingested):
    cfg, emb, _ = ingested
    probe = FakeLLM()
    ask(LEAVE, cfg, embedder=emb, llm=probe)
    chars = len(probe.prompts[0][0]) + len(probe.prompts[0][1])
    for tokens in (int(chars / 4.0), int(chars / 3.0), int(chars / 5.0)):
        r = ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(prompt_tokens=tokens))
        assert r.warnings == [], tokens
    assert ask(LEAVE, cfg, embedder=emb, llm=FakeLLM(prompt_tokens=int(chars / 6.0))).warnings


def test_k_limits_how_many_passages_are_retrieved(ingested):
    cfg, emb, _ = ingested
    assert len(run(cfg, emb, LEAVE, k=1).hits) == 1
    assert len(run(cfg, emb, LEAVE, k=3).hits) == 3


def test_empty_store_is_a_plain_error(cfg, embedder):
    with pytest.raises(StoreEmpty, match="Ingest some PDFs first"):
        ask("anything?", cfg, embedder=embedder, llm=FakeLLM())


def test_asking_with_another_embedding_model_is_refused_before_embedding(ingested):
    cfg, _, _ = ingested
    other = FakeEmbedder(dim=256, model="some-other-model")
    with pytest.raises(StoreMismatch, match=r"built with the embedding model 'fake-embed'.*'some-other-model'.*--rebuild"):
        ask(LEAVE, cfg, embedder=other, llm=FakeLLM())
    assert other.calls == 0


def test_same_name_but_other_dimension_is_a_plain_error_not_a_crash(ingested):
    cfg, _, _ = ingested
    wide = FakeEmbedder(dim=512, model="fake-embed")
    with pytest.raises(StoreMismatch, match="512 dimensions but the store holds 256"):
        ask(LEAVE, cfg, embedder=wide, llm=FakeLLM())


def test_ask_builds_its_own_store_embedder_and_model_from_the_settings(tmp_path):
    cfg = fake_config(tmp_path / "s")
    ingest([SAMPLES], cfg)
    r = ask(LEAVE, cfg)
    assert "25 days" in r.answer and r.citations[0][1] == 2
