"""Settings. Defaults, then an optional TOML file, then environment variables (LOCAL_RAG_<NAME>).

Nothing here is a personal path: the store lives in ``.rag-store`` next to wherever you run the command unless you say otherwise.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

from .errors import ConfigError

ENV_PREFIX = "LOCAL_RAG_"
CONFIG_FILE_ENV = "LOCAL_RAG_CONFIG"


@dataclass(frozen=True)
class Config:
    # models and server
    ollama_host: str = "http://127.0.0.1:11434"
    embed_model: str = "nomic-embed-text"
    llm_model: str = "llama3.2:1b"
    embedder: str = "ollama"  # "ollama" or "fake" (the fake one is for offline tests)
    llm: str = "ollama"  # "ollama" or "fake"
    request_timeout: float = 120.0
    # store
    store_dir: str = ".rag-store"
    # reading PDFs
    extract_mode: str = "layout"  # "plain" (pypdf default), "layout" (keeps table rows on one line) or "columns" (two column pages)
    chunk_size: int = 500  # characters, not tokens
    chunk_overlap: int = 80  # characters
    # asking
    k: int = 4
    min_score: float = 0.60  # cosine similarity of the best chunk; below it the answer is the refusal text
    num_ctx: int = 4096  # tokens the model server is asked to keep in memory
    num_predict: int = 256  # tokens reserved for the answer
    chars_per_token: float = 3.0  # deliberately pessimistic estimate used for the prompt size check
    on_overflow: str = "trim"  # "trim" (drop the lowest ranked passages, visibly) or "refuse"
    # embedding model specifics (nomic-embed-text wants these prefixes; set both to "" for models that do not)
    embed_doc_prefix: str = "search_document: "
    embed_query_prefix: str = "search_query: "
    embed_dimensions: int = 0  # 0 = the model's own size; a positive number asks Ollama for shorter vectors (models that support it)
    fake_dim: int = 256


_FIELD_TYPES = {f.name: f.type for f in fields(Config)}
_CHOICES = {
    "embedder": ("ollama", "fake"),
    "llm": ("ollama", "fake"),
    "extract_mode": ("plain", "layout", "columns"),
    "on_overflow": ("trim", "refuse"),
}


def _coerce(name: str, raw: Any, origin: str) -> Any:
    kind = _FIELD_TYPES[name]
    try:
        if kind in ("int", int):
            if isinstance(raw, bool):
                raise ValueError("a yes/no value is not a number")
            return int(raw)
        if kind in ("float", float):
            if isinstance(raw, bool):
                raise ValueError("a yes/no value is not a number")
            return float(raw)
        return str(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Setting '{name}' (from {origin}) must be {kind}, got {raw!r}: {exc}") from exc


def validate(cfg: Config) -> Config:
    for name, allowed in _CHOICES.items():
        value = getattr(cfg, name)
        if value not in allowed:
            raise ConfigError(f"Setting '{name}' is {value!r}; allowed values are: {', '.join(allowed)}.")
    if cfg.chunk_size < 50:
        raise ConfigError(f"chunk_size is {cfg.chunk_size}; it counts characters, so anything under 50 cannot hold a sentence.")
    if not 0 <= cfg.chunk_overlap < cfg.chunk_size:
        raise ConfigError(f"chunk_overlap ({cfg.chunk_overlap}) must be at least 0 and smaller than chunk_size ({cfg.chunk_size}).")
    if cfg.k < 1:
        raise ConfigError(f"k is {cfg.k}; it must be at least 1.")
    if not -1.0 <= cfg.min_score <= 1.0:
        raise ConfigError(f"min_score is {cfg.min_score}; it is a cosine similarity, so it must be between -1 and 1.")
    if cfg.num_ctx < 256:
        raise ConfigError(f"num_ctx is {cfg.num_ctx}; that is too small to hold even one passage.")
    if not 1 <= cfg.num_predict < cfg.num_ctx:
        raise ConfigError(f"num_predict ({cfg.num_predict}) must be at least 1 and smaller than num_ctx ({cfg.num_ctx}).")
    if cfg.chars_per_token <= 0:
        raise ConfigError(f"chars_per_token is {cfg.chars_per_token}; it must be greater than 0.")
    if cfg.embed_dimensions < 0:
        raise ConfigError(f"embed_dimensions is {cfg.embed_dimensions}; use 0 for the model's own size or a positive number.")
    if cfg.fake_dim < 8:
        raise ConfigError(f"fake_dim is {cfg.fake_dim}; it must be at least 8.")
    return cfg


def load_config(env: Mapping[str, str] | None = None, file: str | None = None, overrides: Mapping[str, Any] | None = None) -> Config:
    """Build the settings. ``overrides`` (command line flags) win over the environment, which wins over the file."""
    env = os.environ if env is None else env
    values: dict[str, Any] = {}
    path = file or env.get(CONFIG_FILE_ENV)
    if path:
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except FileNotFoundError as exc:
            raise ConfigError(f"Config file '{path}' does not exist.") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Config file '{path}' is not valid TOML: {exc}") from exc
        unknown = sorted(set(data) - set(_FIELD_TYPES))
        if unknown:
            raise ConfigError(f"Config file '{path}' has unknown setting(s): {', '.join(unknown)}. Known: {', '.join(sorted(_FIELD_TYPES))}.")
        for name, raw in data.items():
            values[name] = _coerce(name, raw, f"file {path}")
    for name in _FIELD_TYPES:
        raw = env.get(ENV_PREFIX + name.upper())
        if raw is not None:
            values[name] = _coerce(name, raw, f"environment variable {ENV_PREFIX + name.upper()}")
    for name, raw in (overrides or {}).items():
        if raw is None:
            continue
        if name not in _FIELD_TYPES:
            raise ConfigError(f"Unknown setting '{name}'.")
        values[name] = _coerce(name, raw, "the command line")
    return validate(replace(Config(), **values))
