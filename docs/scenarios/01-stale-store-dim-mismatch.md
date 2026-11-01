# 01. Stale vector store: the embedding settings changed, the store did not

`stale-store-dim-mismatch`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

The store was built with 768-dimensional vectors. Later the embedding settings were changed (here: nomic-embed-text was asked for 256-dimensional vectors, which it supports) and nobody rebuilt the store. The inherited pipeline never compares the store with the vectors it is given, so the first question crashes inside faiss.

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
  File "<world>/pkg/local_rag/ask.py", line 49, in ask
    hits = retrieve(question, cfg, store, embedder)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/ask.py", line 34, in retrieve
    return store.search(vector, cfg.k)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/store.py", line 172, in search
    scores, ids = self._index.search(query, min(k, len(self.records)))
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<repo>/.venv/lib/python3.11/site-packages/faiss/class_wrappers.py", line 454, in replacement_search
    assert d == self.d
           ^^^^^^^^^^^
AssertionError
```

## Diagnosis

```text
$ python -m local_rag doctor
[ok]      Ollama 0.40.13 answers at http://127.0.0.1:11434
          2 model(s) installed: llama3.2:1b, nomic-embed-text:latest
[ok]      The embedding model 'nomic-embed-text' is installed
[ok]      The language model 'llama3.2:1b' is installed
[ok]      Store 'store': 24 chunks from 3 file(s)
          built with 'nomic-embed-text', 768 dimensions
[PROBLEM] Dimension mismatch: the store has 768-dimensional vectors, 'nomic-embed-text' returns 256
          The model behind that name changed, or the store came from another setup. Rebuild: python -m local_rag ingest --rebuild <pdfs>
[ok]      A full set of passages (about 720 tokens) fits into the 3776 tokens left of num_ctx=4096

1 problem(s).
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the store and the configured embedder agree on the vector size
PASS  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
PASS  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
PASS  a question about meridian-price-list.pdf p.1 finds that page among the top 4
PASS  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
PASS  a question about meridian-price-list.pdf p.3 finds that page among the top 4
PASS  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
```

Broken state: **fails**

```text
FAIL  the store and the configured embedder agree on the vector size
        the store holds 768-dimensional vectors, the embedder returns 256
FAIL  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
        assertion failed
FAIL  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
        assertion failed
FAIL  a question about meridian-price-list.pdf p.1 finds that page among the top 4
        assertion failed
FAIL  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
        assertion failed
FAIL  a question about meridian-price-list.pdf p.3 finds that page among the top 4
        assertion failed
FAIL  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
        assertion failed
```

Not part of the verdict, what the user would see in the broken state:

```text
$ python -m local_rag ask --debug How many days of paid annual leave does each employee get per year?
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
  File "<world>/pkg/local_rag/ask.py", line 49, in ask
    hits = retrieve(question, cfg, store, embedder)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/ask.py", line 34, in retrieve
    return store.search(vector, cfg.k)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<world>/pkg/local_rag/store.py", line 172, in search
    scores, ids = self._index.search(query, min(k, len(self.records)))
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<repo>/.venv/lib/python3.11/site-packages/faiss/class_wrappers.py", line 454, in replacement_search
    assert d == self.d
           ^^^^^^^^^^^
AssertionError
```

## Fixes that pass the check

### `rebuild_the_store`: passes

`ingest --rebuild` throws the old vectors away and embeds every chunk again with the current settings.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/store.py
    -if query.shape[1] != self.dim:
    +if False:
edit local_rag/store.py
    -if matrix.shape[1] != self.dim:
    +if False:
edit local_rag/ingest.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/ingest.py
    -store.check_compatible(embedder.model, len(vectors[0]))
    +pass
set LOCAL_RAG_EMBED_DIMENSIONS=256
run: python -m local_rag ingest --rebuild pdfs
```

```text
PASS  the store and the configured embedder agree on the vector size
PASS  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
PASS  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
PASS  a question about meridian-price-list.pdf p.1 finds that page among the top 4
PASS  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
PASS  a question about meridian-price-list.pdf p.3 finds that page among the top 4
PASS  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
```

Not part of the verdict, what the user sees now:

```text
$ python -m local_rag ask --debug How many days of paid annual leave does each employee get per year?
Answer: Every employee has 25 days of paid annual leave per calendar year.
Sources: harbor-pine-handbook.pdf p.2; harbor-pine-handbook.pdf p.1; harbor-pine-handbook.pdf p.3

-- debug --
retrieved 4 passage(s), k=4, min_score=0.6
  1. score 0.848  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
  2. score 0.748  harbor-pine-handbook.pdf p.2 chunk 1  [in prompt]  "5. Sick leave\nThe first 3 days of an illness do not need a doctor's note. From the fourth "
  3. score 0.722  harbor-pine-handbook.pdf p.1 chunk 2  [in prompt]  '2. Remote work\nStaff may work remotely up to three days per week. The two days in the stud'
  4. score 0.705  harbor-pine-handbook.pdf p.3 chunk 1  [in prompt]  '8. Travel\nWhen travelling for work, meals are reimbursed up to 45 EUR per day and hotels u'
prompt: about 642 tokens estimated (budget 3776, num_ctx 4096); server evaluated 492
```

### `revert_the_setting`: passes

Give the embedder back the size the store was built with. Nothing is re-embedded.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/store.py
    -if query.shape[1] != self.dim:
    +if False:
edit local_rag/store.py
    -if matrix.shape[1] != self.dim:
    +if False:
edit local_rag/ingest.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/ingest.py
    -store.check_compatible(embedder.model, len(vectors[0]))
    +pass
set LOCAL_RAG_EMBED_DIMENSIONS=256
unset LOCAL_RAG_EMBED_DIMENSIONS
```

```text
PASS  the store and the configured embedder agree on the vector size
PASS  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
PASS  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
PASS  a question about meridian-price-list.pdf p.1 finds that page among the top 4
PASS  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
PASS  a question about meridian-price-list.pdf p.3 finds that page among the top 4
PASS  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
```

## Wrong fixes the check refuses

### `reingest_without_rebuild`: refused

The PDFs did not change, so `ingest` skips them as 'unchanged': the store keeps the old vector size.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/store.py
    -if query.shape[1] != self.dim:
    +if False:
edit local_rag/store.py
    -if matrix.shape[1] != self.dim:
    +if False:
edit local_rag/ingest.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/ingest.py
    -store.check_compatible(embedder.model, len(vectors[0]))
    +pass
set LOCAL_RAG_EMBED_DIMENSIONS=256
run: python -m local_rag ingest pdfs
```

The check says:

```text
FAIL  the store and the configured embedder agree on the vector size
        the store holds 768-dimensional vectors, the embedder returns 256
FAIL  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
        assertion failed
FAIL  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
        assertion failed
FAIL  a question about meridian-price-list.pdf p.1 finds that page among the top 4
        assertion failed
FAIL  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
        assertion failed
FAIL  a question about meridian-price-list.pdf p.3 finds that page among the top 4
        assertion failed
FAIL  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
        assertion failed
```

### `delete_meta_json`: refused

Removes the record of which model built the store; the store then looks empty. The vectors are not fixed.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/store.py
    -if query.shape[1] != self.dim:
    +if False:
edit local_rag/store.py
    -if matrix.shape[1] != self.dim:
    +if False:
edit local_rag/ingest.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/ingest.py
    -store.check_compatible(embedder.model, len(vectors[0]))
    +pass
set LOCAL_RAG_EMBED_DIMENSIONS=256
delete store/meta.json
```

The check says:

```text
FAIL  the store and the configured embedder agree on the vector size
        the store holds None-dimensional vectors, the embedder returns 256
FAIL  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
        StoreEmpty: The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>
FAIL  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
        StoreEmpty: The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>
FAIL  a question about meridian-price-list.pdf p.1 finds that page among the top 4
        StoreEmpty: The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>
FAIL  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
        StoreEmpty: The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>
FAIL  a question about meridian-price-list.pdf p.3 finds that page among the top 4
        StoreEmpty: The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>
FAIL  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
        StoreEmpty: The store is empty. Ingest some PDFs first: python -m local_rag ingest <pdf or folder>
```

### `swallow_the_assertion`: refused

Turns the crash into 'no results'. Every question is now refused, which looks like a threshold problem.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/store.py
    -if query.shape[1] != self.dim:
    +if False:
edit local_rag/store.py
    -if matrix.shape[1] != self.dim:
    +if False:
edit local_rag/ingest.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/ingest.py
    -store.check_compatible(embedder.model, len(vectors[0]))
    +pass
set LOCAL_RAG_EMBED_DIMENSIONS=256
edit local_rag/store.py
    -scores, ids = self._index.search(query, min(k, len(self.records)))
    +try:
    +            scores, ids = self._index.search(query, min(k, len(self.records)))
    +        except AssertionError:
    +            return []
```

The check says:

```text
FAIL  the store and the configured embedder agree on the vector size
        the store holds 768-dimensional vectors, the embedder returns 256
FAIL  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
        got []
FAIL  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
        got []
FAIL  a question about meridian-price-list.pdf p.1 finds that page among the top 4
        got []
FAIL  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
        got []
FAIL  a question about meridian-price-list.pdf p.3 finds that page among the top 4
        got []
FAIL  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
        got []
```

### `lower_the_threshold`: refused

The threshold has nothing to do with it: the crash happens before any score exists.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/store.py
    -if query.shape[1] != self.dim:
    +if False:
edit local_rag/store.py
    -if matrix.shape[1] != self.dim:
    +if False:
edit local_rag/ingest.py
    -store.check_compatible(embedder.model)
    +pass
edit local_rag/ingest.py
    -store.check_compatible(embedder.model, len(vectors[0]))
    +pass
set LOCAL_RAG_EMBED_DIMENSIONS=256
set LOCAL_RAG_MIN_SCORE=0.0
```

The check says:

```text
FAIL  the store and the configured embedder agree on the vector size
        the store holds 768-dimensional vectors, the embedder returns 256
FAIL  a question about harbor-pine-handbook.pdf p.2 finds that page among the top 4
        assertion failed
FAIL  a question about aurora-kettle-manual.pdf p.1 finds that page among the top 4
        assertion failed
FAIL  a question about meridian-price-list.pdf p.1 finds that page among the top 4
        assertion failed
FAIL  a question about aurora-kettle-manual.pdf p.4 finds that page among the top 4
        assertion failed
FAIL  a question about meridian-price-list.pdf p.3 finds that page among the top 4
        assertion failed
FAIL  a question about harbor-pine-handbook.pdf p.4 finds that page among the top 4
        assertion failed
```

