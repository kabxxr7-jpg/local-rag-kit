"""Errors the pipeline raises on purpose. Every message is written for a person, not for a log parser."""


class RagError(Exception):
    """Base class. The message is plain words and says what to do next."""


class ConfigError(RagError):
    """A setting is missing, unknown or contradicts another one."""


class OllamaUnavailable(RagError):
    """The Ollama server does not answer at the configured address."""


class ModelNotPulled(RagError):
    """The Ollama server answers, but it does not have the model."""


class NoTextError(RagError):
    """A PDF has no extractable text (usually a scan). OCR is not part of this kit."""


class StoreMismatch(RagError):
    """The vector store was built with another embedding model than the one configured now."""


class StoreEmpty(RagError):
    """There is nothing to search yet."""
