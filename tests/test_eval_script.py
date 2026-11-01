"""The eval script's arithmetic, checked offline with the fake embedder and fake model (the real numbers come from running it against Ollama)."""
from __future__ import annotations

import importlib.util
import json
import sys

import pytest

from .conftest import QUESTIONS, ROOT, fake_config

pytestmark = pytest.mark.tooling


@pytest.fixture(scope="module")
def run_eval():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("lrk_run_eval", ROOT / "scripts" / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_question_set_has_what_the_task_asks_for():
    assert len(QUESTIONS["answerable"]) + len(QUESTIONS["unanswerable"]) >= 20
    assert len(QUESTIONS["unanswerable"]) >= 5
    ids = [q["id"] for q in QUESTIONS["answerable"] + QUESTIONS["unanswerable"]]
    assert len(ids) == len(set(ids))
    for q in QUESTIONS["answerable"]:
        assert q["expected"] and (ROOT / "samples" / "pdfs" / q["file"]).is_file() and q["page"] >= 1


def test_every_expected_string_really_is_in_the_pdf_it_points_at(cfg):
    """If the expected answer is not on the cited page, a 'correct' answer could never be found: the question set would be wrong."""
    from local_rag.extract import extract_pdf

    pages = {}
    for q in QUESTIONS["answerable"]:
        key = q["file"]
        if key not in pages:
            pages[key] = {p.page: " ".join(p.text.lower().split()) for p in extract_pdf(ROOT / "samples" / "pdfs" / key, cfg.extract_mode).pages}
        text = pages[key][q["page"]]
        assert any(e.lower() in text for e in q["expected"]), f"{q['id']}: none of {q['expected']} is on {key} page {q['page']}"


def test_run_scores_hits_answers_and_refusals(run_eval, tmp_path):
    cfg = fake_config(tmp_path / "unused", min_score=0.30)
    result = run_eval.run(cfg, {"H04", "K03", "U01"}, gate=False, log=lambda *_: None)
    rows = {r["id"]: r for r in result["rows"]}
    assert set(rows) == {"H04", "K03", "U01"}
    h = rows["H04"]
    assert h["expected_file"] == "harbor-pine-handbook.pdf" and h["expected_page"] == 2
    assert h["hit_at_k"] == any((s, p) == ("harbor-pine-handbook.pdf", 2) for s, p, _ in h["retrieved"])
    assert h["hit_at_1"] == (h["retrieved"][0][:2] == ["harbor-pine-handbook.pdf", 2])
    assert h["correct"] == ("25" in h["answer"] and not h["refused"])
    assert (not h["fact_in_prompt"]) or h["fact_in_top_k"]  # a passage in the prompt was retrieved first
    s = result["summary"]
    assert s["answerable"] == 2 and s["unanswerable"] == 1
    assert s["hit_at_k"] == sum(rows[i]["hit_at_k"] for i in ("H04", "K03"))
    assert s["fact_in_top_k"] == sum(rows[i]["fact_in_top_k"] for i in ("H04", "K03"))
    assert s["fact_in_prompt"] == sum(rows[i]["fact_in_prompt"] for i in ("H04", "K03"))
    assert s["correctly_refused"] + len(s["wrongly_answered"]) == 1
    json.dumps(result)  # the whole result can be written as JSON


def test_table_has_one_line_per_question(run_eval, tmp_path):
    cfg = fake_config(tmp_path / "unused", min_score=0.30)
    result = run_eval.run(cfg, {"P01", "U02"}, gate=False, log=lambda *_: None)
    lines = run_eval.table(result).strip().splitlines()
    assert len(lines) == 2 + 2 and lines[2].startswith("| P01 ") and lines[3].startswith("| U02 ")


def test_norm_makes_matching_case_and_space_insensitive(run_eval):
    assert run_eval.norm("  Up  to\nThree DAYS ") == "up to three days"
