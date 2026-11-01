"""Prints the best retrieval score for probe questions that are NOT in eval/questions.json, to pick min_score.

    python scripts/calibrate.py samples/pdfs        (needs the real Ollama; uses a temporary store)

The default min_score in config.py was chosen from this output, never from the eval questions.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loadgate import wait_between  # noqa: E402
from local_rag.ask import retrieve  # noqa: E402
from local_rag.config import load_config  # noqa: E402
from local_rag.embed import get_embedder  # noqa: E402
from local_rag.ingest import ingest  # noqa: E402
from local_rag.store import VectorStore  # noqa: E402

ANSWERABLE = [
    "What is the length of the standard working week?",
    "How many weeks of parental leave does the other parent get?",
    "What is the equipment budget for a laptop?",
    "How many temperature presets does the kettle have?",
    "What is the minimum amount of water for the kettle?",
    "What is the price of the Starter plan?",
    "How long is the free trial?",
    "What happens to deleted files in Meridian storage?",
]
UNANSWERABLE = [
    "What is the best programming language for beginners?",
    "How tall is Mount Everest?",
    "What colour is the Aurora AK-200 kettle?",
    "Does Harbor & Pine Studio offer a pension plan?",
    "Which payment methods does Meridian accept?",
    "How do I bake sourdough bread?",
    "Who is the managing partner of the studio?",
    "What is the weather in Lisbon today?",
]


def main() -> int:
    docs = sys.argv[1] if len(sys.argv) > 1 else "samples/pdfs"
    wait_between("calibrating")  # a small job, usually run right after another one: the looser limits
    with tempfile.TemporaryDirectory(prefix="lrk-calibrate-") as tmp:
        cfg = replace(load_config(), store_dir=tmp)
        ingest([docs], cfg)
        store, emb = VectorStore.open(tmp), get_embedder(cfg)
        for label, questions in (("ANSWERABLE", ANSWERABLE), ("UNANSWERABLE", UNANSWERABLE)):
            scores = []
            print(f"--- {label}")
            for q in questions:
                hits = retrieve(q, replace(cfg, k=1), store, emb)
                scores.append(hits[0].score)
                print(f"  {hits[0].score:.3f}  {hits[0].source} p.{hits[0].page}  {q}")
            print(f"  min {min(scores):.3f}  max {max(scores):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
