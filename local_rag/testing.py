"""Test doubles: a deterministic fake embedder and a fake language model. No network, no models, no randomness.

``FakeEmbedder`` is a hashed bag of words: texts that share words get similar vectors, which is enough for the offline tests
and scenarios to see the right page win. ``FakeLLM`` answers with the context sentence that shares most words with the question
(so a prompt that lacks the right passage gives a wrong answer, as with a real model, only deterministic).
Neither says anything about how a real model behaves: that is what the live tests and docs/REAL-RUNS.md are for.
"""
from __future__ import annotations

import hashlib
import math
import re

from .llm import Reply

_WORD = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*")
_STOP = frozenset(
    "a an and are as at be by can do does for from how i if in is it its of on or per that the their there this to was what when where which who why will with you your".split()
)


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


class FakeEmbedder:
    def __init__(self, dim: int = 256, model: str = "fake-embed"):
        self.dim = dim
        self.model = model
        self.calls = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for w in words(text):
            h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vec(text)


class FakeLLM:
    """Extractive stand-in. Records every prompt it was given in ``self.prompts``."""

    def __init__(self, reply: str | None = None, prompt_tokens: int | None = None):
        self.prompts: list[tuple[str, str]] = []
        self._reply = reply
        self._prompt_tokens = prompt_tokens

    def generate(self, system: str, user: str) -> Reply:
        self.prompts.append((system, user))
        if self._reply is not None:
            return Reply(self._reply, self._prompt_tokens, 10)
        context, _, tail = user.partition("\n\nQuestion:")
        question = tail.partition("\nAnswer:")[0]
        q = set(words(question))
        best, best_score = "", 0
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", context):
            s = sentence.strip()
            if not s or s.startswith("[") and s.endswith(")"):
                continue
            score = len(q & set(words(s)))
            if score > best_score:
                best, best_score = s, score
        if best_score == 0:
            from .prompt import REFUSAL_TEXT

            return Reply(REFUSAL_TEXT, self._prompt_tokens, 10)
        return Reply(best, self._prompt_tokens, 10)
