# 02. Duplicated chunks after re-ingest

`duplicate-chunks`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

Every run of `ingest` adds the same chunks again. After a few runs the top-k is filled with copies of one passage, the prompt repeats itself and the store grows without bound. The inherited code gives each chunk a random id and never replaces what an earlier run stored for the same file.

## Symptom (real output, broken state)

```text
$ python -m local_rag ingest pdfs
ingested  aurora-kettle-manual.pdf: 8 chunks
ingested  harbor-pine-handbook.pdf: 11 chunks
ingested  meridian-price-list.pdf: 5 chunks
store: 120 chunks in total (removed 0 old chunk(s) of re-ingested files) in 'store'
```

```text
$ python -m local_rag ask --debug How many days of paid annual leave does each employee get per year?
Answer: 25
Sources: harbor-pine-handbook.pdf p.2

-- debug --
retrieved 4 passage(s), k=4, min_score=0.6
  1. score 0.843  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
  2. score 0.843  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
  3. score 0.843  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
  4. score 0.843  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
prompt: about 798 tokens estimated (budget 3776, num_ctx 4096); server evaluated 594
```

## Diagnosis

```text
$ python -m local_rag doctor
[ok]      Ollama 0.40.13 answers at http://127.0.0.1:11434
          2 model(s) installed: llama3.2:1b, nomic-embed-text:latest
[ok]      The embedding model 'nomic-embed-text' is installed
[ok]      The language model 'llama3.2:1b' is installed
[ok]      Store 'store': 120 chunks from 3 file(s)
          built with 'nomic-embed-text', 768 dimensions
[ok]      The embedding model returns 768 dimensions, the same as the store
[ok]      A full set of passages (about 720 tokens) fits into the 3776 tokens left of num_ctx=4096

No problems found.
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  ingesting the same PDFs again leaves the number of chunks unchanged
PASS  no passage is stored twice
PASS  the passages retrieved for a question are all different
```

Broken state: **fails**

```text
FAIL  ingesting the same PDFs again leaves the number of chunks unchanged
        72 chunks before, 96 after a repeat ingest
FAIL  no passage is stored twice
        24 passages are stored more than once (96 chunks for 24 different passages)
FAIL  the passages retrieved for a question are all different
        4 passages retrieved, 1 different
```

## Fixes that pass the check

### `content_ids_replace_and_rebuild`: passes

The id is a hash of file, page, position and text, a file that did not change is skipped, a file that did is replaced, and one rebuild removes the copies already stored.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    import uuid
    +
    +    return uuid.uuid4().hex[:24]
    +
    +
    +def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
    +if False:
edit local_rag/ingest.py
    -report.removed_chunks += store.remove_source(pdf.name)
    +pass
run: python -m local_rag ingest pdfs
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    -    import uuid
    -
    -    return uuid.uuid4().hex[:24]
    -
    -
    -def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -if False:
    +if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
edit local_rag/ingest.py
    -pass
    +report.removed_chunks += store.remove_source(pdf.name)
run: python -m local_rag ingest --rebuild pdfs
```

```text
PASS  ingesting the same PDFs again leaves the number of chunks unchanged
PASS  no passage is stored twice
PASS  the passages retrieved for a question are all different
```

### `content_ids_and_replace_only`: passes

Same, without the 'unchanged' shortcut: every run re-embeds but replaces what the file had before, so there are still no copies.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    import uuid
    +
    +    return uuid.uuid4().hex[:24]
    +
    +
    +def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
    +if False:
edit local_rag/ingest.py
    -report.removed_chunks += store.remove_source(pdf.name)
    +pass
run: python -m local_rag ingest pdfs
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    -    import uuid
    -
    -    return uuid.uuid4().hex[:24]
    -
    -
    -def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -pass
    +report.removed_chunks += store.remove_source(pdf.name)
run: python -m local_rag ingest --rebuild pdfs
```

```text
PASS  ingesting the same PDFs again leaves the number of chunks unchanged
PASS  no passage is stored twice
PASS  the passages retrieved for a question are all different
```

## Wrong fixes the check refuses

### `rebuild_only`: refused

Cleans the store once. The next ingest duplicates again because the code is unchanged.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    import uuid
    +
    +    return uuid.uuid4().hex[:24]
    +
    +
    +def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
    +if False:
edit local_rag/ingest.py
    -report.removed_chunks += store.remove_source(pdf.name)
    +pass
run: python -m local_rag ingest pdfs
run: python -m local_rag ingest pdfs
run: python -m local_rag ingest --rebuild pdfs
```

The check says:

```text
FAIL  ingesting the same PDFs again leaves the number of chunks unchanged
        24 chunks before, 48 after a repeat ingest
FAIL  no passage is stored twice
        24 passages are stored more than once (48 chunks for 24 different passages)
FAIL  the passages retrieved for a question are all different
        4 passages retrieved, 2 different
```

### `dedupe_when_answering`: refused

Hides the copies from the top-k only. The store, its size and the next ingest are as bad as before.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    import uuid
    +
    +    return uuid.uuid4().hex[:24]
    +
    +
    +def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
    +if False:
edit local_rag/ingest.py
    -report.removed_chunks += store.remove_source(pdf.name)
    +pass
run: python -m local_rag ingest pdfs
run: python -m local_rag ingest pdfs
edit local_rag/ask.py
    -return store.search(vector, cfg.k)
    +seen, out = set(), []
    +    for h in store.search(vector, cfg.k * 4):
    +        if h.text not in seen:
    +            seen.add(h.text)
    +            out.append(h)
    +    return out[: cfg.k]
```

The check says:

```text
FAIL  ingesting the same PDFs again leaves the number of chunks unchanged
        72 chunks before, 96 after a repeat ingest
FAIL  no passage is stored twice
        24 passages are stored more than once (96 chunks for 24 different passages)
PASS  the passages retrieved for a question are all different
```

### `raise_k`: refused

More passages retrieved means more copies retrieved.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    import uuid
    +
    +    return uuid.uuid4().hex[:24]
    +
    +
    +def _chunk_id_from_content(source: str, page: int, index: int, text: str) -> str:
edit local_rag/ingest.py
    -if known and known.get("sha256") == digest and known.get("signature") == _signature(cfg):
    +if False:
edit local_rag/ingest.py
    -report.removed_chunks += store.remove_source(pdf.name)
    +pass
run: python -m local_rag ingest pdfs
run: python -m local_rag ingest pdfs
set LOCAL_RAG_K=12
```

The check says:

```text
FAIL  ingesting the same PDFs again leaves the number of chunks unchanged
        72 chunks before, 96 after a repeat ingest
FAIL  no passage is stored twice
        24 passages are stored more than once (96 chunks for 24 different passages)
FAIL  the passages retrieved for a question are all different
        12 passages retrieved, 3 different
```

