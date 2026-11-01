"""The language model. The real one is ChatOllama (langchain-ollama); the fake one lives in testing.py."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import Config
from .ollama_util import explain_ollama_errors


@dataclass
class Reply:
    text: str
    prompt_tokens: int | None = None  # what the server says it evaluated (Ollama: prompt_eval_count)
    output_tokens: int | None = None


class LLM(Protocol):
    def generate(self, system: str, user: str) -> Reply: ...


class OllamaLLM:
    def __init__(self, cfg: Config):
        from langchain_ollama import ChatOllama

        self._host = cfg.ollama_host
        self._model = cfg.llm_model
        self._chat = ChatOllama(
            model=cfg.llm_model,
            base_url=cfg.ollama_host,
            num_ctx=cfg.num_ctx,
            num_predict=cfg.num_predict,
            temperature=0.0,
            seed=0,
            client_kwargs={"timeout": cfg.request_timeout},
        )

    def generate(self, system: str, user: str) -> Reply:
        with explain_ollama_errors(self._host, self._model):
            msg = self._chat.invoke([("system", system), ("human", user)])
        meta = getattr(msg, "response_metadata", {}) or {}
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        return Reply(content.strip(), meta.get("prompt_eval_count"), meta.get("eval_count"))


def get_llm(cfg: Config) -> LLM:
    if cfg.llm == "fake":
        from .testing import FakeLLM

        return FakeLLM()
    return OllamaLLM(cfg)
