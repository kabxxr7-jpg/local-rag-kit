"""Citations name the wrong page: the page of a chunk was guessed from its position in the document."""
from __future__ import annotations

from framework import Edit, Scenario, cli

from .common import MAIN_PDFS, PROBES

NEW = '''def chunk_pages(pages: list[Page], cfg: Config) -> list[Chunk]:
    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    by_source: dict[str, list[Page]] = {}
    for p in pages:
        by_source.setdefault(p.source, []).append(p)
    splitter = make_splitter(cfg)
    chunks: list[Chunk] = []
    for source, ps in by_source.items():
        pieces = [x.strip() for x in splitter.split_text("\\n\\n".join(p.text for p in ps)) if x.strip()]
        for i, piece in enumerate(pieces):
            page = ps[0].page + (i * len(ps)) // len(pieces)
            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    return chunks


def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:'''
HEAD = "def chunk_pages(pages: list[Page], cfg: Config) -> list[Chunk]:"
BREAK = Edit("local_rag/chunk.py", HEAD, NEW)
FIX = Edit("local_rag/chunk.py", NEW, HEAD)


def check(ctx):
    for question, file, page, fact in PROBES:
        with ctx.step(f"'{fact}' is stored as {file} p.{page}"):
            where = ctx.pages_holding(fact)
            assert where == {(file, page)}, f"stored under {sorted(where)}"
    for question, file, page, fact in PROBES:
        with ctx.step(f"the best passage for a question about {file} p.{page} cites page {page}"):
            top = ctx.retrieve(question)[0]
            assert (top.source, top.page) == (file, page), f"best passage is cited as {top.source} p.{top.page}"


SCENARIO = Scenario(
    name="citations-wrong-page",
    title="Page numbers wrong: citations point at the wrong page",
    story=(
        "The inherited ingest joins all pages of a file, splits the text once and estimates each chunk's page as 'position in the list x pages / chunks'. "
        "That is exact only if every page has the same amount of text. These pages do not, so later pages are cited as earlier ones and some chunks contain two pages."
    ),
    pdfs=MAIN_PDFS,
    setup=[cli("ingest", "pdfs")],
    break_=[BREAK, cli("ingest", "--rebuild", "pdfs")],
    symptom=[cli("ask", "Who is the trust person for raising harassment concerns?"), cli("ask", "In which countries are the data centres located?")],
    diagnose=[cli("ask", "--debug", "Who is the trust person for raising harassment concerns?")],
    check=check,
    fixes={"split_page_by_page_and_rebuild": [FIX, cli("ingest", "--rebuild", "pdfs")]},
    wrongs={
        "add_one_to_every_page": [Edit("local_rag/chunk.py", "page = ps[0].page + (i * len(ps)) // len(pieces)", "page = ps[0].page + (i * len(ps)) // len(pieces) + 1"), cli("ingest", "--rebuild", "pdfs")],
        "cite_the_last_page": [Edit("local_rag/chunk.py", "page = ps[0].page + (i * len(ps)) // len(pieces)", "page = ps[-1].page"), cli("ingest", "--rebuild", "pdfs")],
        "fix_the_code_but_do_not_rebuild": [FIX],
    },
    fix_notes={"split_page_by_page_and_rebuild": "Chunk each page on its own, so the page is known by construction, then rebuild: the PDFs did not change, so a plain `ingest` would skip them."},
    wrong_notes={
        "add_one_to_every_page": "Right for a few chunks by luck, wrong for the rest: the error is not a constant.",
        "cite_the_last_page": "Every chunk of a file is cited with its last page.",
        "fix_the_code_but_do_not_rebuild": "The store still holds the wrongly numbered chunks: the files are unchanged, so nothing is re-read until `--rebuild`.",
    },
)
