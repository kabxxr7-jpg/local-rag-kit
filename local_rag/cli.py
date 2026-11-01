"""Command line: python -m local_rag ingest|ask|doctor"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .errors import RagError


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="TOML file with settings (environment variables LOCAL_RAG_<NAME> override it)")
    p.add_argument("--store", dest="store_dir", help="folder of the vector store (default .rag-store)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m local_rag", description="Ask questions about PDFs with a local model (Ollama).")
    sub = parser.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="read PDFs into the store (running it again changes nothing)")
    _add_common(ing)
    ing.add_argument("paths", nargs="+", help="PDF files or folders of PDFs")
    ing.add_argument("--rebuild", action="store_true", help="throw the store away first (needed after changing the embedding model)")

    ask = sub.add_parser("ask", help="ask one question")
    _add_common(ask)
    ask.add_argument("question")
    ask.add_argument("-k", type=int, dest="k", help="how many passages to retrieve")
    ask.add_argument("--json", action="store_true", help="print the full result as JSON")
    ask.add_argument("--debug", action="store_true", help="show scores, what went into the prompt, what was dropped")
    ask.add_argument("--show-prompt", action="store_true", help="with --debug: also print the prompt sent to the model")

    doc = sub.add_parser("doctor", help="check the usual things that go wrong, in plain words")
    _add_common(doc)
    doc.add_argument("paths", nargs="*", help="PDFs or folders to check for extractable text")
    return parser


def _cmd_ingest(args, cfg) -> int:
    from .ingest import ingest

    report = ingest(args.paths, cfg, rebuild=args.rebuild)
    for name, n in report.ingested.items():
        print(f"ingested  {name}: {n} chunks")
    for name in report.unchanged:
        print(f"unchanged {name}")
    for name, why in report.failed.items():
        print(f"FAILED    {name}: {why}", file=sys.stderr)
    for w in report.warnings:
        print(f"warning   {w}")
    print(f"store: {report.total_chunks} chunks in total (removed {report.removed_chunks} old chunk(s) of re-ingested files) in '{cfg.store_dir}'")
    return 1 if report.failed else 0


def _cmd_ask(args, cfg) -> int:
    from .ask import ask

    result = ask(args.question, cfg)
    if args.json:
        data = {
            "question": result.question,
            "answer": result.answer,
            "refused": result.refused,
            "reason": result.reason,
            "citations": [{"file": f, "page": p} for f, p in result.citations],
            "best_score": result.best_score,
            "est_tokens": result.est_tokens,
            "prompt_tokens": result.prompt_tokens,
            "dropped": [{"file": h.source, "page": h.page, "score": round(h.score, 4)} for h in result.dropped],
            "warnings": result.warnings,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    print(f"Answer: {result.answer}")
    if result.citations:
        print("Sources: " + "; ".join(f"{f} p.{p}" for f, p in result.citations))
    elif result.reason == "below_threshold":
        print(f"(best match score {result.best_score:.3f} is below min_score {cfg.min_score}; the model was not asked)")
    for w in result.warnings:
        print(f"warning: {w}")
    if args.debug:
        print("\n-- debug --")
        print(f"retrieved {len(result.hits)} passage(s), k={cfg.k}, min_score={cfg.min_score}")
        for n, h in enumerate(result.hits, start=1):
            state = "dropped" if h in result.dropped else ("in prompt" if h in result.kept else "not used")
            print(f"  {n}. score {h.score:.3f}  {h.source} p.{h.page} chunk {h.index}  [{state}]  {h.text[:90]!r}")
        print(f"prompt: about {result.est_tokens} tokens estimated (budget {result.budget_tokens}, num_ctx {cfg.num_ctx}); server evaluated {result.prompt_tokens}")
        if args.show_prompt and result.prompt:
            print("\n-- prompt --\n" + result.prompt)
    return 0


def _cmd_doctor(args, cfg) -> int:
    from .doctor import render, run_doctor
    from .doctor import PROBLEM

    findings = run_doctor(cfg, args.paths)
    print(render(findings))
    return 1 if any(f.level == PROBLEM for f in findings) else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        overrides = {"store_dir": args.store_dir}
        if args.command == "ask":
            overrides["k"] = args.k
        cfg = load_config(file=args.config, overrides=overrides)
        return {"ingest": _cmd_ingest, "ask": _cmd_ask, "doctor": _cmd_doctor}[args.command](args, cfg)
    except RagError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
