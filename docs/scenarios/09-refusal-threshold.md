# 09. Refusal threshold too high (and what happens when it is too low)

`refusal-threshold`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

min_score was set to 0.95 'to avoid hallucinations'. The best passage for a question that the documents answer scores 0.64 to 0.85 with nomic-embed-text, so nothing ever reaches the model. The obvious reaction, setting it to 0, brings the opposite failure: questions about nothing in the documents get answered.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask What is the length of the standard working week?
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.787 is below min_score 0.95; the model was not asked)
```

```text
$ python -m local_rag ask --debug What is the equipment budget for a laptop?
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.813 is below min_score 0.95; the model was not asked)

-- debug --
retrieved 4 passage(s), k=4, min_score=0.95
  1. score 0.813  harbor-pine-handbook.pdf p.3 chunk 2  [not used]  '9. Equipment and learning\nEach employee has an equipment budget of 1,200 EUR every three y'
  2. score 0.652  harbor-pine-handbook.pdf p.1 chunk 3  [not used]  '3. Devices and security\nEvery laptop uses full-disk encryption and must lock itself after '
  3. score 0.648  harbor-pine-handbook.pdf p.3 chunk 0  [not used]  'Harbor & Pine Studio - Staff handbook 2026\n\nExpenses, equipment and learning\n\n7. Expense c'
  4. score 0.561  meridian-price-list.pdf p.2 chunk 0  [not used]  'Meridian Cloud Storage - Price list 2026\n\nAdd-ons and terms\n\nAdd-on | Unit | Price per mon'
prompt: about None tokens estimated (budget 3776, num_ctx 4096); server evaluated None
```

## Diagnosis

```text
$ python -m local_rag ask --debug --json How many temperature presets does the kettle have?
{
  "question": "How many temperature presets does the kettle have?",
  "answer": "I could not find an answer to that in the ingested documents.",
  "refused": true,
  "reason": "below_threshold",
  "citations": [],
  "best_score": 0.8440483808517456,
  "est_tokens": null,
  "prompt_tokens": null,
  "dropped": [],
  "warnings": []
}
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  answerable, not refused by the threshold: What is the length of the standard working week?
PASS  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
PASS  answerable, not refused by the threshold: What is the equipment budget for a laptop?
PASS  answerable, not refused by the threshold: How many temperature presets does the kettle have?
PASS  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

Broken state: **fails**

```text
FAIL  answerable, not refused by the threshold: What is the length of the standard working week?
        refused: best score 0.787 < min_score 0.95
FAIL  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
        refused: best score 0.807 < min_score 0.95
FAIL  answerable, not refused by the threshold: What is the equipment budget for a laptop?
        refused: best score 0.813 < min_score 0.95
FAIL  answerable, not refused by the threshold: How many temperature presets does the kettle have?
        refused: best score 0.844 < min_score 0.95
FAIL  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
        refused: best score 0.803 < min_score 0.95
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

## Fixes that pass the check

### `calibrated_threshold`: passes

Chosen between the best scores of off-topic probes (at most 0.58) and of answerable ones (at least 0.64) with scripts/calibrate.py. With a different embedding model it has to be calibrated again.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_MIN_SCORE=0.95
set LOCAL_RAG_MIN_SCORE=0.60
```

```text
PASS  answerable, not refused by the threshold: What is the length of the standard working week?
PASS  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
PASS  answerable, not refused by the threshold: What is the equipment budget for a laptop?
PASS  answerable, not refused by the threshold: How many temperature presets does the kettle have?
PASS  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

### `calibrated_threshold_a_bit_higher`: passes

Anything inside the gap works; the gap is narrow (see docs/REAL-RUNS.md).

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_MIN_SCORE=0.95
set LOCAL_RAG_MIN_SCORE=0.62
```

```text
PASS  answerable, not refused by the threshold: What is the length of the standard working week?
PASS  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
PASS  answerable, not refused by the threshold: What is the equipment budget for a laptop?
PASS  answerable, not refused by the threshold: How many temperature presets does the kettle have?
PASS  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

## Wrong fixes the check refuses

### `threshold_zero`: refused

Nothing is refused any more: the model answers questions about Portugal and bread from a staff handbook.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_MIN_SCORE=0.95
set LOCAL_RAG_MIN_SCORE=0.0
```

The check says:

```text
PASS  answerable, not refused by the threshold: What is the length of the standard working week?
PASS  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
PASS  answerable, not refused by the threshold: What is the equipment budget for a laptop?
PASS  answerable, not refused by the threshold: How many temperature presets does the kettle have?
PASS  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
FAIL  off topic, refused by the threshold: Who painted the Mona Lisa?
        not refused: best score 0.463 >= min_score 0.0; the model answered 'Ines Carvalho.'
FAIL  off topic, refused by the threshold: What is the best programming language for beginners?
        not refused: best score 0.557 >= min_score 0.0; the model answered '[2] (harbor-pine-handbook.pdf, page 1)\nThe studio is open from 08:00 to 19:00 on weekdays. There are no meetings on Wednesdays, so that the day can be used for focused work.'
FAIL  off topic, refused by the threshold: How do I bake sourdough bread?
        not refused: best score 0.558 >= min_score 0.0; the model answered '[2] (aurora-kettle-manual.pdf, page 3)\nAurora AK-200 smart kettle - user manual\n\nCare and troubleshooting\n\nDescaling\nDescale the kettle every 4 weeks, or sooner when the ring light blinks amber. Fill it with one part white\nvinegar and two parts water, bring it to the boil, let it stand for 15 minutes, then rinse it well twice.'
FAIL  off topic, refused by the threshold: What is the weather in Lisbon today?
        not refused: best score 0.582 >= min_score 0.0; the model answered 'I could not find an answer to that in the ingested documents.'
```

### `threshold_a_bit_lower`: refused

0.90 is still above every score these documents give.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_MIN_SCORE=0.95
set LOCAL_RAG_MIN_SCORE=0.90
```

The check says:

```text
FAIL  answerable, not refused by the threshold: What is the length of the standard working week?
        refused: best score 0.787 < min_score 0.9
FAIL  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
        refused: best score 0.807 < min_score 0.9
FAIL  answerable, not refused by the threshold: What is the equipment budget for a laptop?
        refused: best score 0.813 < min_score 0.9
FAIL  answerable, not refused by the threshold: How many temperature presets does the kettle have?
        refused: best score 0.844 < min_score 0.9
FAIL  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
        refused: best score 0.803 < min_score 0.9
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

### `retrieve_more`: refused

k does not move the best score, and the threshold looks only at the best score.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_MIN_SCORE=0.95
set LOCAL_RAG_K=20
```

The check says:

```text
FAIL  answerable, not refused by the threshold: What is the length of the standard working week?
        refused: best score 0.787 < min_score 0.95
FAIL  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
        refused: best score 0.807 < min_score 0.95
FAIL  answerable, not refused by the threshold: What is the equipment budget for a laptop?
        refused: best score 0.813 < min_score 0.95
FAIL  answerable, not refused by the threshold: How many temperature presets does the kettle have?
        refused: best score 0.844 < min_score 0.95
FAIL  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
        refused: best score 0.803 < min_score 0.95
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

### `friendlier_refusal_text`: refused

The same refusals, politely worded.

What changes:

```text
run: python -m local_rag ingest pdfs
set LOCAL_RAG_MIN_SCORE=0.95
edit local_rag/prompt.py
    -REFUSAL_TEXT = "I could not find an answer to that in the ingested documents."
    +REFUSAL_TEXT = "Sorry, I am not sure about that one, please try rephrasing."
```

The check says:

```text
FAIL  answerable, not refused by the threshold: What is the length of the standard working week?
        refused: best score 0.787 < min_score 0.95
FAIL  answerable, not refused by the threshold: How many weeks of parental leave does the other parent get?
        refused: best score 0.807 < min_score 0.95
FAIL  answerable, not refused by the threshold: What is the equipment budget for a laptop?
        refused: best score 0.813 < min_score 0.95
FAIL  answerable, not refused by the threshold: How many temperature presets does the kettle have?
        refused: best score 0.844 < min_score 0.95
FAIL  answerable, not refused by the threshold: What is the minimum amount of water for the kettle?
        refused: best score 0.803 < min_score 0.95
PASS  off topic, refused by the threshold: Who painted the Mona Lisa?
PASS  off topic, refused by the threshold: What is the best programming language for beginners?
PASS  off topic, refused by the threshold: How do I bake sourdough bread?
PASS  off topic, refused by the threshold: What is the weather in Lisbon today?
```

