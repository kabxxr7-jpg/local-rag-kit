from __future__ import annotations

import urllib.error
from dataclasses import replace

import pytest

from local_rag import doctor
from local_rag.config import Config
from local_rag.doctor import OK, PROBLEM, WARN, check_budget, check_ollama, check_pdfs, check_store, render, run_doctor
from local_rag.ingest import ingest
from local_rag.testing import FakeEmbedder

from .conftest import SAMPLES, fake_config


def levels(findings):
    return [f.level for f in findings]


def serve(monkeypatch, models, version="0.9.9"):
    def fake_http(url, timeout=5.0):
        if url.endswith("/api/version"):
            return {"version": version}
        return {"models": [{"name": m} for m in models]}

    monkeypatch.setattr(doctor, "_http_json", fake_http)


def test_ollama_not_running_is_explained_in_plain_words(monkeypatch):
    def refuse(url, timeout=5.0):
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(doctor, "_http_json", refuse)
    findings, installed = check_ollama(Config(ollama_host="http://127.0.0.1:4799"))
    assert installed is None and levels(findings) == [PROBLEM]
    assert "Ollama does not answer at http://127.0.0.1:4799" in findings[0].title
    assert "not running" in findings[0].detail and "ollama serve" in findings[0].detail and "LOCAL_RAG_OLLAMA_HOST" in findings[0].detail


def test_nothing_listening_on_the_port_is_the_same_problem_without_mocks():
    findings, installed = check_ollama(Config(ollama_host="http://127.0.0.1:4799"))
    assert installed is None and findings[0].level == PROBLEM and "ollama serve" in findings[0].detail


def test_something_else_on_the_port(monkeypatch):
    def not_json(url, timeout=5.0):
        raise ValueError("Expecting value")

    monkeypatch.setattr(doctor, "_http_json", not_json)
    findings, installed = check_ollama(Config())
    assert installed is None and "not like Ollama" in findings[0].title


def test_model_not_pulled_names_the_model_and_what_is_installed(monkeypatch):
    serve(monkeypatch, ["nomic-embed-text:latest", "llama3.2:1b"])
    findings, installed = check_ollama(Config(llm_model="llama3.2:3b"))
    assert installed == ["nomic-embed-text:latest", "llama3.2:1b"]
    bad = [f for f in findings if f.level == PROBLEM]
    assert len(bad) == 1 and "language model 'llama3.2:3b' is not pulled" in bad[0].title
    assert "ollama pull llama3.2:3b" in bad[0].detail and "llama3.2:1b" in bad[0].detail
    assert any(f.level == OK and "embedding model 'nomic-embed-text' is installed" in f.title for f in findings)


def test_a_name_without_tag_matches_latest_but_a_tag_must_match(monkeypatch):
    serve(monkeypatch, ["nomic-embed-text:latest", "llama3.2:1b"])
    assert levels(check_ollama(Config())[0]) == [OK, OK, OK]
    findings, _ = check_ollama(Config(llm_model="llama3.2"))
    assert PROBLEM in levels(findings)
    findings, _ = check_ollama(Config(embed_model="nomic-embed-text:v1.5"))
    assert PROBLEM in levels(findings)


def test_fake_backends_are_not_checked_against_the_server(monkeypatch):
    serve(monkeypatch, [])
    findings, _ = check_ollama(Config(embedder="fake", llm="fake"))
    assert levels(findings) == [OK]


def test_no_store_yet_is_a_warning_with_the_command_to_run(tmp_path):
    f = check_store(fake_config(tmp_path / "none"))
    assert levels(f) == [WARN] and "python -m local_rag ingest" in f[0].detail


def test_store_built_with_another_model_is_the_dimension_mismatch_story(tmp_path):
    cfg = fake_config(tmp_path / "s", embed_model="model-a")
    ingest([SAMPLES], cfg, FakeEmbedder(dim=64, model="model-a"))
    f = check_store(replace(cfg, embed_model="model-b"), FakeEmbedder(dim=128, model="model-b"))
    problems = [x for x in f if x.level == PROBLEM]
    assert len(problems) == 1
    assert "built with 'model-a' but embed_model is now 'model-b'" in problems[0].title
    assert "64" in problems[0].detail and "--rebuild" in problems[0].detail


def test_same_name_other_dimension_is_found_by_probing_the_model(tmp_path):
    cfg = fake_config(tmp_path / "s", embed_model="model-a")
    ingest([SAMPLES], cfg, FakeEmbedder(dim=64, model="model-a"))
    f = check_store(cfg, FakeEmbedder(dim=128, model="model-a"))
    problems = [x for x in f if x.level == PROBLEM]
    assert len(problems) == 1 and "Dimension mismatch: the store has 64-dimensional vectors, 'model-a' returns 128" in problems[0].title


def test_healthy_store(tmp_path):
    cfg = fake_config(tmp_path / "s", embed_model="model-a")
    emb = FakeEmbedder(dim=64, model="model-a")
    ingest([SAMPLES], cfg, emb)
    f = check_store(cfg, emb)
    assert levels(f) == [OK, OK]
    assert "chunks from 3 file(s)" in f[0].title and "64 dimensions" in f[0].detail


def test_unreadable_store_is_a_problem_not_a_crash(tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "meta.json").write_text('{"format": 99}')
    f = check_store(fake_config(tmp_path / "s"))
    assert levels(f) == [PROBLEM] and "cannot be read" in f[0].title


def test_pdf_checks_find_the_scan_and_say_ocr_is_not_covered():
    f = check_pdfs(Config(), [str(SAMPLES)])
    by_title = {x.title.split(":")[0]: x for x in f}
    assert by_title["scanned-notice.pdf"].level == PROBLEM and "does not do OCR" in by_title["scanned-notice.pdf"].detail
    assert by_title["aurora-kettle-manual.pdf"].level == OK and "all 4 page(s)" in by_title["aurora-kettle-manual.pdf"].title


def test_a_half_scanned_pdf_is_a_warning(tmp_path):
    from reportlab.pdfgen import canvas

    p = tmp_path / "half.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(72, 700, "Some words on page one.")
    c.showPage()
    c.showPage()
    c.save()
    f = check_pdfs(Config(), [str(p)])
    assert levels(f) == [WARN] and "1 of 2 page(s) have no text" in f[0].title and "pages 2" in f[0].detail


def test_a_file_that_is_not_a_pdf_is_a_problem_not_a_crash(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"this is not a pdf at all")
    f = check_pdfs(Config(), [str(p)])
    assert levels(f) == [PROBLEM] and "cannot be read" in f[0].title


def test_bad_path_is_reported():
    f = check_pdfs(Config(), ["/nonexistent/place.pdf"])
    assert levels(f) == [PROBLEM] and "neither a PDF file nor a folder" in f[0].detail


def test_budget_warning_appears_when_a_full_set_cannot_fit():
    roomy = check_budget(Config())
    assert levels(roomy) == [OK]
    tight = check_budget(Config(k=8, chunk_size=1500, num_ctx=2048, num_predict=256))
    assert levels(tight) == [WARN] and "silently cuts the prompt" in tight[0].detail and "dropped (and reported)" in tight[0].detail
    refuse = check_budget(Config(k=8, chunk_size=1500, num_ctx=2048, num_predict=256, on_overflow="refuse"))
    assert "refused" in refuse[0].detail


def test_run_doctor_with_fake_backends_skips_the_network(tmp_path):
    cfg = fake_config(tmp_path / "s")
    ingest([SAMPLES], cfg, FakeEmbedder(dim=cfg.fake_dim, model=cfg.embed_model))
    f = run_doctor(cfg, [str(SAMPLES / "aurora-kettle-manual.pdf")])
    assert PROBLEM not in levels(f)


def test_render_marks_each_finding_and_counts_problems():
    text = render([doctor.Finding(OK, "fine"), doctor.Finding(WARN, "hmm", "look"), doctor.Finding(PROBLEM, "bad", "do this")])
    assert "[ok]      fine" in text and "[warning] hmm" in text and "[PROBLEM] bad" in text
    assert "          do this" in text and text.endswith("1 problem(s).")
    assert render([doctor.Finding(OK, "fine")]).endswith("No problems found.")
