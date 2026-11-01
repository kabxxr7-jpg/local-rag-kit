#!/usr/bin/env python3
"""Run eval/questions.json against the real Ollama models and report the numbers.

    python scripts/run_eval.py                       full run, writes docs/eval-results.json and docs/eval-table.md
    python scripts/run_eval.py --only H01,K03 --no-write

What is measured, separately (a miss in one does not hide behind the other):
  retrieval   is the right file AND page among the retrieved passages (hit@k) / is it the best passage (hit@1);
              also, stricter: does a retrieved (or a prompted) passage contain the accepted string at all
  answer      does the answer contain one of the expected strings (case-insensitive substring) -- it cannot judge paraphrases
  citation    does the answer cite the right file and page
  refusal     unanswerable questions: refused (below the threshold or declined by the model) is right, answered is a wrong answer

One request at a time; strict load gate before the job, a looser pause (scripts/loadgate.py) before each question.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from loadgate import wait_between, wait_for_calm  # noqa: E402
from local_rag import __version__  # noqa: E402
from local_rag.ask import ask  # noqa: E402
from local_rag.config import Config, load_config  # noqa: E402
from local_rag.doctor import _http_json  # noqa: E402
from local_rag.embed import get_embedder  # noqa: E402
from local_rag.ingest import ingest  # noqa: E402
from local_rag.llm import get_llm  # noqa: E402
from local_rag.store import VectorStore  # noqa: E402

PDFS = ["harbor-pine-handbook.pdf", "aurora-kettle-manual.pdf", "meridian-price-list.pdf"]


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def run(cfg: Config, only: set[str] | None, gate: bool, log=print, start_gate: str = "strict") -> dict:
    questions = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    rows = []
    with tempfile.TemporaryDirectory(prefix="lrk-eval-") as tmp:
        cfg = replace(cfg, store_dir=str(Path(tmp) / "store"))
        if gate:
            (wait_for_calm if start_gate == "strict" else wait_between)("ingesting for the eval")
        started = time.time()
        report = ingest([ROOT / "samples" / "pdfs" / n for n in PDFS], cfg)
        ingest_seconds = round(time.time() - started, 1)
        store, embedder, llm = VectorStore.open(cfg.store_dir), get_embedder(cfg), get_llm(cfg)
        log(f"ingested {report.total_chunks} chunks in {ingest_seconds} s")

        for kind in ("answerable", "unanswerable"):
            for q in questions[kind]:
                if only and q["id"] not in only:
                    continue
                if gate:
                    wait_between(f"question {q['id']}")
                t0 = time.time()
                r = ask(q["q"], cfg, store=store, embedder=embedder, llm=llm)
                seconds = round(time.time() - t0, 1)
                row = {
                    "id": q["id"], "kind": kind, "question": q["q"], "answer": r.answer, "refused": r.refused, "reason": r.reason,
                    "best_score": round(r.best_score, 3) if r.best_score is not None else None,
                    "retrieved": [[h.source, h.page, round(h.score, 3)] for h in r.hits],
                    "citations": [list(c) for c in r.citations], "warnings": r.warnings, "prompt_tokens": r.prompt_tokens, "seconds": seconds,
                }
                if kind == "answerable":
                    want = (q["file"], q["page"])
                    got = [(h.source, h.page) for h in r.hits]
                    row.update(
                        expected_file=q["file"], expected_page=q["page"], expected=q["expected"],
                        hit_at_k=want in got, hit_at_1=bool(got) and got[0] == want,
                        correct=any(norm(e) in norm(r.answer) for e in q["expected"]) and not r.refused,
                        cited_right=want in [tuple(c) for c in r.citations],
                        # stricter than the page: does a retrieved / a prompted passage actually contain the fact?
                        fact_in_top_k=any(norm(e) in norm(h.text) for h in r.hits for e in q["expected"]),
                        fact_in_prompt=any(norm(e) in norm(h.text) for h in r.kept for e in q["expected"]),
                    )
                else:
                    row["wrongly_answered"] = not r.refused
                rows.append(row)
                mark = (("hit " if row["hit_at_k"] else "MISS") + (" ok " if row["correct"] else " BAD")) if kind == "answerable" else ("refused " if r.refused else "ANSWERED")
                log(f"{q['id']} {mark} {seconds:5.1f}s  best {row['best_score']}  {r.answer[:90]!r}")

    ans = [r for r in rows if r["kind"] == "answerable"]
    una = [r for r in rows if r["kind"] == "unanswerable"]
    try:
        server = _http_json(cfg.ollama_host.rstrip("/") + "/api/version").get("version")
    except Exception:  # noqa: BLE001
        server = None
    summary = {
        "answerable": len(ans),
        "hit_at_k": sum(r["hit_at_k"] for r in ans),
        "hit_at_1": sum(r["hit_at_1"] for r in ans),
        "correct": sum(r["correct"] for r in ans),
        "correct_and_cited_right": sum(r["correct"] and r["cited_right"] for r in ans),
        "correct_given_hit": sum(r["correct"] for r in ans if r["hit_at_k"]),
        "fact_in_top_k": sum(r["fact_in_top_k"] for r in ans),
        "fact_in_prompt": sum(r["fact_in_prompt"] for r in ans),
        "asked_with_fact_in_prompt": sum(1 for r in ans if r["fact_in_prompt"]),
        "wrong_although_fact_in_prompt": [r["id"] for r in ans if r["fact_in_prompt"] and not r["correct"]],
        "hit_but_wrong": [r["id"] for r in ans if r["hit_at_k"] and not r["correct"]],
        "miss_but_correct": [r["id"] for r in ans if not r["hit_at_k"] and r["correct"]],
        "false_refusals": [r["id"] for r in ans if r["refused"]],
        "unanswerable": len(una),
        "correctly_refused": sum(1 for r in una if r["refused"]),
        "wrongly_answered": [r["id"] for r in una if not r["refused"]],
        "seconds_total": round(sum(r["seconds"] for r in rows), 1),
        "seconds_median": sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else None,
    }
    return {
        "when": time.strftime("%Y-%m-%d %H:%M:%S"), "kit_version": __version__, "python": platform.python_version(), "ollama_server": server,
        "models": {"embedding": cfg.embed_model, "llm": cfg.llm_model},
        "settings": {k: v for k, v in asdict(cfg).items() if k in ("k", "min_score", "chunk_size", "chunk_overlap", "extract_mode", "num_ctx", "num_predict", "on_overflow")},
        "chunks": report.total_chunks, "ingest_seconds": ingest_seconds, "summary": summary, "rows": rows,
    }


def table(result: dict) -> str:
    lines = ["| id | question | retrieval (file p.page, score) | answer | right? | cited | note |", "|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        top = r["retrieved"][0] if r["retrieved"] else None
        top_s = f"{top[0].replace('.pdf', '')} p.{top[1]} ({top[2]})" if top else "-"
        answer = r["answer"].replace("|", "/").replace("\n", " ")
        if len(answer) > 160:
            answer = answer[:157] + "..."
        if r["kind"] == "answerable":
            where = f"{r['expected_file'].replace('.pdf', '')} p.{r['expected_page']}"
            note = "retrieval hit" if r["hit_at_k"] else f"retrieval MISS (wanted {where})"
            if r["hit_at_k"] and not r["hit_at_1"]:
                note = "hit, not first"
            lines.append(f"| {r['id']} | {r['question']} | {top_s} | {answer} | {'yes' if r['correct'] else 'NO'} | {'yes' if r['cited_right'] else 'no'} | {note} |")
        else:
            lines.append(f"| {r['id']} | {r['question']} | {top_s} | {answer} | {'refused (right)' if r['refused'] else 'ANSWERED (wrong)'} | - | {r['reason'] or 'answered'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate retrieval, answers and refusals on eval/questions.json with the real Ollama models.")
    ap.add_argument("--only", help="comma separated question ids")
    ap.add_argument("--no-gate", action="store_true", help="skip the load gate")
    ap.add_argument("--start-gate", choices=["strict", "between"], default="strict", help="strict: load < 6 and swap < 4000 MB before starting. between: use the looser limits (when this job directly follows another one that passed the strict gate)")
    ap.add_argument("--no-write", action="store_true", help="print only, write no files")
    ap.add_argument("--out", default=str(ROOT / "docs" / "eval-results.json"))
    ap.add_argument("--table", default=str(ROOT / "docs" / "eval-table.md"))
    args = ap.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    result = run(load_config(), only, gate=not args.no_gate, start_gate=args.start_gate)
    print(json.dumps(result["summary"], indent=1))
    if not args.no_write:
        Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        Path(args.table).write_text(table(result), encoding="utf-8")
        print("wrote", args.out, "and", args.table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
