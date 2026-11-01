# 10. Context silently truncated by num_ctx

`context-truncated-num-ctx`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

num_ctx was set to 1024 to save memory and k raised to 12. The twelve passages need about 1500 tokens. The inherited pipeline never compares the prompt with the window, the Ollama server does not complain when it is handed too much, and the model answers from whatever the server kept.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask --debug How many days of paid annual leave does each employee get per year?
Answer: According to the text, each employee gets 36 hours of paid annual leave per year.
Sources: harbor-pine-handbook.pdf p.2; harbor-pine-handbook.pdf p.1; harbor-pine-handbook.pdf p.4; harbor-pine-handbook.pdf p.3; meridian-price-list.pdf p.3; meridian-price-list.pdf p.2

-- debug --
retrieved 12 passage(s), k=12, min_score=0.0
  1. score 0.843  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
  2. score 0.720  harbor-pine-handbook.pdf p.2 chunk 1  [in prompt]  "5. Sick leave\nThe first 3 days of an illness do not need a doctor's note. From the fourth "
  3. score 0.694  harbor-pine-handbook.pdf p.1 chunk 2  [in prompt]  '2. Remote work\nStaff may work remotely up to three days per week. The two days in the stud'
  4. score 0.661  harbor-pine-handbook.pdf p.4 chunk 1  [in prompt]  '11. Feedback and salary\nPerformance reviews take place twice a year, in May and in Novembe'
  5. score 0.657  harbor-pine-handbook.pdf p.4 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nOnboarding, feedback and conduct\n\n10. Onboardi'
  6. score 0.645  harbor-pine-handbook.pdf p.3 chunk 1  [in prompt]  '8. Travel\nWhen travelling for work, meals are reimbursed up to 45 EUR per day and hotels u'
  7. score 0.635  harbor-pine-handbook.pdf p.3 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nExpenses, equipment and learning\n\n7. Expense c'
  8. score 0.632  harbor-pine-handbook.pdf p.3 chunk 2  [in prompt]  '9. Equipment and learning\nEach employee has an equipment budget of 1,200 EUR every three y'
  9. score 0.616  harbor-pine-handbook.pdf p.1 chunk 1  [in prompt]  '1. Working hours\nThe standard working week is 36 hours. Core hours are 10:00 to 15:00 Cent'
  10. score 0.591  harbor-pine-handbook.pdf p.1 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nWorking hours and place of work\n\nHarbor & Pine'
  11. score 0.562  meridian-price-list.pdf p.3 chunk 1  [in prompt]  'Support hours\nStandard support answers e-mail from Monday to Friday, 09:00 to 17:00 UTC. T'
  12. score 0.542  meridian-price-list.pdf p.2 chunk 0  [in prompt]  'Meridian Cloud Storage - Price list 2026\n\nAdd-ons and terms\n\nAdd-on | Unit | Price per mon'
prompt: about 1652 tokens estimated (budget 704, num_ctx 1024); server evaluated 514
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
[ok]      The embedding model returns 768 dimensions, the same as the store
[warning] k=12 chunks of 500 characters can need about 2160 tokens, but num_ctx=1024 leaves 704
          A full set of passages will not always fit. With on_overflow='trim' the lowest ranked passages are dropped (and reported). A model server that is handed too much silently cuts the prompt, so raise num_ctx or lower k / chunk_size.

No problems found.
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
PASS  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
```

Broken state: **fails**

```text
FAIL  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
        the prompt is 4954 characters (about 1651 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
FAIL  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
        the prompt is 5500 characters (about 1833 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
```

Not part of the verdict, what the user would see in the broken state:

```text
$ python -m local_rag ask What is the maximum fill level of the Aurora AK-200?
Answer: The maximum fill level of the Aurora AK-200 is 1 TB (1 terabyte).
Sources: aurora-kettle-manual.pdf p.1; aurora-kettle-manual.pdf p.4; aurora-kettle-manual.pdf p.3; aurora-kettle-manual.pdf p.2; meridian-price-list.pdf p.3; meridian-price-list.pdf p.2; meridian-price-list.pdf p.1; harbor-pine-handbook.pdf p.3
```

## Fixes that pass the check

### `restore_the_size_check`: passes

The prompt is measured before it is sent (characters / 3 as a pessimistic token estimate) and the lowest ranked passages are dropped until it fits; what was dropped is reported. The reply's prompt token count is compared with the prompt's length as a second line of defence.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -if est <= budget:
    +if True:
edit local_rag/ask.py
    -if reply.prompt_tokens:
    +if False:
edit local_rag/prompt.py
    -if True:
    +if est <= budget:
edit local_rag/ask.py
    -if False:
    +if reply.prompt_tokens:
```

```text
PASS  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
PASS  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
```

Not part of the verdict, what the user sees now:

```text
$ python -m local_rag ask What is the maximum fill level of the Aurora AK-200?
Answer: 1. 1.7 litres
Sources: aurora-kettle-manual.pdf p.1; aurora-kettle-manual.pdf p.4; aurora-kettle-manual.pdf p.3
warning: Context trimmed: 9 of 12 retrieved passage(s) did not fit into num_ctx=1024 (estimated 562 tokens, budget 704) and were left out: aurora-kettle-manual.pdf p.3, aurora-kettle-manual.pdf p.2, aurora-kettle-manual.pdf p.1, meridian-price-list.pdf p.3, meridian-price-list.pdf p.2, meridian-price-list.pdf p.1, harbor-pine-handbook.pdf p.3, harbor-pine-handbook.pdf p.3, meridian-price-list.pdf p.3
```

### `raise_num_ctx`: passes

Room for the whole prompt. Costs memory; the estimate in `doctor` tells whether k x chunk_size fits.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -if est <= budget:
    +if True:
edit local_rag/ask.py
    -if reply.prompt_tokens:
    +if False:
set LOCAL_RAG_NUM_CTX=8192
```

```text
PASS  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
PASS  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
```

## Wrong fixes the check refuses

### `put_the_best_passage_last`: refused

This server keeps the END of an oversized prompt, so the right passage may survive, by luck: the prompt is still cut and the other passages are lost silently.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -if est <= budget:
    +if True:
edit local_rag/ask.py
    -if reply.prompt_tokens:
    +if False:
edit local_rag/prompt.py
    -for n, h in enumerate(hits, start=1))
    +for n, h in enumerate(reversed(hits), start=1))
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
        the prompt is 4954 characters (about 1651 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
FAIL  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
        the prompt is 5500 characters (about 1833 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
```

### `raise_num_predict`: refused

Reserves more room for the answer and so leaves less for the prompt.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -if est <= budget:
    +if True:
edit local_rag/ask.py
    -if reply.prompt_tokens:
    +if False:
set LOCAL_RAG_NUM_PREDICT=512
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
        the prompt is 4954 characters (about 1651 tokens at 3 characters per token) for a window of 1024 tokens with 512 reserved for the answer
FAIL  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
        the prompt is 5500 characters (about 1833 tokens at 3 characters per token) for a window of 1024 tokens with 512 reserved for the answer
```

### `ten_passages_instead_of_twelve`: refused

Still more than the window holds.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -if est <= budget:
    +if True:
edit local_rag/ask.py
    -if reply.prompt_tokens:
    +if False:
set LOCAL_RAG_K=10
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
        the prompt is 4259 characters (about 1420 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
FAIL  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
        the prompt is 4945 characters (about 1648 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
```

### `shorter_instructions`: refused

A few dozen tokens out of hundreds too many.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -if est <= budget:
    +if True:
edit local_rag/ask.py
    -if reply.prompt_tokens:
    +if False:
edit local_rag/prompt.py
    -Keep the answer short. Do not use any knowledge outside the passages.
    +Be brief.
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does ...' fits the window and the server read all of it
        the prompt is 4894 characters (about 1631 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
FAIL  the prompt for 'What is the maximum fill level of the Au...' fits the window and the server read all of it
        the prompt is 5440 characters (about 1813 tokens at 3 characters per token) for a window of 1024 tokens with 256 reserved for the answer
```

