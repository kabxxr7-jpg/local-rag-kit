"""Ollama is running, the configured model is not pulled: a raw traceback instead of an instruction."""
from __future__ import annotations

from framework import Edit, Env, Scenario, cli

from .common import MAIN_PDFS

QUESTION = "How many days of paid annual leave does each employee get per year?"

HEAD = "@contextmanager\ndef explain_ollama_errors(host: str, model: str):"
PASSTHROUGH = "@contextmanager\ndef explain_ollama_errors(host: str, model: str):\n    yield\n\n\n@contextmanager\ndef _explain_ollama_errors_unused(host: str, model: str):"
BREAK = Edit("local_rag/ollama_util.py", HEAD, PASSTHROUGH)
FIX = Edit("local_rag/ollama_util.py", PASSTHROUGH, HEAD)


def check(ctx):
    from local_rag.errors import ModelNotPulled

    with ctx.step("the configured model answers a question"):
        r = ctx.ask(QUESTION)
        assert not r.refused and r.answer.strip(), f"no answer: {r.answer!r}"
    with ctx.step("a model that is not pulled gives a plain message with the pull command"):
        try:
            ctx.ask(QUESTION, llm_model="no-such-model:1b")
        except ModelNotPulled as exc:
            assert "ollama pull no-such-model:1b" in str(exc), str(exc)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"a raw {type(exc).__module__}.{type(exc).__name__} came out instead of a plain message: {str(exc)[:160]}") from None
        else:
            raise AssertionError("asking with a model that does not exist did not fail")


SCENARIO = Scenario(
    name="model-not-pulled",
    title="Ollama is up but the model is not pulled",
    story=(
        "Ollama answers on its port, so 'is Ollama running?' says yes. The config asks for llama3.2:3b, which was never pulled. The inherited pipeline calls the server "
        "without translating its errors, so the user gets a 30-line traceback that ends in an HTTP 404."
    ),
    pdfs=MAIN_PDFS,
    setup=[cli("ingest", "pdfs")],
    break_=[Env("LLM_MODEL", "llama3.2:3b"), BREAK],
    symptom=[cli("ask", QUESTION)],
    diagnose=[cli("doctor")],
    check=check,
    fixes={"use_an_installed_model_and_translate_errors": [Env("LLM_MODEL", "llama3.2:1b"), FIX]},
    wrongs={
        "translate_errors_only": [FIX],
        "change_the_model_only": [Env("LLM_MODEL", "llama3.2:1b")],
        "catch_everything": [Edit("local_rag/ollama_util.py", "@contextmanager\ndef explain_ollama_errors(host: str, model: str):\n    yield", '@contextmanager\ndef explain_ollama_errors(host: str, model: str):\n    try:\n        yield\n    except Exception:\n        print("Something went wrong.")\n        raise SystemExit(1)')],
        "point_at_another_host": [Env("OLLAMA_HOST", "http://127.0.0.1:4799")],
    },
    fix_notes={"use_an_installed_model_and_translate_errors": "The model name is one that `ollama list` shows (`doctor` prints the installed ones), and every call to the server goes through `explain_ollama_errors`, which turns a 404 into 'run: ollama pull <model>'. No `ollama pull` was needed or run."},
    wrong_notes={
        "translate_errors_only": "A friendly message, but the model is still not there: no answer.",
        "change_the_model_only": "Works today. The next typo in a model name is a traceback again.",
        "catch_everything": "One line saying nothing: not which model, not what to do.",
        "point_at_another_host": "Nothing listens there, so the error is a different one.",
    },
    live_only=True,
)
