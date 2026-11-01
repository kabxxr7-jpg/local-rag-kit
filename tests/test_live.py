"""Live suite: the real Ollama server with llama3.2:1b and nomic-embed-text. Run it with:  python -m pytest -m live

It is left out of the normal run (pytest.ini) and out of CI. It waits for a calm machine first (load gate) and asks the
server one thing at a time. Every test also appends what it saw to .live-observations.jsonl (git-ignored), which is where the
numbers and answers in docs/REAL-RUNS.md come from. Nothing here is mocked.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from local_rag.ask import ask
from local_rag.config import Config
from local_rag.doctor import PROBLEM, check_ollama, run_doctor
from local_rag.embed import get_embedder
from local_rag.errors import ModelNotPulled, OllamaUnavailable, StoreMismatch
from local_rag.ingest import ingest
from local_rag.prompt import REFUSAL_TEXT
from local_rag.store import VectorStore

from .conftest import ROOT, SAMPLES

sys.path.insert(0, str(ROOT / "scripts"))
from loadgate import Overloaded, wait_for_calm  # noqa: E402

pytestmark = pytest.mark.live

OBSERVATIONS = ROOT / ".live-observations.jsonl"
THREE = [SAMPLES / "harbor-pine-handbook.pdf", SAMPLES / "aurora-kettle-manual.pdf", SAMPLES / "meridian-price-list.pdf"]


def note(kind: str, **data) -> None:
    with OBSERVATIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": kind, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **data}, ensure_ascii=False) + "\n")


@pytest.fixture(autouse=True)
def calm_machine():
    try:
        wait_for_calm("a live test")
    except Overloaded as exc:
        pytest.fail(f"the machine stayed too busy to run a live test: {exc}")


@pytest.fixture(scope="module")
def server():
    cfg = Config()
    findings, installed = check_ollama(cfg)
    if installed is None:
        pytest.fail("the live suite needs Ollama at " + cfg.ollama_host + ": " + findings[0].detail)
    note("server", findings=[f.title for f in findings], installed=installed)
    return installed


@pytest.fixture(scope="module")
def live_cfg(tmp_path_factory) -> Config:
    return Config(store_dir=str(tmp_path_factory.mktemp("live") / "store"))


@pytest.fixture(scope="module")
def ingested(server, live_cfg):
    started = time.time()
    report = ingest(THREE, live_cfg)
    seconds = round(time.time() - started, 1)
    store = VectorStore.open(live_cfg.store_dir)
    note("ingest", seconds=seconds, chunks=report.total_chunks, per_file=report.ingested, stats=store.stats())
    return report


# ---- doctor, embedding, ingest ------------------------------------------------------------------------------------------
def test_doctor_is_green_against_the_real_server(server):
    findings = run_doctor(Config(), [str(p) for p in THREE])
    note("doctor", findings=[(f.level, f.title) for f in findings])
    assert not [f for f in findings if f.level == PROBLEM], [f.title for f in findings]


def test_embeddings_are_768_numbers_and_a_related_sentence_is_closer(server, live_cfg):
    emb = get_embedder(live_cfg)
    started = time.time()
    q, near, far = emb.embed_query("How many days of annual leave do I get?"), emb.embed_documents(["Every employee gets 25 days of paid annual leave per year."])[0], emb.embed_documents(["The kettle has a 1.7 litre capacity."])[0]
    seconds = round(time.time() - started, 2)
    assert len(q) == len(near) == len(far) == 768

    def dot(a, b):
        na, nb = sum(x * x for x in a) ** 0.5, sum(x * x for x in b) ** 0.5
        return sum(x * y for x, y in zip(a, b)) / (na * nb)

    note("embedding", dim=len(q), seconds=seconds, related=round(dot(q, near), 3), unrelated=round(dot(q, far), 3))
    assert dot(q, near) > dot(q, far)


def test_real_pdfs_are_ingested_page_by_page(ingested, live_cfg):
    assert set(ingested.ingested) == {p.name for p in THREE} and not ingested.failed
    store = VectorStore.open(live_cfg.store_dir)
    assert store.dim == 768 and store.embed_model == "nomic-embed-text"
    pages = {(r["source"], r["page"]) for r in store.records.values()}
    assert ("harbor-pine-handbook.pdf", 4) in pages and ("meridian-price-list.pdf", 3) in pages


def test_ingesting_again_changes_nothing(ingested, live_cfg):
    before = VectorStore.open(live_cfg.store_dir).stats()
    started = time.time()
    report = ingest(THREE, live_cfg)
    note("reingest", seconds=round(time.time() - started, 2), unchanged=report.unchanged, total=report.total_chunks)
    assert not report.ingested and sorted(report.unchanged) == sorted(p.name for p in THREE)
    assert VectorStore.open(live_cfg.store_dir).stats() == before


# ---- asking -------------------------------------------------------------------------------------------------------------
def test_a_known_question_is_answered_and_cited(ingested, live_cfg):
    started = time.time()
    r = ask("How many days of annual leave do employees get?", live_cfg)
    note("ask", question=r.question, answer=r.answer, citations=r.citations, best_score=round(r.best_score, 3), prompt_tokens=r.prompt_tokens, seconds=round(time.time() - started, 1), warnings=r.warnings)
    assert not r.refused
    assert "25" in r.answer
    assert ("harbor-pine-handbook.pdf", 2) in r.citations


def test_an_unrelated_question_is_refused_without_asking_the_model(ingested, live_cfg):
    r = ask("Who painted the Mona Lisa?", live_cfg)
    note("refusal", question=r.question, answer=r.answer, reason=r.reason, best_score=round(r.best_score, 3))
    assert r.refused and r.reason == "below_threshold" and r.answer == REFUSAL_TEXT
    assert r.prompt_tokens is None  # the model was never called


def test_a_too_big_prompt_is_trimmed_before_the_server_sees_it(ingested, live_cfg):
    cfg = replace(live_cfg, num_ctx=1024, k=12, min_score=0.0)
    r = ask("What do I need to know about leave, travel and expenses?", cfg)
    note("trim", dropped=len(r.dropped), kept=len(r.kept), est_tokens=r.est_tokens, budget=r.budget_tokens, prompt_tokens=r.prompt_tokens, answer=r.answer, warnings=r.warnings)
    assert r.dropped and any("Context trimmed" in w for w in r.warnings)
    assert r.prompt_tokens is not None and r.prompt_tokens < cfg.num_ctx - 8  # the server read the whole prompt
    assert not any("probably cut" in w for w in r.warnings)


def test_a_prompt_the_server_cuts_anyway_is_flagged_after_the_fact(ingested, live_cfg):
    # chars_per_token=100 makes the size check believe everything fits: the second line of defence has to notice that the server cut the prompt.
    cfg = replace(live_cfg, num_ctx=1024, k=12, min_score=0.0, chars_per_token=100.0)
    r = ask("What do I need to know about leave, travel and expenses?", cfg)
    note("truncation", dropped=len(r.dropped), prompt_tokens=r.prompt_tokens, answer=r.answer, warnings=r.warnings)
    assert not r.dropped
    assert any("probably cut the prompt" in w for w in r.warnings), (r.prompt_tokens, r.warnings)


# ---- the things that go wrong ---------------------------------------------------------------------------------------------
def test_a_pdf_without_text_is_reported_in_plain_words(server, tmp_path):
    cfg = Config(store_dir=str(tmp_path / "store"))
    report = ingest([SAMPLES / "scanned-notice.pdf"], cfg)
    note("no-text", failed=report.failed)
    assert not report.ingested and "does not do OCR" in report.failed["scanned-notice.pdf"]


def test_a_model_that_is_not_pulled_gives_the_command_to_fix_it(ingested, live_cfg):
    missing = "llama3.2:3b"
    if any(name == missing for name in check_ollama(live_cfg)[1] or []):
        pytest.skip(f"{missing} happens to be installed on this machine")
    with pytest.raises(ModelNotPulled) as err:
        ask("How many days of annual leave do employees get?", replace(live_cfg, llm_model=missing))
    note("not-pulled", message=str(err.value))
    assert f"ollama pull {missing}" in str(err.value)


def test_a_store_built_with_other_vectors_is_refused_with_the_way_out(ingested, live_cfg):
    with pytest.raises(StoreMismatch) as err:
        ask("How many days of annual leave do employees get?", replace(live_cfg, embed_dimensions=256))
    note("dim-mismatch", message=str(err.value))
    assert "768" in str(err.value) and "--rebuild" in str(err.value)


def test_ollama_not_running_is_explained(tmp_path):
    cfg = Config(ollama_host="http://127.0.0.1:4799", store_dir=str(tmp_path / "store"), request_timeout=5)
    findings, installed = check_ollama(cfg)
    assert installed is None and findings[0].level == PROBLEM
    with pytest.raises(OllamaUnavailable) as err:
        ingest([THREE[0]], cfg)
    note("not-running", doctor=findings[0].title + " | " + findings[0].detail, ingest_error=str(err.value))
    assert "ollama serve" in str(err.value) or "Start it" in str(err.value)


def test_the_command_line_end_to_end(server, tmp_path):
    store = str(tmp_path / "cli-store")
    env_run = dict(cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    first = subprocess.run([sys.executable, "-m", "local_rag", "ingest", "--store", store, str(THREE[1])], **env_run)
    second = subprocess.run([sys.executable, "-m", "local_rag", "ask", "--store", store, "--json", "How long is the warranty on the Aurora AK-200?"], **env_run)
    note("cli", ingest_out=first.stdout.strip(), ask_out=second.stdout.strip(), ask_err=second.stderr.strip()[-300:])
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    data = json.loads(second.stdout)
    assert data["citations"] and data["citations"][0]["file"] == "aurora-kettle-manual.pdf"
