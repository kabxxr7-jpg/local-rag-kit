"""The refusal threshold is far too high: every question is refused, including the ones the documents answer."""
from __future__ import annotations

from framework import Edit, Env, Scenario, cli

from .common import MAIN_PDFS

# probe questions that are NOT in eval/questions.json
ANSWERABLE = [
    "What is the length of the standard working week?",
    "How many weeks of parental leave does the other parent get?",
    "What is the equipment budget for a laptop?",
    "How many temperature presets does the kettle have?",
    "What is the minimum amount of water for the kettle?",
]
OFF_TOPIC = [
    "Who painted the Mona Lisa?",
    "What is the best programming language for beginners?",
    "How do I bake sourdough bread?",
    "What is the weather in Lisbon today?",
]
GOOD = {"ollama": "0.60", "fake": "0.12"}


def check(ctx):
    for q in ANSWERABLE:
        with ctx.step(f"answerable, not refused by the threshold: {q}"):
            r = ctx.ask(q)
            assert r.reason != "below_threshold", f"refused: best score {r.best_score:.3f} < min_score {ctx.cfg.min_score}"
    for q in OFF_TOPIC:
        with ctx.step(f"off topic, refused by the threshold: {q}"):
            r = ctx.ask(q)
            assert r.reason == "below_threshold", f"not refused: best score {r.best_score:.3f} >= min_score {ctx.cfg.min_score}; the model answered {r.answer!r}"


SCENARIO = Scenario(
    name="refusal-threshold",
    title="Refusal threshold too high (and what happens when it is too low)",
    story=(
        "min_score was set to 0.95 'to avoid hallucinations'. The best passage for a question that the documents answer scores 0.64 to 0.85 with nomic-embed-text, "
        "so nothing ever reaches the model. The obvious reaction, setting it to 0, brings the opposite failure: questions about nothing in the documents get answered."
    ),
    pdfs=MAIN_PDFS,
    env={"fake": {"LOCAL_RAG_FAKE_DIM": "4096", "LOCAL_RAG_MIN_SCORE": "0.12"}},  # fewer hash collisions, so the fake scores separate the two kinds of question
    setup=[cli("ingest", "pdfs")],
    break_=[Env("MIN_SCORE", "0.95")],
    symptom=[cli("ask", ANSWERABLE[0]), cli("ask", "--debug", ANSWERABLE[2])],
    diagnose=[cli("ask", "--debug", "--json", ANSWERABLE[3])],
    check=check,
    fixes={
        "calibrated_threshold": lambda backend: [Env("MIN_SCORE", GOOD[backend])],
        "calibrated_threshold_a_bit_higher": lambda backend: [Env("MIN_SCORE", "0.62" if backend == "ollama" else "0.15")],
    },
    wrongs={
        "threshold_zero": [Env("MIN_SCORE", "0.0")],
        "threshold_a_bit_lower": [Env("MIN_SCORE", "0.90")],
        "retrieve_more": [Env("K", "20")],
        "friendlier_refusal_text": [Edit("local_rag/prompt.py", 'REFUSAL_TEXT = "I could not find an answer to that in the ingested documents."', 'REFUSAL_TEXT = "Sorry, I am not sure about that one, please try rephrasing."')],
    },
    fix_notes={
        "calibrated_threshold": "Chosen between the best scores of off-topic probes (at most 0.58) and of answerable ones (at least 0.64) with scripts/calibrate.py. With a different embedding model it has to be calibrated again.",
        "calibrated_threshold_a_bit_higher": "Anything inside the gap works; the gap is narrow (see docs/REAL-RUNS.md).",
    },
    wrong_notes={
        "threshold_zero": "Nothing is refused any more: the model answers questions about Portugal and bread from a staff handbook.",
        "threshold_a_bit_lower": "0.90 is still above every score these documents give.",
        "retrieve_more": "k does not move the best score, and the threshold looks only at the best score.",
        "friendlier_refusal_text": "The same refusals, politely worded.",
    },
)
