"""num_ctx is smaller than the prompt: the model server silently cuts the prompt and the model answers from what is left."""
from __future__ import annotations

from framework import Edit, Env, Scenario, cli

from .common import MAIN_PDFS

QUESTION = "How many days of paid annual leave does each employee get per year?"
QUESTION2 = "What is the maximum fill level of the Aurora AK-200?"

NO_TRIM = Edit("local_rag/prompt.py", "if est <= budget:", "if True:")
NO_WARNING = Edit("local_rag/ask.py", "if reply.prompt_tokens:", "if False:")


def check(ctx):
    from local_rag.prompt import MAX_PLAUSIBLE_CHARS_PER_TOKEN

    for q in (QUESTION, QUESTION2):
        with ctx.step(f"the prompt for '{q[:40]}...' fits the window and the server read all of it"):
            ctx.ask(q)
            system, user, server_tokens = ctx.prompts[-1]
            chars = len(system) + len(user)
            room = ctx.cfg.num_ctx - ctx.cfg.num_predict
            assert chars / 3.0 <= room, f"the prompt is {chars} characters (about {chars / 3.0:.0f} tokens at 3 characters per token) for a window of {ctx.cfg.num_ctx} tokens with {ctx.cfg.num_predict} reserved for the answer"
            assert server_tokens, "the server did not report how many prompt tokens it read"
            assert chars / server_tokens <= MAX_PLAUSIBLE_CHARS_PER_TOKEN, f"the server read {server_tokens} tokens of a {chars} character prompt"


SCENARIO = Scenario(
    name="context-truncated-num-ctx",
    title="Context silently truncated by num_ctx",
    story=(
        "num_ctx was set to 1024 to save memory and k raised to 12. The twelve passages need about 1500 tokens. The inherited pipeline never compares the prompt with the window, "
        "the Ollama server does not complain when it is handed too much, and the model answers from whatever the server kept."
    ),
    pdfs=MAIN_PDFS,
    env={"ollama": {"LOCAL_RAG_NUM_CTX": "1024", "LOCAL_RAG_K": "12", "LOCAL_RAG_MIN_SCORE": "0.0"}},
    setup=[cli("ingest", "pdfs")],
    break_=[NO_TRIM, NO_WARNING],
    symptom=[cli("ask", "--debug", QUESTION)],
    diagnose=[cli("doctor")],
    check=check,
    fixes={
        "restore_the_size_check": [Edit("local_rag/prompt.py", "if True:", "if est <= budget:"), Edit("local_rag/ask.py", "if False:", "if reply.prompt_tokens:")],
        "raise_num_ctx": [Env("NUM_CTX", "8192")],
    },
    wrongs={
        "put_the_best_passage_last": [Edit("local_rag/prompt.py", "for n, h in enumerate(hits, start=1))", "for n, h in enumerate(reversed(hits), start=1))")],
        "raise_num_predict": [Env("NUM_PREDICT", "512")],
        "ten_passages_instead_of_twelve": [Env("K", "10")],
        "shorter_instructions": [Edit("local_rag/prompt.py", "Keep the answer short. Do not use any knowledge outside the passages.", "Be brief.")],
    },
    fix_notes={
        "restore_the_size_check": "The prompt is measured before it is sent (characters / 3 as a pessimistic token estimate) and the lowest ranked passages are dropped until it fits; what was dropped is reported. The reply's prompt token count is compared with the prompt's length as a second line of defence.",
        "raise_num_ctx": "Room for the whole prompt. Costs memory; the estimate in `doctor` tells whether k x chunk_size fits.",
    },
    wrong_notes={
        "put_the_best_passage_last": "This server keeps the END of an oversized prompt, so the right passage may survive, by luck: the prompt is still cut and the other passages are lost silently.",
        "raise_num_predict": "Reserves more room for the answer and so leaves less for the prompt.",
        "ten_passages_instead_of_twelve": "Still more than the window holds.",
        "shorter_instructions": "A few dozen tokens out of hundreds too many.",
    },
    live_only=True,
    observe=[cli("ask", QUESTION2)],
)
