"""`doctor`: look at the usual reasons a local RAG setup does not work and say, in plain words, what is wrong and what to do."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .errors import NoTextError, RagError
from .extract import extract_pdf
from .ingest import find_pdfs
from .prompt import estimate_tokens, token_budget
from .store import VectorStore

OK, WARN, PROBLEM = "ok", "warn", "problem"


@dataclass
class Finding:
    level: str
    title: str
    detail: str = ""


def _http_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - the host is the configured Ollama address
        return json.loads(resp.read().decode("utf-8"))


def _name_matches(wanted: str, installed: str) -> bool:
    if wanted == installed:
        return True
    return ":" not in wanted and installed == wanted + ":latest"


def check_ollama(cfg: Config) -> tuple[list[Finding], list[str] | None]:
    """Returns the findings and the installed model names (None when the server could not be reached)."""
    host = cfg.ollama_host.rstrip("/")
    try:
        version = _http_json(host + "/api/version").get("version", "?")
        tags = _http_json(host + "/api/tags")
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        return [
            Finding(
                PROBLEM,
                f"Ollama does not answer at {host}",
                f"({type(exc).__name__}: {getattr(exc, 'reason', exc)}) Ollama is not running, or it listens on another address. Open the Ollama app or run "
                f"`ollama serve`, then try again. If it runs elsewhere, set LOCAL_RAG_OLLAMA_HOST.",
            )
        ], None
    except ValueError as exc:
        return [Finding(PROBLEM, f"{host} answers, but not like Ollama", f"({exc}) Is another program using this port?")], None
    installed = [m.get("name", "") for m in tags.get("models", [])]
    findings = [Finding(OK, f"Ollama {version} answers at {host}", f"{len(installed)} model(s) installed: {', '.join(installed) or 'none'}")]
    for role, wanted in (("embedding model", cfg.embed_model), ("language model", cfg.llm_model)):
        if cfg.embedder == "fake" and role == "embedding model":
            continue
        if cfg.llm == "fake" and role == "language model":
            continue
        if any(_name_matches(wanted, name) for name in installed):
            findings.append(Finding(OK, f"The {role} '{wanted}' is installed"))
        else:
            findings.append(
                Finding(
                    PROBLEM,
                    f"The {role} '{wanted}' is not pulled",
                    f"Ollama is running but does not have it. Run: ollama pull {wanted}   (installed now: {', '.join(installed) or 'none'}). "
                    f"Or set the model name to one of those.",
                )
            )
    return findings, installed


def check_store(cfg: Config, embedder=None, installed: list[str] | None = None) -> list[Finding]:
    try:
        store = VectorStore.open(cfg.store_dir)
    except RagError as exc:
        return [Finding(PROBLEM, f"The store in '{cfg.store_dir}' cannot be read", str(exc))]
    if not store.exists:
        return [Finding(WARN, f"No store in '{cfg.store_dir}' yet", "Nothing has been ingested here. Run: python -m local_rag ingest <pdf or folder>")]
    stats = store.stats()
    findings = [Finding(OK, f"Store '{cfg.store_dir}': {stats['chunks']} chunks from {len(stats['files'])} file(s)", f"built with '{stats['embed_model']}', {stats['dim']} dimensions")]
    if stats["embed_model"] != cfg.embed_model:
        findings.append(
            Finding(
                PROBLEM,
                f"The store was built with '{stats['embed_model']}' but embed_model is now '{cfg.embed_model}'",
                f"Vectors from two models cannot be compared (the sizes differ: {stats['dim']} here). Set embed_model back to '{stats['embed_model']}' or rebuild: "
                f"python -m local_rag ingest --rebuild <pdfs>",
            )
        )
        return findings
    if embedder is not None and (cfg.embedder == "fake" or installed is not None):
        try:
            dim = len(embedder.embed_query("dimension probe"))
        except RagError as exc:
            findings.append(Finding(PROBLEM, "Could not embed a test sentence", str(exc)))
            return findings
        if dim != stats["dim"]:
            findings.append(
                Finding(
                    PROBLEM,
                    f"Dimension mismatch: the store has {stats['dim']}-dimensional vectors, '{cfg.embed_model}' returns {dim}",
                    "The model behind that name changed, or the store came from another setup. Rebuild: python -m local_rag ingest --rebuild <pdfs>",
                )
            )
        else:
            findings.append(Finding(OK, f"The embedding model returns {dim} dimensions, the same as the store"))
    return findings


def check_budget(cfg: Config) -> list[Finding]:
    worst = cfg.k * (cfg.chunk_size + 40)
    est = estimate_tokens("x" * worst, cfg.chars_per_token)
    budget = token_budget(cfg)
    if est > budget:
        return [
            Finding(
                WARN,
                f"k={cfg.k} chunks of {cfg.chunk_size} characters can need about {est} tokens, but num_ctx={cfg.num_ctx} leaves {budget}",
                f"A full set of passages will not always fit. With on_overflow={cfg.on_overflow!r} the lowest ranked passages are "
                f"{'dropped (and reported)' if cfg.on_overflow == 'trim' else 'not tried: the question is refused'}. "
                f"A model server that is handed too much silently cuts the prompt, so raise num_ctx or lower k / chunk_size.",
            )
        ]
    return [Finding(OK, f"A full set of passages (about {est} tokens) fits into the {budget} tokens left of num_ctx={cfg.num_ctx}")]


def check_pdfs(cfg: Config, paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    try:
        pdfs = find_pdfs(list(paths))
    except RagError as exc:
        return [Finding(PROBLEM, "PDF path problem", str(exc))]
    for pdf in pdfs:
        try:
            ex = extract_pdf(pdf, cfg.extract_mode)
        except NoTextError as exc:
            findings.append(Finding(PROBLEM, f"{pdf.name}: no extractable text", str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - a broken PDF should be reported, not crash the doctor
            findings.append(Finding(PROBLEM, f"{pdf.name}: cannot be read", f"{type(exc).__name__}: {exc}. The file may be damaged or password protected."))
            continue
        if ex.empty_pages:
            findings.append(Finding(WARN, f"{pdf.name}: {len(ex.empty_pages)} of {ex.page_count} page(s) have no text", f"pages {', '.join(map(str, ex.empty_pages))} are probably images; they will be skipped (no OCR)."))
        else:
            findings.append(Finding(OK, f"{pdf.name}: text found on all {ex.page_count} page(s)"))
    return findings


def run_doctor(cfg: Config, pdf_paths: list[str] | None = None, embedder=None) -> list[Finding]:
    findings: list[Finding] = []
    installed: list[str] | None = None
    if cfg.embedder == "ollama" or cfg.llm == "ollama":
        found, installed = check_ollama(cfg)
        findings += found
    if embedder is None and (cfg.embedder == "fake" or installed is not None):
        from .embed import get_embedder

        embedder = get_embedder(cfg)
    findings += check_store(cfg, embedder, installed)
    findings += check_budget(cfg)
    if pdf_paths:
        findings += check_pdfs(cfg, pdf_paths)
    return findings


def render(findings: list[Finding]) -> str:
    marks = {OK: "[ok]     ", WARN: "[warning]", PROBLEM: "[PROBLEM]"}
    lines = []
    for f in findings:
        lines.append(f"{marks[f.level]} {f.title}")
        if f.detail:
            lines.append(f"          {f.detail}")
    problems = sum(1 for f in findings if f.level == PROBLEM)
    lines.append("")
    lines.append(f"{problems} problem(s)." if problems else "No problems found.")
    return "\n".join(lines)
