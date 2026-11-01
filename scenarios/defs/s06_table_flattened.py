"""A price table read as one cell per line: the row (Pro, 5 TB, 10, 29 EUR) no longer exists."""
from __future__ import annotations

from framework import Env, Scenario, cli

ROWS = ["Plan | Storage | Users | Price per month", "Pro | 5 TB | 10 | 29 EUR", "Business | 20 TB | 50 | 89 EUR"]
Q1 = "How much does the Pro plan cost per month?"
Q2 = "How many users are included in the Business plan?"


def check(ctx):
    for row in ROWS:
        with ctx.step(f"the table row is one line in the stored text: {row}"):
            assert ctx.chunk_with(row), "not found. The page reads: " + ctx.norm(ctx.page_text("price-list-columnwise.pdf", 1))[200:420]


SCENARIO = Scenario(
    name="table-flattened",
    title="Table flattened into nonsense",
    story=(
        "The price list's table was written into the PDF column by column. Read in that order, the text is 'Plan, Starter, Plus, Pro, Business, Storage, 100 GB...': "
        "every cell on its own line, the rows gone. Asked what the Pro plan costs, the model has to guess which '29 EUR' belongs to which name."
    ),
    pdfs=["price-list-columnwise.pdf"],
    setup=[Env("EXTRACT_MODE", "layout"), cli("ingest", "pdfs")],
    break_=[Env("EXTRACT_MODE", "plain"), cli("ingest", "pdfs")],
    symptom=[cli("ask", "--debug", "--show-prompt", Q1)],
    diagnose=[cli("doctor", "pdfs")],
    check=check,
    fixes={"layout_extraction": [Env("EXTRACT_MODE", "layout"), cli("ingest", "pdfs")]},
    wrongs={
        "columns_mode": [Env("EXTRACT_MODE", "columns"), cli("ingest", "pdfs")],
        "bigger_chunks": [Env("CHUNK_SIZE", "2500"), cli("ingest", "pdfs")],
        "retrieve_more": [Env("K", "12")],
    },
    fix_notes={"layout_extraction": "`extract_mode=layout` places every text fragment by its position on the page, so cells that share a baseline come back on one line; the cleaner writes the gaps between them as ' | '."},
    wrong_notes={
        "columns_mode": "The page is split into a left and a right half and read half by half; the table is cut through the middle, between its third and fourth column.",
        "bigger_chunks": "A chunk holding the whole page holds all the cells, still one per line.",
        "retrieve_more": "More chunks of the same flattened text.",
    },
    observe=[cli("ask", Q1), cli("ask", Q2)],
)
