"""Runs one scenario's check inside a world: `python checkproc.py <scenario-name> <backend>` with PYTHONPATH set to the world's package copy.

Prints one line per step (PASS / FAIL) and exits 1 if any step failed (or if there was no step at all).
The check imports `local_rag` from the world, never from the repository: this is verified first.
"""
from __future__ import annotations

import importlib
import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Ctx:
    def __init__(self, backend: str):
        self.backend = backend
        self.results: list[tuple[bool, str, str]] = []
        self.prompts: list[tuple[str, str, int | None]] = []
        self._cfg = None

    # ---- the pipeline under test ---------------------------------------------------------------------------------
    @property
    def cfg(self):
        from local_rag.config import load_config

        if self._cfg is None:
            self._cfg = load_config()
        return self._cfg

    def store(self):
        from local_rag.store import VectorStore

        return VectorStore.open(self.cfg.store_dir)

    def ask(self, question: str, **changes):
        from dataclasses import replace

        from local_rag.ask import ask
        from local_rag.llm import get_llm

        cfg = replace(self.cfg, **changes) if changes else self.cfg
        inner = get_llm(cfg)
        ctx = self

        class Recording:
            def generate(self, system, user):
                reply = inner.generate(system, user)
                ctx.prompts.append((system, user, reply.prompt_tokens))
                return reply

        return ask(question, cfg, llm=Recording())

    def retrieve(self, question: str, **changes):
        from dataclasses import replace

        from local_rag.ask import retrieve
        from local_rag.embed import get_embedder

        cfg = replace(self.cfg, **changes) if changes else self.cfg
        return retrieve(question, cfg, self.store(), get_embedder(cfg))

    def ingest(self, paths, rebuild: bool = False):
        from local_rag.ingest import ingest

        return ingest(list(paths), self.cfg, rebuild=rebuild)

    # ---- helpers for checks --------------------------------------------------------------------------------------
    @staticmethod
    def norm(text: str) -> str:
        return " ".join(text.split())

    def page_text(self, source: str, page: int) -> str:
        recs = [r for r in self.store().records.values() if r["source"] == source and r["page"] == page]
        return "\n".join(r["text"] for r in sorted(recs, key=lambda r: r["index"]))

    def pages_holding(self, fact: str) -> set[tuple[str, int]]:
        """Every (file, page) whose stored chunks contain the fact (compared with whitespace collapsed)."""
        return {(r["source"], r["page"]) for r in self.store().records.values() if self.norm(fact) in self.norm(r["text"])}

    def chunk_with(self, fact: str) -> list[str]:
        return [r["text"] for r in self.store().records.values() if self.norm(fact) in self.norm(r["text"])]

    # ---- recording verdicts --------------------------------------------------------------------------------------
    @contextmanager
    def step(self, label: str):
        try:
            yield
        except AssertionError as exc:
            self.results.append((False, label, str(exc) or "assertion failed"))
        except Exception as exc:  # noqa: BLE001 - a crash IS the symptom in many broken states
            self.results.append((False, label, f"{type(exc).__name__}: {str(exc)[:400]}"))
        else:
            self.results.append((True, label, ""))


def main(argv: list[str]) -> int:
    name, backend = argv[1], argv[2]
    import local_rag

    pkg = Path(local_rag.__file__).resolve()
    expected = Path(os.environ["PYTHONPATH"].split(os.pathsep)[0]).resolve()
    if expected not in pkg.parents:
        print(f"FAIL harness: local_rag was imported from {pkg}, not from the world ({expected})")
        return 3
    sys.path.insert(0, str(HERE))
    scenario = None
    for p in sorted((HERE / "defs").glob("s[0-9][0-9]_*.py")):
        module = importlib.import_module(f"defs.{p.stem}")
        if module.SCENARIO.name == name:
            scenario = module.SCENARIO
    if scenario is None:
        print(f"FAIL harness: no scenario called {name}")
        return 3
    ctx = Ctx(backend)
    try:
        scenario.check(ctx)
    except Exception:  # noqa: BLE001
        ctx.results.append((False, "the check itself crashed", traceback.format_exc(limit=3)[-600:]))
    for ok, label, why in ctx.results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"\n        {why}" if why else ""))
    if not ctx.results:
        print("FAIL  the check ran no step")
        return 1
    return 0 if all(ok for ok, _, _ in ctx.results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
