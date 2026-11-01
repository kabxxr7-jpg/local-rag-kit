from __future__ import annotations

import json

import pytest

from local_rag.cli import main
from local_rag.prompt import REFUSAL_TEXT

from .conftest import SAMPLES


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_RAG_EMBEDDER", "fake")
    monkeypatch.setenv("LOCAL_RAG_LLM", "fake")
    monkeypatch.setenv("LOCAL_RAG_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("LOCAL_RAG_MIN_SCORE", "0.3")
    monkeypatch.delenv("LOCAL_RAG_CONFIG", raising=False)
    return tmp_path


def test_ingest_prints_what_it_did_and_exits_1_because_the_scan_failed(env, capsys):
    assert main(["ingest", str(SAMPLES)]) == 1
    out, err = capsys.readouterr()
    assert "ingested  harbor-pine-handbook.pdf:" in out and "store: " in out
    assert "FAILED    scanned-notice.pdf" in err and "OCR" in err


def test_ingest_of_only_good_files_exits_0_and_a_repeat_says_unchanged(env, capsys):
    good = str(SAMPLES / "aurora-kettle-manual.pdf")
    assert main(["ingest", good]) == 0
    capsys.readouterr()
    assert main(["ingest", good]) == 0
    out = capsys.readouterr().out
    assert "unchanged aurora-kettle-manual.pdf" in out
    assert not any(line.startswith("ingested ") for line in out.splitlines())


def test_ask_prints_the_answer_and_the_sources(env, capsys):
    main(["ingest", str(SAMPLES)])
    capsys.readouterr()
    assert main(["ask", "How many days of paid annual leave does each employee get per year?"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Answer: ") and "25 days" in out
    assert "Sources: harbor-pine-handbook.pdf p.2" in out


def test_ask_a_refused_question_says_why_without_calling_it_an_error(env, capsys):
    main(["ingest", str(SAMPLES)])
    capsys.readouterr()
    assert main(["ask", "What is the capital of Portugal?"]) == 0
    out = capsys.readouterr().out
    assert f"Answer: {REFUSAL_TEXT}" in out
    assert "is below min_score 0.3; the model was not asked" in out and "Sources:" not in out


def test_ask_json_has_the_documented_fields(env, capsys):
    main(["ingest", str(SAMPLES)])
    capsys.readouterr()
    assert main(["ask", "--json", "How many days of paid annual leave does each employee get per year?"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"question", "answer", "refused", "reason", "citations", "best_score", "est_tokens", "prompt_tokens", "dropped", "warnings"}
    assert data["refused"] is False and data["citations"][0] == {"file": "harbor-pine-handbook.pdf", "page": 2}


def test_ask_debug_lists_every_passage_with_its_state(env, capsys):
    main(["ingest", str(SAMPLES)])
    capsys.readouterr()
    main(["ask", "--debug", "--show-prompt", "-k", "3", "How many days of paid annual leave does each employee get per year?"])
    out = capsys.readouterr().out
    assert "-- debug --" in out and "retrieved 3 passage(s), k=3" in out
    assert "[in prompt]" in out and "-- prompt --" in out and "Passages:" in out


def test_errors_are_one_line_on_stderr_with_exit_code_2_and_no_traceback(env, capsys):
    assert main(["ask", "anything?"]) == 2
    out, err = capsys.readouterr()
    assert err.startswith("error: The store is empty") and "Traceback" not in err and out == ""


def test_config_errors_are_reported_the_same_way(env, capsys, monkeypatch):
    monkeypatch.setenv("LOCAL_RAG_CHUNK_OVERLAP", "9999")
    assert main(["ingest", str(SAMPLES)]) == 2
    assert "chunk_overlap" in capsys.readouterr().err


def test_flags_beat_the_environment(env, capsys, tmp_path):
    other = tmp_path / "other-store"
    assert main(["ingest", "--store", str(other), str(SAMPLES / "aurora-kettle-manual.pdf")]) == 0
    assert (other / "meta.json").exists() and not (env / "store").exists()
    capsys.readouterr()
    main(["ask", "--store", str(other), "--json", "-k", "2", "What is the maximum fill level of the Aurora AK-200?"])
    assert json.loads(capsys.readouterr().out)["citations"][0]["file"] == "aurora-kettle-manual.pdf"


def test_config_file_flag(env, capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_RAG_STORE_DIR")
    cfg = tmp_path / "rag.toml"
    cfg.write_text(f'store_dir = "{tmp_path / "from-file"}"\n')
    assert main(["ingest", "--config", str(cfg), str(SAMPLES / "aurora-kettle-manual.pdf")]) == 0
    assert (tmp_path / "from-file" / "meta.json").exists()


def test_rebuild_flag_resets_the_store(env, capsys):
    main(["ingest", str(SAMPLES / "aurora-kettle-manual.pdf")])
    capsys.readouterr()
    assert main(["ingest", "--rebuild", str(SAMPLES / "meridian-price-list.pdf")]) == 0
    out = capsys.readouterr().out
    assert "ingested  meridian-price-list.pdf" in out
    from local_rag.store import VectorStore

    assert set(VectorStore.open(env / "store").stats()["files"]) == {"meridian-price-list.pdf"}


def test_doctor_exit_codes_follow_the_findings(env, capsys):
    main(["ingest", str(SAMPLES / "aurora-kettle-manual.pdf")])
    capsys.readouterr()
    assert main(["doctor", str(SAMPLES / "aurora-kettle-manual.pdf")]) == 0
    assert "No problems found." in capsys.readouterr().out
    assert main(["doctor", str(SAMPLES)]) == 1
    out = capsys.readouterr().out
    assert "[PROBLEM] scanned-notice.pdf: no extractable text" in out and "1 problem(s)." in out


def test_unknown_command_is_an_argparse_error(env):
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])
    assert exc.value.code == 2
