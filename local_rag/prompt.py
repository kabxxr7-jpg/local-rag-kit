"""Prompt assembly and the prompt size check.

The size check exists because a model server that is handed more text than ``num_ctx`` does not fail: it silently cuts the
prompt (see docs/REAL-RUNS.md for what the real server did) and the model answers from whatever is left.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Config
from .store import Hit

REFUSAL_TEXT = "I could not find an answer to that in the ingested documents."

SYSTEM = (
    "You answer questions using ONLY the numbered passages from the user's documents. "
    "If the passages do not contain the answer, reply with exactly this sentence and nothing else: "
    f"{REFUSAL_TEXT} "
    "Keep the answer short. Do not use any knowledge outside the passages."
)

# English prose is about 4 characters per token on the models used here (measured, docs/REAL-RUNS.md). A server that reports
# far fewer prompt tokens than the prompt has characters for 5.5 characters each has not read the whole prompt.
MAX_PLAUSIBLE_CHARS_PER_TOKEN = 5.5

# room for the chat template's role markers and the "Question:" scaffolding the estimate does not see
TEMPLATE_RESERVE_TOKENS = 64


@dataclass
class Prompt:
    system: str
    user: str
    kept: list[Hit]  # passages that are in the prompt, best first
    dropped: list[Hit]  # passages cut to make the prompt fit; always reported to the caller
    est_tokens: int
    budget_tokens: int


def format_passage(number: int, hit: Hit) -> str:
    return f"[{number}] ({hit.source}, page {hit.page})\n{hit.text}"


def render(question: str, hits: list[Hit]) -> str:
    passages = "\n\n".join(format_passage(n, h) for n, h in enumerate(hits, start=1))
    return f"Passages:\n\n{passages}\n\nQuestion: {question}\nAnswer:"


def estimate_tokens(text: str, chars_per_token: float) -> int:
    return math.ceil(len(text) / chars_per_token)


def token_budget(cfg: Config) -> int:
    """Tokens the prompt may use: the window minus the room kept for the answer and the template."""
    return cfg.num_ctx - cfg.num_predict - TEMPLATE_RESERVE_TOKENS


def assemble(question: str, hits: list[Hit], cfg: Config) -> Prompt | None:
    """Build the prompt. Passages that do not fit are dropped from the end (lowest score first), never silently:
    they are returned in ``dropped``. Returns None when nothing fits (or when ``on_overflow`` is "refuse" and something would
    have to be cut), and the caller then refuses instead of asking."""
    budget = token_budget(cfg)
    kept = list(hits)
    dropped: list[Hit] = []
    while kept:
        est = estimate_tokens(SYSTEM, cfg.chars_per_token) + estimate_tokens(render(question, kept), cfg.chars_per_token)
        if est <= budget:
            return Prompt(SYSTEM, render(question, kept), kept, dropped, est, budget)
        if cfg.on_overflow == "refuse":
            return None
        dropped.insert(0, kept.pop())
    return None
