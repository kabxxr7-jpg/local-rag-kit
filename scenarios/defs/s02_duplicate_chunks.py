"""Re-ingesting the same PDFs doubles the chunks, and the duplicates crowd the top-k."""
from __future__ import annotations

from framework import Edit, Env, Scenario, cli

from .common import MAIN_PDFS

QUESTION = "How many days of paid annual leave does each employee get per year?"

BREAK_EDITS = [
    # random ids: the same chunk gets a new id every run, so "already stored" can never be recognised
    Edit(
        "local_rag/chunk.py",
        "def chunk_id(source: str, page: int, index: int, text: str) -> str:",
        'def chunk_id(source: str, page: int, index: int, text: str) -> str:\n    import uuid\n\n    return uuid.uuid4().hex[:24]\n\n\ndef _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:',
    ),
    # never skip a file, never remove what an earlier run stored for it
    Edit("local_rag/ingest.py", 'if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):', "if False:"),
    Edit("local_rag/ingest.py", "report.removed_chunks += store.remove_source(pdf.name)", "pass"),
]
ids_back = BREAK_EDITS[0]
unskip_back = BREAK_EDITS[1]
remove_back = BREAK_EDITS[2]


def inverse(e: Edit) -> Edit:
    return Edit(e.path, e.replace, e.find)


def check(ctx):
    import re

    pdfs = ["pdfs"]
    store = ctx.store()
    before = len(store)
    with ctx.step("ingesting the same PDFs again leaves the number of chunks unchanged"):
        ctx.ingest(pdfs)
        after = len(ctx.store())
        assert after == before, f"{before} chunks before, {after} after a repeat ingest"
    with ctx.step("no passage is stored twice"):
        seen: dict[tuple, int] = {}
        for r in ctx.store().records.values():
            key = (r["source"], r["page"], r["text"])
            seen[key] = seen.get(key, 0) + 1
        twice = sum(1 for n in seen.values() if n > 1)
        assert twice == 0, f"{twice} passages are stored more than once ({len(ctx.store())} chunks for {len(seen)} different passages)"
    with ctx.step("the passages retrieved for a question are all different"):
        texts = [h.text for h in ctx.retrieve(QUESTION)]
        assert len(texts) == len(set(texts)), f"{len(texts)} passages retrieved, {len(set(texts))} different"


SCENARIO = Scenario(
    name="duplicate-chunks",
    title="Duplicated chunks after re-ingest",
    story=(
        "Every run of `ingest` adds the same chunks again. After a few runs the top-k is filled with copies of one passage, the prompt repeats itself and "
        "the store grows without bound. The inherited code gives each chunk a random id and never replaces what an earlier run stored for the same file."
    ),
    pdfs=MAIN_PDFS,
    setup=[cli("ingest", "pdfs")],
    break_=BREAK_EDITS + [cli("ingest", "pdfs"), cli("ingest", "pdfs")],
    symptom=[cli("ingest", "pdfs"), cli("ask", "--debug", QUESTION)],
    diagnose=[cli("doctor")],
    check=check,
    fixes={
        "content_ids_replace_and_rebuild": [inverse(ids_back), inverse(unskip_back), inverse(remove_back), cli("ingest", "--rebuild", "pdfs")],
        "content_ids_and_replace_only": [inverse(ids_back), inverse(remove_back), cli("ingest", "--rebuild", "pdfs")],
    },
    wrongs={
        "rebuild_only": [cli("ingest", "--rebuild", "pdfs")],
        "dedupe_when_answering": [Edit("local_rag/ask.py", "return store.search(vector, cfg.k)", "seen, out = set(), []\n    for h in store.search(vector, cfg.k * 4):\n        if h.text not in seen:\n            seen.add(h.text)\n            out.append(h)\n    return out[: cfg.k]")],
        "raise_k": [Env("K", "12")],
    },
    fix_notes={
        "content_ids_replace_and_rebuild": "The id is a hash of file, page, position and text, a file that did not change is skipped, a file that did is replaced, and one rebuild removes the copies already stored.",
        "content_ids_and_replace_only": "Same, without the 'unchanged' shortcut: every run re-embeds but replaces what the file had before, so there are still no copies.",
    },
    wrong_notes={
        "rebuild_only": "Cleans the store once. The next ingest duplicates again because the code is unchanged.",
        "dedupe_when_answering": "Hides the copies from the top-k only. The store, its size and the next ingest are as bad as before.",
        "raise_k": "More passages retrieved means more copies retrieved.",
    },
)
