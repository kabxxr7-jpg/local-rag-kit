from __future__ import annotations

from dataclasses import replace

from local_rag.config import Config
from local_rag.prompt import REFUSAL_TEXT, SYSTEM, TEMPLATE_RESERVE_TOKENS, assemble, estimate_tokens, format_passage, render, token_budget
from local_rag.store import Hit


def hit(n: int, score: float, text: str | None = None, source: str = "a.pdf", page: int = 1) -> Hit:
    return Hit(score, f"id{n}", source, page, n, text or f"passage text number {n}")


def test_refusal_text_is_the_fixed_sentence_and_the_prompt_asks_for_exactly_it():
    assert REFUSAL_TEXT == "I could not find an answer to that in the ingested documents."
    assert REFUSAL_TEXT in SYSTEM
    assert "ONLY" in SYSTEM


def test_estimate_rounds_up_and_uses_the_ratio():
    assert estimate_tokens("x" * 9, 3.0) == 3
    assert estimate_tokens("x" * 10, 3.0) == 4
    assert estimate_tokens("x" * 10, 5.0) == 2
    assert estimate_tokens("", 3.0) == 0


def test_budget_is_the_window_minus_the_answer_and_the_template():
    c = Config(num_ctx=4096, num_predict=256)
    assert token_budget(c) == 4096 - 256 - TEMPLATE_RESERVE_TOKENS
    assert token_budget(replace(c, num_ctx=2048)) == 2048 - 256 - TEMPLATE_RESERVE_TOKENS


def test_passages_are_numbered_from_one_and_name_file_and_page():
    text = render("Why?", [hit(0, 0.9, "alpha", "x.pdf", 3), hit(1, 0.8, "beta", "y.pdf", 7)])
    assert "[1] (x.pdf, page 3)\nalpha" in text
    assert "[2] (y.pdf, page 7)\nbeta" in text
    assert text.index("alpha") < text.index("beta")
    assert text.endswith("Question: Why?\nAnswer:")
    assert format_passage(5, hit(0, 0.5, "t", "f.pdf", 2)) == "[5] (f.pdf, page 2)\nt"


def test_everything_that_fits_is_kept_in_order():
    hits = [hit(0, 0.9), hit(1, 0.8), hit(2, 0.7)]
    p = assemble("q?", hits, Config())
    assert p.kept == hits and p.dropped == []
    assert p.est_tokens <= p.budget_tokens
    for h in hits:
        assert h.text in p.user
    assert p.system == SYSTEM


def test_the_lowest_ranked_passages_are_dropped_first_and_reported():
    big = "word " * 400  # about 2000 characters
    hits = [hit(0, 0.9, "BEST " + big), hit(1, 0.8, "SECOND " + big), hit(2, 0.7, "THIRD " + big), hit(3, 0.6, "FOURTH " + big)]
    cfg = Config(num_ctx=1200, num_predict=100, chars_per_token=3.0)  # budget about 1036 tokens = 3100 characters
    p = assemble("q?", hits, cfg)
    assert [h.text.split()[0] for h in p.kept] == ["BEST"]
    assert [h.text.split()[0] for h in p.dropped] == ["SECOND", "THIRD", "FOURTH"]
    assert "BEST" in p.user and "SECOND" not in p.user and "FOURTH" not in p.user
    assert p.est_tokens <= p.budget_tokens


def test_what_is_kept_is_a_prefix_of_the_ranking():
    big = "word " * 150
    hits = [hit(n, 1 - n / 10, f"P{n} " + big) for n in range(8)]
    p = assemble("q?", hits, Config(num_ctx=1000, num_predict=100))
    assert p.kept == hits[: len(p.kept)] and p.dropped == hits[len(p.kept) :]
    assert 0 < len(p.kept) < 8
    assert p.est_tokens <= p.budget_tokens


def test_refuse_mode_gives_up_instead_of_cutting():
    hits = [hit(0, 0.9, "x" * 1500), hit(1, 0.8, "y" * 1500)]
    cfg = Config(num_ctx=1000, num_predict=100, on_overflow="refuse")
    assert assemble("q?", hits, cfg) is None
    assert assemble("q?", hits, replace(cfg, on_overflow="trim")) is not None


def test_refuse_mode_still_answers_when_everything_fits():
    p = assemble("q?", [hit(0, 0.9)], Config(on_overflow="refuse"))
    assert p is not None and p.dropped == []


def test_nothing_fits_when_even_the_best_passage_is_too_big():
    assert assemble("q?", [hit(0, 0.9, "x" * 20000)], Config(num_ctx=1000, num_predict=100)) is None


def test_estimate_uses_the_configured_ratio():
    hits = [hit(0, 0.9, "x" * 1500)]
    tight = assemble("q?", hits, Config(num_ctx=1000, num_predict=100, chars_per_token=1.5))
    roomy = assemble("q?", hits, Config(num_ctx=1000, num_predict=100, chars_per_token=4.0))
    assert tight is None and roomy is not None
    assert roomy.est_tokens == estimate_tokens(roomy.system, 4.0) + estimate_tokens(roomy.user, 4.0)
