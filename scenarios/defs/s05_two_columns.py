"""Two text columns merged line by line: the sentences are interleaved."""
from __future__ import annotations

from framework import Env, Scenario, cli

SENTENCES = [
    "Customers may return unused goods within 30 days of delivery for a full refund.",
    "Orders above 50 EUR ship free of charge. Standard delivery takes 3 to 5 working days.",
]
Q1 = "How many days do customers have to return unused goods?"
Q2 = "How long does standard delivery take?"


def check(ctx):
    for sentence in SENTENCES:
        with ctx.step(f"the sentence reads as written in one chunk: {sentence[:48]}..."):
            found = ctx.chunk_with(sentence)
            assert found, "no stored chunk contains it. The stored page reads: " + ctx.norm(ctx.page_text("shop-policies-two-columns.pdf", 1))[:260]


SCENARIO = Scenario(
    name="two-columns-merged",
    title="Two columns merged: text extraction reads across the page",
    story=(
        "The shop policy page has two columns, written into the PDF line by line (left line 1, right line 1, left line 2...). Read in that order, "
        "the returns policy and the delivery policy are interleaved, so '30 days' sits next to 'ship free of' and a model has to untangle it."
    ),
    pdfs=["shop-policies-two-columns.pdf"],
    env={"fake": {"LOCAL_RAG_CHUNK_SIZE": "1200", "LOCAL_RAG_CHUNK_OVERLAP": "100"}, "ollama": {"LOCAL_RAG_CHUNK_SIZE": "1200", "LOCAL_RAG_CHUNK_OVERLAP": "100"}},
    setup=[Env("EXTRACT_MODE", "columns"), cli("ingest", "pdfs")],
    break_=[Env("EXTRACT_MODE", "plain"), cli("ingest", "pdfs")],
    symptom=[cli("ask", "--debug", "--show-prompt", Q1)],
    diagnose=[cli("doctor", "pdfs")],
    check=check,
    fixes={"read_the_page_column_by_column": [Env("EXTRACT_MODE", "columns"), cli("ingest", "pdfs")]},
    wrongs={
        "layout_mode": [Env("EXTRACT_MODE", "layout"), cli("ingest", "pdfs")],
        "bigger_chunks": [Env("CHUNK_SIZE", "3000"), cli("ingest", "pdfs")],
        "retrieve_more": [Env("K", "12")],
    },
    fix_notes={"read_the_page_column_by_column": "`extract_mode=columns` sorts the text fragments by where they sit on the page: left column top to bottom, then the right one. `ingest` sees that the extraction setting changed and re-reads the file."},
    wrong_notes={
        "layout_mode": "Keeps the lines side by side ('left text | right text'), which is right for a table and wrong for two columns of prose.",
        "bigger_chunks": "The whole page in one chunk is still the interleaved page.",
        "retrieve_more": "The garbled text is what gets retrieved, however many times.",
    },
    observe=[cli("ask", Q1), cli("ask", Q2)],
)
