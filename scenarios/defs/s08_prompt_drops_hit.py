"""Retrieval finds the right page, but the prompt assembly leaves the best passage out."""
from __future__ import annotations

from framework import Edit, Env, Scenario, cli

from .common import MAIN_PDFS

PROMPT_QUESTIONS = [
    "How many days of paid annual leave does each employee get per year?",
    "What is the maximum fill level of the Aurora AK-200?",
    "How much does the priority support add-on cost per month?",
]
FIND = "for n, h in enumerate(hits, start=1))"
BREAK = Edit("local_rag/prompt.py", FIND, "for n, h in enumerate(hits[-3:], start=1))")
FIX = Edit("local_rag/prompt.py", "for n, h in enumerate(hits[-3:], start=1))", FIND)


def check(ctx):
    for q in PROMPT_QUESTIONS:
        with ctx.step(f"the prompt for '{q[:46]}...' contains the best passage and everything that is cited"):
            r = ctx.ask(q)
            prompt = ctx.prompts[-1][1]
            assert r.kept, "nothing was kept"
            assert r.hits[0].text in prompt, f"the best passage ({r.hits[0].source} p.{r.hits[0].page}, score {r.hits[0].score:.2f}) is not in the prompt; the prompt holds {prompt.count('] (')} passages"
            missing = [h for h in r.kept if h.text not in prompt]
            assert not missing, f"{len(missing)} passage(s) listed as used are not in the prompt"


SCENARIO = Scenario(
    name="prompt-assembly-drops-hit",
    title="Retrieval is right, the prompt never contains the page",
    story=(
        "k was raised to 6 for recall. The inherited prompt builder keeps 'the last three passages' to save room, but the list is best first, so with four or more "
        "passages it throws the best ones away. Retrieval and citations still look right; the model is answering from the worst passages."
    ),
    pdfs=MAIN_PDFS,
    env={"fake": {"LOCAL_RAG_K": "6", "LOCAL_RAG_MIN_SCORE": "0.15"}, "ollama": {"LOCAL_RAG_K": "6", "LOCAL_RAG_MIN_SCORE": "0.50"}},
    setup=[cli("ingest", "pdfs")],
    break_=[BREAK],
    symptom=[cli("ask", "--debug", "--show-prompt", PROMPT_QUESTIONS[0])],
    diagnose=[cli("ask", "--debug", PROMPT_QUESTIONS[1])],
    check=check,
    fixes={"keep_every_passage": [FIX]},
    wrongs={
        "raise_k": [Env("K", "10")],
        "lower_the_threshold": [Env("MIN_SCORE", "0.0")],
        "rewrite_the_instructions": [Edit("local_rag/prompt.py", "Keep the answer short. Do not use any knowledge outside the passages.", "Read the passages very carefully and give a short, precise answer.")],
    },
    fix_notes={"keep_every_passage": "Render the passages that were kept, in rank order. No re-ingest: this is code that runs at question time."},
    wrong_notes={
        "raise_k": "More passages retrieved; the builder still keeps only the last three of them.",
        "lower_the_threshold": "More passages pass the filter; still only the last three are rendered.",
        "rewrite_the_instructions": "Better wording for text the model never gets to see.",
    },
)
