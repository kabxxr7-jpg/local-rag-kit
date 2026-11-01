"""The store was built with 768-dimensional vectors; the embedding settings changed and nobody rebuilt it."""
from __future__ import annotations

from framework import Edit, Env, Rm, Scenario, cli

from .common import MAIN_PDFS, PROBES

QUESTION = "How many days of paid annual leave does each employee get per year?"

# What the inherited pipeline lacks: any comparison between the store and the vectors it is given.
GUARDS = [
    Edit("local_rag/ask.py", "store.check_compatible(embedder.model)", "pass"),
    Edit("local_rag/store.py", "if query.shape[1] != self.dim:", "if False:"),
    Edit("local_rag/store.py", "if matrix.shape[1] != self.dim:", "if False:"),
    Edit("local_rag/ingest.py", "store.check_compatible(embedder.model)", "pass"),
    Edit("local_rag/ingest.py", "store.check_compatible(embedder.model, len(vectors[0]))", "pass"),
]


def settings_changed(backend: str):
    # ollama: nomic-embed-text asked for 256-dimensional vectors (it supports shorter ones); fake: another vector size
    return [Env("EMBED_DIMENSIONS", "256")] if backend == "ollama" else [Env("FAKE_DIM", "128")]


def settings_reverted(backend: str):
    return [Env("EMBED_DIMENSIONS", None)] if backend == "ollama" else [Env("FAKE_DIM", None)]


def check(ctx):
    from local_rag.embed import get_embedder

    with ctx.step("the store and the configured embedder agree on the vector size"):
        store, dim = ctx.store(), len(get_embedder(ctx.cfg).embed_query("size probe"))
        assert store.dim == dim, f"the store holds {store.dim}-dimensional vectors, the embedder returns {dim}"
    for question, file, page, _ in PROBES:
        with ctx.step(f"a question about {file} p.{page} finds that page among the top {ctx.cfg.k}"):
            pages = [(h.source, h.page) for h in ctx.retrieve(question)]
            assert (file, page) in pages, f"got {pages}"


SCENARIO = Scenario(
    name="stale-store-dim-mismatch",
    title="Stale vector store: the embedding settings changed, the store did not",
    story=(
        "The store was built with 768-dimensional vectors. Later the embedding settings were changed (here: nomic-embed-text was asked for "
        "256-dimensional vectors, which it supports) and nobody rebuilt the store. The inherited pipeline never compares the store with the vectors "
        "it is given, so the first question crashes inside faiss."
    ),
    pdfs=MAIN_PDFS,
    setup=[cli("ingest", "pdfs")],
    break_=lambda backend: GUARDS + settings_changed(backend),
    symptom=[cli("ask", QUESTION)],
    diagnose=[cli("doctor")],
    check=check,
    fixes={
        "rebuild_the_store": lambda backend: [cli("ingest", "--rebuild", "pdfs")],
        "revert_the_setting": settings_reverted,
    },
    wrongs={
        "reingest_without_rebuild": [cli("ingest", "pdfs")],
        "delete_meta_json": [Rm("store/meta.json")],
        "swallow_the_assertion": [Edit("local_rag/store.py", "scores, ids = self._index.search(query, min(k, len(self.records)))", "try:\n            scores, ids = self._index.search(query, min(k, len(self.records)))\n        except AssertionError:\n            return []")],
        "lower_the_threshold": [Env("MIN_SCORE", "0.0")],
    },
    fix_notes={
        "rebuild_the_store": "`ingest --rebuild` throws the old vectors away and embeds every chunk again with the current settings.",
        "revert_the_setting": "Give the embedder back the size the store was built with. Nothing is re-embedded.",
    },
    wrong_notes={
        "reingest_without_rebuild": "The PDFs did not change, so `ingest` skips them as 'unchanged': the store keeps the old vector size.",
        "delete_meta_json": "Removes the record of which model built the store; the store then looks empty. The vectors are not fixed.",
        "swallow_the_assertion": "Turns the crash into 'no results'. Every question is now refused, which looks like a threshold problem.",
        "lower_the_threshold": "The threshold has nothing to do with it: the crash happens before any score exists.",
    },
    observe=[cli("ask", "--debug", QUESTION)],
)
