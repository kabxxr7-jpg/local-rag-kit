"""Turns the raw failures of the Ollama client into errors a person can act on."""
from __future__ import annotations

from contextlib import contextmanager

from .errors import ModelNotPulled, OllamaUnavailable


@contextmanager
def explain_ollama_errors(host: str, model: str):
    """Wrap every call to the Ollama server in this. Without it a missing model is a 30 line traceback."""
    try:
        yield
    except ConnectionError as exc:  # the Ollama client turns a refused connection into the built-in ConnectionError
        raise OllamaUnavailable(
            f"Ollama does not answer at {host} ({type(exc).__name__}). Start it (open the Ollama app or run `ollama serve`) "
            f"or fix ollama_host / LOCAL_RAG_OLLAMA_HOST."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - classified below, anything unknown is re-raised untouched
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        message = str(getattr(exc, "error", "") or exc)
        if name == "ResponseError" and (status == 404 or "not found" in message.lower()):
            raise ModelNotPulled(
                f"Ollama is running at {host} but does not have the model '{model}'. Pull it with: ollama pull {model}   "
                f"(or set the model name to one that `ollama list` shows)."
            ) from exc
        if name in ("ConnectError", "ConnectTimeout", "ReadTimeout", "TimeoutException", "TimeoutError"):
            raise OllamaUnavailable(f"Ollama at {host} did not answer in time ({name}). Is the server running and not overloaded?") from exc
        raise
