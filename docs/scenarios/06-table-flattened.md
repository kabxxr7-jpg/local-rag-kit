# 06. Table flattened into nonsense

`table-flattened`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

The price list's table was written into the PDF column by column. Read in that order, the text is 'Plan, Starter, Plus, Pro, Business, Storage, 100 GB...': every cell on its own line, the rows gone. Asked what the Pro plan costs, the model has to guess which '29 EUR' belongs to which name.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask --debug --show-prompt How much does the Pro plan cost per month?
Answer: 29 EUR
Sources: price-list-columnwise.pdf p.1

-- debug --
retrieved 4 passage(s), k=4, min_score=0.6
  1. score 0.656  price-list-columnwise.pdf p.1 chunk 0  [in prompt]  'Meridian Cloud Storage - Price list 2026\nPage 1 of 3\nPlans\nMeridian Cloud Storage offers f'
  2. score 0.599  price-list-columnwise.pdf p.2 chunk 0  [not used]  'Meridian Cloud Storage - Price list 2026\nPage 2 of 3\nAdd-ons and terms\nAdd-on\nExtra storag'
  3. score 0.538  price-list-columnwise.pdf p.3 chunk 1  [not used]  "customers receive a service credit of 10 percent of that month's fee.\nSupport hours\nStanda"
  4. score 0.502  price-list-columnwise.pdf p.3 chunk 0  [not used]  'Meridian Cloud Storage - Price list 2026\nPage 3 of 3\nData, uptime and support\nWhere your d'
prompt: about 297 tokens estimated (budget 3776, num_ctx 4096); server evaluated 247

-- prompt --
Passages:

[1] (price-list-columnwise.pdf, page 1)
Meridian Cloud Storage - Price list 2026
Page 1 of 3
Plans
Meridian Cloud Storage offers four plans. All plans include end-to-end encryption and a 14-day free trial.
Paying for a full year in advance gives a 15 percent discount on the monthly prices below.
Plan
Starter
Plus
Pro
Business
Storage
100 GB
1 TB
5 TB
20 TB
Users
1
3
10
50
Price per month
4 EUR
12 EUR
29 EUR
89 EUR
The Business plan includes a dedicated account manager. Prices are per month and exclude VAT.

Question: How much does the Pro plan cost per month?
Answer:
```

## Diagnosis

```text
$ python -m local_rag doctor pdfs
[ok]      Ollama 0.40.13 answers at http://127.0.0.1:11434
          2 model(s) installed: llama3.2:1b, nomic-embed-text:latest
[ok]      The embedding model 'nomic-embed-text' is installed
[ok]      The language model 'llama3.2:1b' is installed
[ok]      Store 'store': 4 chunks from 1 file(s)
          built with 'nomic-embed-text', 768 dimensions
[ok]      The embedding model returns 768 dimensions, the same as the store
[ok]      A full set of passages (about 720 tokens) fits into the 3776 tokens left of num_ctx=4096
[ok]      price-list-columnwise.pdf: text found on all 3 page(s)

No problems found.
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the table row is one line in the stored text: Plan | Storage | Users | Price per month
PASS  the table row is one line in the stored text: Pro | 5 TB | 10 | 29 EUR
PASS  the table row is one line in the stored text: Business | 20 TB | 50 | 89 EUR
```

Broken state: **fails**

```text
FAIL  the table row is one line in the stored text: Plan | Storage | Users | Price per month
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
FAIL  the table row is one line in the stored text: Pro | 5 TB | 10 | 29 EUR
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
FAIL  the table row is one line in the stored text: Business | 20 TB | 50 | 89 EUR
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
```

Not part of the verdict, what the user would see in the broken state:

```text
$ python -m local_rag ask How much does the Pro plan cost per month?
Answer: 29 EUR
Sources: price-list-columnwise.pdf p.1
```

```text
$ python -m local_rag ask How many users are included in the Business plan?
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.573 is below min_score 0.6; the model was not asked)
```

## Fixes that pass the check

### `layout_extraction`: passes

`extract_mode=layout` places every text fragment by its position on the page, so cells that share a baseline come back on one line; the cleaner writes the gaps between them as ' | '.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=layout
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=layout
run: python -m local_rag ingest pdfs
```

```text
PASS  the table row is one line in the stored text: Plan | Storage | Users | Price per month
PASS  the table row is one line in the stored text: Pro | 5 TB | 10 | 29 EUR
PASS  the table row is one line in the stored text: Business | 20 TB | 50 | 89 EUR
```

Not part of the verdict, what the user sees now:

```text
$ python -m local_rag ask How much does the Pro plan cost per month?
Answer: 29
Sources: price-list-columnwise.pdf p.1
```

```text
$ python -m local_rag ask How many users are included in the Business plan?
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.560 is below min_score 0.6; the model was not asked)
```

## Wrong fixes the check refuses

### `columns_mode`: refused

The page is split into a left and a right half and read half by half; the table is cut through the middle, between its third and fourth column.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=layout
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=columns
run: python -m local_rag ingest pdfs
```

The check says:

```text
FAIL  the table row is one line in the stored text: Plan | Storage | Users | Price per month
        not found. The page reads: ercent discount on the monthly prices below. Plan Storage Users Starter 100 GB 1 Plus 1 TB 3 Pro 5 TB 10 Business 20 TB 50 The Business plan includes a dedicated account manager. Prices are per month and exclude VAT. Pri
FAIL  the table row is one line in the stored text: Pro | 5 TB | 10 | 29 EUR
        not found. The page reads: ercent discount on the monthly prices below. Plan Storage Users Starter 100 GB 1 Plus 1 TB 3 Pro 5 TB 10 Business 20 TB 50 The Business plan includes a dedicated account manager. Prices are per month and exclude VAT. Pri
FAIL  the table row is one line in the stored text: Business | 20 TB | 50 | 89 EUR
        not found. The page reads: ercent discount on the monthly prices below. Plan Storage Users Starter 100 GB 1 Plus 1 TB 3 Pro 5 TB 10 Business 20 TB 50 The Business plan includes a dedicated account manager. Prices are per month and exclude VAT. Pri
```

### `bigger_chunks`: refused

A chunk holding the whole page holds all the cells, still one per line.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=layout
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=2500
run: python -m local_rag ingest pdfs
```

The check says:

```text
FAIL  the table row is one line in the stored text: Plan | Storage | Users | Price per month
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
FAIL  the table row is one line in the stored text: Pro | 5 TB | 10 | 29 EUR
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
FAIL  the table row is one line in the stored text: Business | 20 TB | 50 | 89 EUR
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
```

### `retrieve_more`: refused

More chunks of the same flattened text.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=layout
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_K=12
```

The check says:

```text
FAIL  the table row is one line in the stored text: Plan | Storage | Users | Price per month
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
FAIL  the table row is one line in the stored text: Pro | 5 TB | 10 | 29 EUR
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
FAIL  the table row is one line in the stored text: Business | 20 TB | 50 | 89 EUR
        not found. The page reads: gives a 15 percent discount on the monthly prices below. Plan Starter Plus Pro Business Storage 100 GB 1 TB 5 TB 20 TB Users 1 3 10 50 Price per month 4 EUR 12 EUR 29 EUR 89 EUR The Business plan includes a dedicated acc
```

