from __future__ import annotations

import pytest

from local_rag.errors import ModelNotPulled, OllamaUnavailable
from local_rag.ollama_util import explain_ollama_errors


class ResponseError(Exception):
    """Same name and shape as ollama.ResponseError."""

    def __init__(self, error, status_code=-1):
        super().__init__(error)
        self.error, self.status_code = error, status_code


class ConnectError(Exception):
    pass


def test_a_refused_connection_says_ollama_is_not_running():
    with pytest.raises(OllamaUnavailable, match=r"does not answer at http://x:1.*ollama serve.*LOCAL_RAG_OLLAMA_HOST"):
        with explain_ollama_errors("http://x:1", "m"):
            raise ConnectionError("Failed to connect to Ollama.")


def test_a_404_names_the_model_and_the_pull_command():
    with pytest.raises(ModelNotPulled, match=r"does not have the model 'llama3.2:3b'.*ollama pull llama3.2:3b"):
        with explain_ollama_errors("http://x:1", "llama3.2:3b"):
            raise ResponseError("model 'llama3.2:3b' not found", 404)


def test_not_found_in_the_message_is_enough():
    with pytest.raises(ModelNotPulled):
        with explain_ollama_errors("h", "m"):
            raise ResponseError("model \"m\" not found, try pulling it first")


def test_a_timeout_is_reported_as_unavailable():
    with pytest.raises(OllamaUnavailable, match="did not answer in time"):
        with explain_ollama_errors("h", "m"):
            raise ConnectError("boom")


def test_other_errors_are_not_disguised():
    with pytest.raises(ResponseError, match="out of memory"):
        with explain_ollama_errors("h", "m"):
            raise ResponseError("out of memory", 500)
    with pytest.raises(ValueError):
        with explain_ollama_errors("h", "m"):
            raise ValueError("unrelated")


def test_no_error_no_effect():
    with explain_ollama_errors("h", "m"):
        value = 1 + 1
    assert value == 2
