# 08. Retrieval is right, the prompt never contains the page

`prompt-assembly-drops-hit`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

k was raised to 6 for recall. The inherited prompt builder keeps 'the last three passages' to save room, but the list is best first, so with four or more passages it throws the best ones away. Retrieval and citations still look right; the model is answering from the worst passages.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask --debug --show-prompt How many days of paid annual leave does each employee get per year?
Answer: 11. 26
Sources: harbor-pine-handbook.pdf p.2; harbor-pine-handbook.pdf p.1; harbor-pine-handbook.pdf p.4; harbor-pine-handbook.pdf p.3

-- debug --
retrieved 6 passage(s), k=6, min_score=0.5
  1. score 0.843  harbor-pine-handbook.pdf p.2 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nLeave and absence\n\n4. Annual leave\nEvery emplo'
  2. score 0.720  harbor-pine-handbook.pdf p.2 chunk 1  [in prompt]  "5. Sick leave\nThe first 3 days of an illness do not need a doctor's note. From the fourth "
  3. score 0.694  harbor-pine-handbook.pdf p.1 chunk 2  [in prompt]  '2. Remote work\nStaff may work remotely up to three days per week. The two days in the stud'
  4. score 0.661  harbor-pine-handbook.pdf p.4 chunk 1  [in prompt]  '11. Feedback and salary\nPerformance reviews take place twice a year, in May and in Novembe'
  5. score 0.657  harbor-pine-handbook.pdf p.4 chunk 0  [in prompt]  'Harbor & Pine Studio - Staff handbook 2026\n\nOnboarding, feedback and conduct\n\n10. Onboardi'
  6. score 0.645  harbor-pine-handbook.pdf p.3 chunk 1  [in prompt]  '8. Travel\nWhen travelling for work, meals are reimbursed up to 45 EUR per day and hotels u'
prompt: about 512 tokens estimated (budget 3776, num_ctx 4096); server evaluated 393

-- prompt --
Passages:

[1] (harbor-pine-handbook.pdf, page 4)
11. Feedback and salary
Performance reviews take place twice a year, in May and in November. Salaries are reviewed once a
year, in January, together with the budget for the new year.

12. Conduct
Gifts from clients worth more than 50 EUR must be declared to the managing partner. Concerns about
harassment can be raised in confidence with the trust person, Ines Carvalho, or with the managing
partner. Client files are kept for 7 years and then deleted.

Page 4 of 4

[2] (harbor-pine-handbook.pdf, page 4)
Harbor & Pine Studio - Staff handbook 2026

Onboarding, feedback and conduct

10. Onboarding and probation
Every new employee is paired with a buddy for the first 6 weeks. The probation period lasts 3 months;
during probation either side may end the contract with 1 week of notice. After probation the notice
period is 2 months.

[3] (harbor-pine-handbook.pdf, page 3)
8. Travel
When travelling for work, meals are reimbursed up to 45 EUR per day and hotels up to 140 EUR per
night. Train travel is preferred for journeys under 6 hours; flights in economy class are reimbursed in full.

Question: How many days of paid annual leave does each employee get per year?
Answer:
```

## Diagnosis

```text
$ python -m local_rag ask --debug What is the maximum fill level of the Aurora AK-200?
Answer: Page 1 of 4
Sources: aurora-kettle-manual.pdf p.1; aurora-kettle-manual.pdf p.4; aurora-kettle-manual.pdf p.3; aurora-kettle-manual.pdf p.2

-- debug --
retrieved 6 passage(s), k=6, min_score=0.5
  1. score 0.802  aurora-kettle-manual.pdf p.1 chunk 0  [in prompt]  'Aurora AK-200 smart kettle - user manual\n\nSafety and first use\n\nAurora AK-200 smart kettle'
  2. score 0.716  aurora-kettle-manual.pdf p.4 chunk 0  [in prompt]  'Aurora AK-200 smart kettle - user manual\n\nSpecifications and disposal\n\nSpecifications\n- He'
  3. score 0.676  aurora-kettle-manual.pdf p.3 chunk 1  [in prompt]  'Reset and warranty\nTo reset the kettle, unplug it from the mains for 30 seconds and plug i'
  4. score 0.652  aurora-kettle-manual.pdf p.3 chunk 0  [in prompt]  'Aurora AK-200 smart kettle - user manual\n\nCare and troubleshooting\n\nDescaling\nDescale the '
  5. score 0.622  aurora-kettle-manual.pdf p.2 chunk 0  [in prompt]  'Aurora AK-200 smart kettle - user manual\n\nOperation\n\nTemperature presets\nPress the preset '
  6. score 0.521  aurora-kettle-manual.pdf p.1 chunk 1  [in prompt]  '- Place the kettle on a flat, dry surface. Never immerse the power base in water.\n\n- The k'
prompt: about 581 tokens estimated (budget 3776, num_ctx 4096); server evaluated 450
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the prompt for 'How many days of paid annual leave does each e...' contains the best passage and everything that is cited
PASS  the prompt for 'What is the maximum fill level of the Aurora A...' contains the best passage and everything that is cited
PASS  the prompt for 'How much does the priority support add-on cost...' contains the best passage and everything that is cited
```

Broken state: **fails**

```text
FAIL  the prompt for 'How many days of paid annual leave does each e...' contains the best passage and everything that is cited
        the best passage (harbor-pine-handbook.pdf p.2, score 0.84) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'What is the maximum fill level of the Aurora A...' contains the best passage and everything that is cited
        the best passage (aurora-kettle-manual.pdf p.1, score 0.80) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'How much does the priority support add-on cost...' contains the best passage and everything that is cited
        the best passage (meridian-price-list.pdf p.2, score 0.72) is not in the prompt; the prompt holds 3 passages
```

## Fixes that pass the check

### `keep_every_passage`: passes

Render the passages that were kept, in rank order. No re-ingest: this is code that runs at question time.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -for n, h in enumerate(hits, start=1))
    +for n, h in enumerate(hits[-3:], start=1))
edit local_rag/prompt.py
    -for n, h in enumerate(hits[-3:], start=1))
    +for n, h in enumerate(hits, start=1))
```

```text
PASS  the prompt for 'How many days of paid annual leave does each e...' contains the best passage and everything that is cited
PASS  the prompt for 'What is the maximum fill level of the Aurora A...' contains the best passage and everything that is cited
PASS  the prompt for 'How much does the priority support add-on cost...' contains the best passage and everything that is cited
```

## Wrong fixes the check refuses

### `raise_k`: refused

More passages retrieved; the builder still keeps only the last three of them.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -for n, h in enumerate(hits, start=1))
    +for n, h in enumerate(hits[-3:], start=1))
set LOCAL_RAG_K=10
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does each e...' contains the best passage and everything that is cited
        the best passage (harbor-pine-handbook.pdf p.2, score 0.84) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'What is the maximum fill level of the Aurora A...' contains the best passage and everything that is cited
        the best passage (aurora-kettle-manual.pdf p.1, score 0.80) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'How much does the priority support add-on cost...' contains the best passage and everything that is cited
        the best passage (meridian-price-list.pdf p.2, score 0.72) is not in the prompt; the prompt holds 3 passages
```

### `lower_the_threshold`: refused

More passages pass the filter; still only the last three are rendered.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -for n, h in enumerate(hits, start=1))
    +for n, h in enumerate(hits[-3:], start=1))
set LOCAL_RAG_MIN_SCORE=0.0
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does each e...' contains the best passage and everything that is cited
        the best passage (harbor-pine-handbook.pdf p.2, score 0.84) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'What is the maximum fill level of the Aurora A...' contains the best passage and everything that is cited
        the best passage (aurora-kettle-manual.pdf p.1, score 0.80) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'How much does the priority support add-on cost...' contains the best passage and everything that is cited
        the best passage (meridian-price-list.pdf p.2, score 0.72) is not in the prompt; the prompt holds 3 passages
```

### `rewrite_the_instructions`: refused

Better wording for text the model never gets to see.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/prompt.py
    -for n, h in enumerate(hits, start=1))
    +for n, h in enumerate(hits[-3:], start=1))
edit local_rag/prompt.py
    -Keep the answer short. Do not use any knowledge outside the passages.
    +Read the passages very carefully and give a short, precise answer.
```

The check says:

```text
FAIL  the prompt for 'How many days of paid annual leave does each e...' contains the best passage and everything that is cited
        the best passage (harbor-pine-handbook.pdf p.2, score 0.84) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'What is the maximum fill level of the Aurora A...' contains the best passage and everything that is cited
        the best passage (aurora-kettle-manual.pdf p.1, score 0.80) is not in the prompt; the prompt holds 3 passages
FAIL  the prompt for 'How much does the priority support add-on cost...' contains the best passage and everything that is cited
        the best passage (meridian-price-list.pdf p.2, score 0.72) is not in the prompt; the prompt holds 3 passages
```

