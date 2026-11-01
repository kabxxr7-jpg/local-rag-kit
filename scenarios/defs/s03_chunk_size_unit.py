"""chunk_size was meant as tokens but counts characters: sentences are cut to pieces and the answer is lost."""
from __future__ import annotations

from framework import Env, Scenario, cli

from .common import MAIN_PDFS

# (question, the whole sentence that holds the answer)
SENTENCES = [
    ("How many unused leave days can be carried over to the next year?", "Up to 5 unused days may be carried over and must be taken by 31 March of the following year; anything left after that date expires."),
    ("How much is the learning budget per person per year?", "The learning budget is 800 EUR per person per year for courses, books and conferences; it does not roll over to the next year."),
    ("How do you descale the kettle?", "Fill it with one part white vinegar and two parts water, bring it to the boil, let it stand for 15 minutes, then rinse it well twice."),
    ("Who can I talk to in confidence about harassment?", "Concerns about harassment can be raised in confidence with the trust person, Ines Carvalho, or with the managing partner."),
]


def check(ctx):
    for question, sentence in SENTENCES:
        with ctx.step(f"the sentence answering '{question}' reaches the model in one piece"):
            hits = ctx.retrieve(question)
            whole = [h for h in hits if ctx.norm(sentence) in ctx.norm(h.text)]
            sizes = sorted(len(h.text) for h in hits)
            assert whole, f"none of the {len(hits)} retrieved passages (lengths {sizes}) holds the whole sentence"


SCENARIO = Scenario(
    name="chunk-size-unit-mistake",
    title="Chunks too small: chunk_size counted in characters, meant as tokens",
    story=(
        "Someone set chunk_size=100 and chunk_overlap=0 believing the unit was tokens. The splitter counts characters, so every chunk is about 100 characters, "
        "sentences are cut in the middle, and the piece that holds the number is not the piece that holds the subject."
    ),
    pdfs=MAIN_PDFS,
    setup=[cli("ingest", "pdfs")],
    break_=[Env("CHUNK_SIZE", "100"), Env("CHUNK_OVERLAP", "0"), cli("ingest", "pdfs")],
    symptom=[cli("ask", "--debug", SENTENCES[0][0])],
    diagnose=[cli("doctor")],
    check=check,
    fixes={
        "restore_the_defaults_and_ingest": [Env("CHUNK_SIZE", None), Env("CHUNK_OVERLAP", None), cli("ingest", "pdfs")],
        "set_600_100_and_ingest": [Env("CHUNK_SIZE", "600"), Env("CHUNK_OVERLAP", "100"), cli("ingest", "pdfs")],
    },
    wrongs={
        "raise_k": [Env("K", "20")],
        "change_the_setting_but_do_not_ingest": [Env("CHUNK_SIZE", None), Env("CHUNK_OVERLAP", None)],
        "add_overlap_only": [Env("CHUNK_OVERLAP", "50"), cli("ingest", "pdfs")],
    },
    fix_notes={
        "restore_the_defaults_and_ingest": "Characters, about 500 per chunk. `ingest` notices that the chunk settings changed and re-chunks the files that were stored with the old ones, so no `--rebuild` is needed.",
        "set_600_100_and_ingest": "Any size that holds a few sentences works; the check only asks that the answering sentence is whole.",
    },
    wrong_notes={
        "raise_k": "Twenty fragments are still fragments, and the prompt gets longer.",
        "change_the_setting_but_do_not_ingest": "The store still holds the 100-character chunks; settings only apply to files that are ingested again.",
        "add_overlap_only": "An overlap of 50 on 100-character chunks repeats half of each fragment; the sentences are still cut.",
    },
)
