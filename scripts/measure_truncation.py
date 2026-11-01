#!/usr/bin/env python3
"""What does the Ollama server do with a prompt that is longer than num_ctx?  (needs the real Ollama; uses a temporary store)

    python scripts/measure_truncation.py

Sends the same question with more and more passages and prints, for each size, how many characters the prompt had and how many
prompt tokens the server says it evaluated. The numbers behind docs/REAL-RUNS.md ("Context window") and the two defences in
local_rag/ask.py come from this script: the characters-per-token ratio that justifies chars_per_token, and the point where the
server starts to cut without saying so.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from loadgate import wait_for_calm  # noqa: E402
from local_rag.ask import retrieve  # noqa: E402
from local_rag.config import load_config  # noqa: E402
from local_rag.embed import get_embedder  # noqa: E402
from local_rag.ingest import ingest  # noqa: E402
from local_rag.llm import OllamaLLM  # noqa: E402
from local_rag.prompt import SYSTEM, render  # noqa: E402
from local_rag.store import VectorStore  # noqa: E402

QUESTION = "How many days of paid annual leave does each employee get per year?"
PDFS = [ROOT / "samples" / "pdfs" / n for n in ("harbor-pine-handbook.pdf", "aurora-kettle-manual.pdf", "meridian-price-list.pdf")]


def main() -> int:
    wait_for_calm("measuring truncation")
    with tempfile.TemporaryDirectory(prefix="lrk-trunc-") as tmp:
        cfg = replace(load_config(), store_dir=tmp)
        ingest(PDFS, cfg)
        hits = retrieve(QUESTION, replace(cfg, k=24), VectorStore.open(tmp), get_embedder(cfg))
        print(f"{len(hits)} passages available; question: {QUESTION}")
        print(f"{'num_ctx':>7} {'passages':>8} {'chars':>6} {'server prompt tokens':>21} {'chars/token':>12}  answer")
        for num_ctx in (4096, 1024):
            for n in (2, 4, 6, 8, 12, 16):
                if n > len(hits):
                    continue
                c = replace(cfg, num_ctx=num_ctx, num_predict=256)
                user = render(QUESTION, hits[:n])
                reply = OllamaLLM(c).generate(SYSTEM, user)
                chars = len(SYSTEM) + len(user)
                ratio = chars / reply.prompt_tokens if reply.prompt_tokens else float("nan")
                print(f"{num_ctx:>7} {n:>8} {chars:>6} {reply.prompt_tokens!s:>21} {ratio:>12.2f}  {reply.text[:50]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
