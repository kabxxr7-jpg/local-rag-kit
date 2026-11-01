# 11. Ollama is up but the model is not pulled

`model-not-pulled`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

Ollama answers on its port, so 'is Ollama running?' says yes. The config asks for llama3.2:3b, which was never pulled. The inherited pipeline calls the server without translating its errors, so the user gets a 30-line traceback that ends in an HTTP 404.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask How many days of paid annual leave does each employee get per year?
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "<world>/pkg/local_rag/__main__.py", line 5, in <module>
    sys.exit(main())
             ^^^^^^
  File "<world>/pkg/local_rag/cli.py", line 110, in main
    return {"ingest": _cmd_ingest, "ask": _cmd_ask, "doctor": _cmd_doctor}[args.command](args, cfg)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/cli.py", line 59, in _cmd_ask
    result = ask(args.question, cfg)
             ^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/ask.py", line 74, in ask
    reply = llm.generate(prompt.system, prompt.user)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/llm.py", line 40, in generate
    msg = self._chat.invoke([("system", system), ("human", user)])
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_core/language_models/chat_models.py", line 529, in invoke
    self.generate_prompt(
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_core/language_models/chat_models.py", line 1920, in generate_prompt
    return self.generate(prompt_messages, stop=stop, callbacks=callbacks, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_core/language_models/chat_models.py", line 1727, in generate
    self._generate_with_cache(
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_core/language_models/chat_models.py", line 2065, in _generate_with_cache
    result = self._generate(
             ^^^^^^^^^^^^^^^
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_ollama/chat_models.py", line 1200, in _generate
    final_chunk = self._chat_stream_with_aggregation(
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_ollama/chat_models.py", line 1135, in _chat_stream_with_aggregation
    for chunk in self._iterate_over_stream(messages, stop, **kwargs):
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_ollama/chat_models.py", line 1224, in _iterate_over_stream
    for stream_resp in self._create_chat_stream(messages, stop, **kwargs):
  File "<repo>/.venv/lib/python3.11/site-packages/langchain_ollama/chat_models.py", line 1122, in _create_chat_stream
    yield from self._client.chat(**chat_params)
  File "<repo>/.venv/lib/python3.11/site-packages/ollama/_client.py", line 193, in inner
    raise ResponseError(e.response.text, e.response.status_code) from None
ollama._types.ResponseError: model 'llama3.2:3b' not found (status code: 404)
```

## Diagnosis

```text
$ python -m local_rag doctor
[ok]      Ollama 0.40.13 answers at http://127.0.0.1:11434
          2 model(s) installed: llama3.2:1b, nomic-embed-text:latest
[ok]      The embedding model 'nomic-embed-text' is installed
[PROBLEM] The language model 'llama3.2:3b' is not pulled
          Ollama is running but does not have it. Run: ollama pull llama3.2:3b   (installed now: llama3.2:1b, nomic-embed-text:latest). Or set the model name to one of those.
[ok]      Store 'store': 24 chunks from 3 file(s)
          built with 'nomic-embed-text', 768 dimensions
[ok]      The embedding model returns 768 dimensions, the same as the store
[ok]      A full set of passages (about 720 tokens) fits into the 3776 tokens left of num_ctx=4096

1 problem(s).
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the configured model answers a question
PASS  a model that is not pulled gives a plain message with the pull command
```

Broken state: **fails**

```text
FAIL  the configured model answers a question
        ResponseError: model 'llama3.2:3b' not found (status code: 404)
FAIL  a model that is not pulled gives a plain message with the pull command
        a raw ollama._types.ResponseError came out instead of a plain message: model 'no-such-model:1b' not found (status code: 404)
```

## Fixes that pass the check

### `use_an_installed_model_and_translate_errors`: passes

The model name is one that `ollama list` shows (`doctor` prints the installed ones), and every call to the server goes through `explain_ollama_errors`, which turns a 404 into 'run: ollama pull <model>'. No `ollama pull` was needed or run.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_LLM_MODEL=llama3.2:3b
edit local_rag/ollama_util.py
    +    yield
    +
    +
    +@contextmanager
    +def _explain_ollama_errors_unused(host: str, model: str):
set LOCAL_RAG_LLM_MODEL=llama3.2:1b
edit local_rag/ollama_util.py
    -    yield
    -
    -
    -@contextmanager
    -def _explain_ollama_errors_unused(host: str, model: str):
```

```text
PASS  the configured model answers a question
PASS  a model that is not pulled gives a plain message with the pull command
```

## Wrong fixes the check refuses

### `translate_errors_only`: refused

A friendly message, but the model is still not there: no answer.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_LLM_MODEL=llama3.2:3b
edit local_rag/ollama_util.py
    +    yield
    +
    +
    +@contextmanager
    +def _explain_ollama_errors_unused(host: str, model: str):
edit local_rag/ollama_util.py
    -    yield
    -
    -
    -@contextmanager
    -def _explain_ollama_errors_unused(host: str, model: str):
```

The check says:

```text
FAIL  the configured model answers a question
        ModelNotPulled: Ollama is running at http://127.0.0.1:11434 but does not have the model 'llama3.2:3b'. Pull it with: ollama pull llama3.2:3b   (or set the model name to one that `ollama list` shows).
PASS  a model that is not pulled gives a plain message with the pull command
```

### `change_the_model_only`: refused

Works today. The next typo in a model name is a traceback again.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_LLM_MODEL=llama3.2:3b
edit local_rag/ollama_util.py
    +    yield
    +
    +
    +@contextmanager
    +def _explain_ollama_errors_unused(host: str, model: str):
set LOCAL_RAG_LLM_MODEL=llama3.2:1b
```

The check says:

```text
PASS  the configured model answers a question
FAIL  a model that is not pulled gives a plain message with the pull command
        a raw ollama._types.ResponseError came out instead of a plain message: model 'no-such-model:1b' not found (status code: 404)
```

### `catch_everything`: refused

One line saying nothing: not which model, not what to do.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_LLM_MODEL=llama3.2:3b
edit local_rag/ollama_util.py
    +    yield
    +
    +
    +@contextmanager
    +def _explain_ollama_errors_unused(host: str, model: str):
edit local_rag/ollama_util.py
    -    yield
    +    try:
    +        yield
    +    except Exception:
    +        print("Something went wrong.")
    +        raise SystemExit(1)
```

The check says:

```text
Something went wrong.
```

### `point_at_another_host`: refused

Nothing listens there, so the error is a different one.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_LLM_MODEL=llama3.2:3b
edit local_rag/ollama_util.py
    +    yield
    +
    +
    +@contextmanager
    +def _explain_ollama_errors_unused(host: str, model: str):
set LOCAL_RAG_OLLAMA_HOST=http://127.0.0.1:4799
```

The check says:

```text
FAIL  the configured model answers a question
        ConnectionError: Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible. https://ollama.com/download
FAIL  a model that is not pulled gives a plain message with the pull command
        a raw builtins.ConnectionError came out instead of a plain message: Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible. https://ollama.com/download
```

