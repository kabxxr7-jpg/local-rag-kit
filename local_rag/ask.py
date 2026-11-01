"""Answer a question: retrieve, refuse when the match is weak, check the prompt size, generate, cite."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .embed import Embedder, get_embedder
from .llm import LLM, get_llm
from .prompt import MAX_PLAUSIBLE_CHARS_PER_TOKEN, REFUSAL_TEXT, assemble, token_budget
from .store import Hit, VectorStore


@dataclass
class AskResult:
    question: str
    answer: str
    refused: bool
    reason: str | None  # None, "below_threshold", "context_too_large", "model_declined"
    citations: list[tuple[str, int]] = field(default_factory=list)  # (file name, page), best first, no repeats
    hits: list[Hit] = field(default_factory=list)  # everything retrieved
    kept: list[Hit] = field(default_factory=list)  # what went into the prompt
    dropped: list[Hit] = field(default_factory=list)  # retrieved but cut to fit the context window
    best_score: float | None = None
    est_tokens: int | None = None
    budget_tokens: int | None = None
    prompt_tokens: int | None = None  # as reported by the server
    warnings: list[str] = field(default_factory=list)
    prompt: str | None = None


def retrieve(question: str, cfg: Config, store: VectorStore, embedder: Embedder) -> list[Hit]:
    store.check_compatible(embedder.model)
    vector = embedder.embed_query(question)
    return store.search(vector, cfg.k)


def _citations(hits: list[Hit]) -> list[tuple[str, int]]:
    seen: list[tuple[str, int]] = []
    for h in hits:
        key = (h.source, h.page)
        if key not in seen:
            seen.append(key)
    return seen


def ask(question: str, cfg: Config, *, store: VectorStore | None = None, embedder: Embedder | None = None, llm: LLM | None = None) -> AskResult:
    store = store or VectorStore.open(cfg.store_dir)
    embedder = embedder or get_embedder(cfg)
    hits = retrieve(question, cfg, store, embedder)
    best = hits[0].score if hits else None
    result = AskResult(question, REFUSAL_TEXT, True, "below_threshold", hits=hits, best_score=best, budget_tokens=token_budget(cfg))

    if best is None or best < cfg.min_score:
        return result

    usable = [h for h in hits if h.score >= cfg.min_score]  # weak passages are noise: the model never sees them
    prompt = assemble(question, usable, cfg)
    if prompt is None:
        result.reason = "context_too_large"
        result.warnings.append(
            f"The retrieved passages do not fit into num_ctx={cfg.num_ctx} (budget {token_budget(cfg)} tokens) and on_overflow={cfg.on_overflow!r}, "
            f"so the model was not asked. Raise num_ctx, lower k or chunk_size, or set on_overflow=trim."
        )
        return result
    result.kept, result.dropped, result.est_tokens, result.prompt = prompt.kept, prompt.dropped, prompt.est_tokens, prompt.user
    if prompt.dropped:
        result.warnings.append(
            f"Context trimmed: {len(prompt.dropped)} of {len(hits)} retrieved passage(s) did not fit into num_ctx={cfg.num_ctx} "
            f"(estimated {prompt.est_tokens} tokens, budget {prompt.budget_tokens}) and were left out: "
            + ", ".join(f"{h.source} p.{h.page}" for h in prompt.dropped)
        )

    llm = llm or get_llm(cfg)
    reply = llm.generate(prompt.system, prompt.user)
    result.prompt_tokens = reply.prompt_tokens
    if reply.prompt_tokens:
        chars = len(prompt.system) + len(prompt.user)
        if reply.prompt_tokens >= cfg.num_ctx - 8 or chars / reply.prompt_tokens > MAX_PLAUSIBLE_CHARS_PER_TOKEN:
            result.warnings.append(
                f"The server evaluated only {reply.prompt_tokens} tokens of a prompt of {chars} characters (num_ctx={cfg.num_ctx}): "
                f"it has probably cut the prompt. Do not trust this answer."
            )

    result.answer = reply.text
    if REFUSAL_TEXT.lower().rstrip(".") in reply.text.lower():
        result.answer, result.reason, result.refused = REFUSAL_TEXT, "model_declined", True
        return result
    result.refused, result.reason = False, None
    result.citations = _citations(prompt.kept)
    return result
