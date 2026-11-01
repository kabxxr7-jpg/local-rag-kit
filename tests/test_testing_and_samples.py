from __future__ import annotations

import math
import subprocess
import sys

from local_rag.prompt import REFUSAL_TEXT
from local_rag.testing import FakeEmbedder, FakeLLM, words

from .conftest import ROOT, SAMPLES, SCENARIO_PDFS


def test_fake_embedder_is_deterministic_and_unit_length():
    a, b = FakeEmbedder(64), FakeEmbedder(64)
    v = a.embed_query("annual leave days")
    assert v == b.embed_query("annual leave days")
    assert math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-9) and len(v) == 64


def test_fake_embedder_puts_shared_words_closer():
    e = FakeEmbedder(256)
    q, near, far = e.embed_query("annual leave"), e.embed_query("paid annual leave days"), e.embed_query("kettle descaling vinegar")
    dot = lambda x, y: sum(p * r for p, r in zip(x, y))  # noqa: E731
    assert dot(q, near) > 0.5 > dot(q, far)


def test_words_drop_stop_words_and_keep_numbers_and_decimals():
    assert words("What is the 1.7 litre limit of AF-20?") == ["1.7", "litre", "limit", "af", "20"]


def test_fake_llm_picks_the_sentence_that_shares_the_most_words_and_records_prompts():
    llm = FakeLLM()
    user = "Passages:\n\n[1] (a.pdf, page 1)\nThe kettle holds 1.7 litres of water. Blue is a colour.\n\nQuestion: How much water does the kettle hold?\nAnswer:"
    assert llm.generate("sys", user).text == "The kettle holds 1.7 litres of water."
    assert llm.prompts == [("sys", user)]


def test_fake_llm_declines_when_nothing_overlaps_and_can_be_scripted():
    llm = FakeLLM()
    assert llm.generate("s", "Passages:\n\n[1] (a.pdf, page 1)\nCompletely unrelated sentence about nothing.\n\nQuestion: zebra?\nAnswer:").text == REFUSAL_TEXT
    scripted = FakeLLM(reply="fixed", prompt_tokens=77).generate("s", "u")
    assert (scripted.text, scripted.prompt_tokens) == ("fixed", 77)


def test_the_sample_pdfs_are_exactly_what_the_generator_writes(tmp_path):
    """The committed PDFs are reproducible: regenerating them changes nothing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_pdfs", ROOT / "samples" / "make_pdfs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_pdfs"] = module
    spec.loader.exec_module(module)
    written = module.build_all(tmp_path)
    assert len(written) == 7
    for path in written:
        committed = ROOT / path.relative_to(tmp_path)
        assert committed.read_bytes() == path.read_bytes(), path.name


def test_the_scanned_sample_really_has_no_text_layer_and_the_others_do():
    from pypdf import PdfReader

    assert [(p.extract_text() or "").strip() for p in PdfReader(str(SAMPLES / "scanned-notice.pdf")).pages] == [""]
    for name in ("harbor-pine-handbook.pdf", "aurora-kettle-manual.pdf", "meridian-price-list.pdf"):
        assert all((p.extract_text() or "").strip() for p in PdfReader(str(SAMPLES / name)).pages), name
    assert len(list(SCENARIO_PDFS.glob("*.pdf"))) == 3


def test_module_entry_point_runs_without_the_network():
    out = subprocess.run([sys.executable, "-m", "local_rag", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "ingest" in out.stdout and "ask" in out.stdout and "doctor" in out.stdout
