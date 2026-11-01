# 03. Chunks too small: chunk_size counted in characters, meant as tokens

`chunk-size-unit-mistake`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

Someone set chunk_size=100 and chunk_overlap=0 believing the unit was tokens. The splitter counts characters, so every chunk is about 100 characters, sentences are cut in the middle, and the piece that holds the number is not the piece that holds the subject.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask --debug How many unused leave days can be carried over to the next year?
Answer: 5
Sources: harbor-pine-handbook.pdf p.2

-- debug --
retrieved 4 passage(s), k=4, min_score=0.6
  1. score 0.849  harbor-pine-handbook.pdf p.2 chunk 4  [in prompt]  'to 5 unused days may be carried over and must be taken by 31 March of the following year; '
  2. score 0.761  harbor-pine-handbook.pdf p.2 chunk 2  [in prompt]  'Every employee has 25 days of paid annual leave per calendar year, in addition to public h'
  3. score 0.740  harbor-pine-handbook.pdf p.2 chunk 11  [in prompt]  'required. Sick leave is paid in full for up to 20 days per calendar year.'
  4. score 0.727  harbor-pine-handbook.pdf p.2 chunk 6  [in prompt]  "A leave request of more than 5 consecutive working days needs at least 4 weeks' notice. Sh"
prompt: about 309 tokens estimated (budget 3776, num_ctx 4096); server evaluated 255
```

## Diagnosis

```text
$ python -m local_rag doctor
[ok]      Ollama 0.40.13 answers at http://127.0.0.1:11434
          2 model(s) installed: llama3.2:1b, nomic-embed-text:latest
[ok]      The embedding model 'nomic-embed-text' is installed
[ok]      The language model 'llama3.2:1b' is installed
[ok]      Store 'store': 158 chunks from 3 file(s)
          built with 'nomic-embed-text', 768 dimensions
[ok]      The embedding model returns 768 dimensions, the same as the store
[ok]      A full set of passages (about 187 tokens) fits into the 3776 tokens left of num_ctx=4096

No problems found.
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
PASS  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
PASS  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
PASS  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
```

Broken state: **fails**

```text
FAIL  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [73, 95, 97, 98]) holds the whole sentence
FAIL  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [90, 91, 98, 99]) holds the whole sentence
FAIL  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [76, 81, 81, 91]) holds the whole sentence
FAIL  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [50, 64, 95, 97]) holds the whole sentence
```

## Fixes that pass the check

### `restore_the_defaults_and_ingest`: passes

Characters, about 500 per chunk. `ingest` notices that the chunk settings changed and re-chunks the files that were stored with the old ones, so no `--rebuild` is needed.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=100
set LOCAL_RAG_CHUNK_OVERLAP=0
run: python -m local_rag ingest pdfs
unset LOCAL_RAG_CHUNK_SIZE
unset LOCAL_RAG_CHUNK_OVERLAP
run: python -m local_rag ingest pdfs
```

```text
PASS  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
PASS  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
PASS  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
PASS  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
```

### `set_600_100_and_ingest`: passes

Any size that holds a few sentences works; the check only asks that the answering sentence is whole.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=100
set LOCAL_RAG_CHUNK_OVERLAP=0
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=600
set LOCAL_RAG_CHUNK_OVERLAP=100
run: python -m local_rag ingest pdfs
```

```text
PASS  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
PASS  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
PASS  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
PASS  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
```

## Wrong fixes the check refuses

### `raise_k`: refused

Twenty fragments are still fragments, and the prompt gets longer.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=100
set LOCAL_RAG_CHUNK_OVERLAP=0
run: python -m local_rag ingest pdfs
set LOCAL_RAG_K=20
```

The check says:

```text
FAIL  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
        none of the 20 retrieved passages (lengths [15, 29, 38, 49, 54, 55, 61, 65, 73, 83, 90, 91, 92, 95, 96, 97, 98, 99, 99, 99]) holds the whole sentence
FAIL  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
        none of the 20 retrieved passages (lengths [13, 53, 56, 60, 65, 73, 76, 90, 91, 92, 93, 96, 96, 97, 98, 98, 98, 99, 99, 99]) holds the whole sentence
FAIL  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
        none of the 20 retrieved passages (lengths [9, 11, 22, 38, 42, 51, 62, 66, 69, 76, 78, 81, 81, 90, 91, 92, 93, 98, 99, 99]) holds the whole sentence
FAIL  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
        none of the 20 retrieved passages (lengths [11, 49, 50, 51, 51, 53, 62, 64, 66, 68, 69, 76, 90, 92, 92, 93, 95, 97, 98, 99]) holds the whole sentence
```

### `change_the_setting_but_do_not_ingest`: refused

The store still holds the 100-character chunks; settings only apply to files that are ingested again.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=100
set LOCAL_RAG_CHUNK_OVERLAP=0
run: python -m local_rag ingest pdfs
unset LOCAL_RAG_CHUNK_SIZE
unset LOCAL_RAG_CHUNK_OVERLAP
```

The check says:

```text
FAIL  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [73, 95, 97, 98]) holds the whole sentence
FAIL  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [90, 91, 98, 99]) holds the whole sentence
FAIL  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [76, 81, 81, 91]) holds the whole sentence
FAIL  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [50, 64, 95, 97]) holds the whole sentence
```

### `add_overlap_only`: refused

An overlap of 50 on 100-character chunks repeats half of each fragment; the sentences are still cut.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=100
set LOCAL_RAG_CHUNK_OVERLAP=0
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_OVERLAP=50
run: python -m local_rag ingest pdfs
```

The check says:

```text
FAIL  the sentence answering 'How many unused leave days can be carried over to the next year?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [73, 95, 97, 98]) holds the whole sentence
FAIL  the sentence answering 'How much is the learning budget per person per year?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [90, 91, 98, 99]) holds the whole sentence
FAIL  the sentence answering 'How do you descale the kettle?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [76, 81, 81, 91]) holds the whole sentence
FAIL  the sentence answering 'Who can I talk to in confidence about harassment?' reaches the model in one piece
        none of the 4 retrieved passages (lengths [50, 64, 95, 97]) holds the whole sentence
```

