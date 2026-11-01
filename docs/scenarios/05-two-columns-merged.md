# 05. Two columns merged: text extraction reads across the page

`two-columns-merged`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

The shop policy page has two columns, written into the PDF line by line (left line 1, right line 1, left line 2...). Read in that order, the returns policy and the delivery policy are interleaved, so '30 days' sits next to 'ship free of' and a model has to untangle it.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask --debug --show-prompt How many days do customers have to return unused goods?
Answer: 5 working days.
Sources: shop-policies-two-columns.pdf p.1

-- debug --
retrieved 1 passage(s), k=4, min_score=0.6
  1. score 0.796  shop-policies-two-columns.pdf p.1 chunk 0  [in prompt]  'Corner Shop policies\nPage 1 of 1\nShop policies\nReturns policy\nDelivery policy\nCustomers ma'
prompt: about 348 tokens estimated (budget 3776, num_ctx 4096); server evaluated 264

-- prompt --
Passages:

[1] (shop-policies-two-columns.pdf, page 1)
Corner Shop policies
Page 1 of 1
Shop policies
Returns policy
Delivery policy
Customers may return unused goods
Orders above 50 EUR ship free of
within 30 days of delivery for a full
charge. Standard delivery takes 3 to
refund. The goods must be in their
5 working days. Express delivery
original packaging. Returns are free
takes 1 working day and costs 9 EUR.
of charge inside the country.
We do not deliver to post office
A refund is paid to the original
boxes. Parcels are left with a
payment method within 5 working
neighbour only if you allow it in
days after the parcel arrives.
your account settings.

Question: How many days do customers have to return unused goods?
Answer:
```

## Diagnosis

```text
$ python -m local_rag doctor pdfs
[ok]      Ollama 0.40.13 answers at http://127.0.0.1:11434
          2 model(s) installed: llama3.2:1b, nomic-embed-text:latest
[ok]      The embedding model 'nomic-embed-text' is installed
[ok]      The language model 'llama3.2:1b' is installed
[ok]      Store 'store': 1 chunks from 1 file(s)
          built with 'nomic-embed-text', 768 dimensions
[ok]      The embedding model returns 768 dimensions, the same as the store
[ok]      A full set of passages (about 1654 tokens) fits into the 3776 tokens left of num_ctx=4096
[ok]      shop-policies-two-columns.pdf: text found on all 1 page(s)

No problems found.
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the sentence reads as written in one chunk: Customers may return unused goods within 30 days...
PASS  the sentence reads as written in one chunk: Orders above 50 EUR ship free of charge. Standar...
```

Broken state: **fails**

```text
FAIL  the sentence reads as written in one chunk: Customers may return unused goods within 30 days...
        no stored chunk contains it. The stored page reads: Corner Shop policies Page 1 of 1 Shop policies Returns policy Delivery policy Customers may return unused goods Orders above 50 EUR ship free of within 30 days of delivery for a full charge. Standard delivery takes 3 to refund. The goods must be in their 5 wor
FAIL  the sentence reads as written in one chunk: Orders above 50 EUR ship free of charge. Standar...
        no stored chunk contains it. The stored page reads: Corner Shop policies Page 1 of 1 Shop policies Returns policy Delivery policy Customers may return unused goods Orders above 50 EUR ship free of within 30 days of delivery for a full charge. Standard delivery takes 3 to refund. The goods must be in their 5 wor
```

Not part of the verdict, what the user would see in the broken state:

```text
$ python -m local_rag ask How many days do customers have to return unused goods?
Answer: 5 working days.
Sources: shop-policies-two-columns.pdf p.1
```

```text
$ python -m local_rag ask How long does standard delivery take?
Answer: Standard delivery takes 3 to refund.
Sources: shop-policies-two-columns.pdf p.1
```

## Fixes that pass the check

### `read_the_page_column_by_column`: passes

`extract_mode=columns` sorts the text fragments by where they sit on the page: left column top to bottom, then the right one. `ingest` sees that the extraction setting changed and re-reads the file.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=columns
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=columns
run: python -m local_rag ingest pdfs
```

```text
PASS  the sentence reads as written in one chunk: Customers may return unused goods within 30 days...
PASS  the sentence reads as written in one chunk: Orders above 50 EUR ship free of charge. Standar...
```

Not part of the verdict, what the user sees now:

```text
$ python -m local_rag ask How many days do customers have to return unused goods?
Answer: 30 days.
Sources: shop-policies-two-columns.pdf p.1
```

```text
$ python -m local_rag ask How long does standard delivery take?
Answer: Standard delivery takes 3 to 5 working days.
Sources: shop-policies-two-columns.pdf p.1
```

## Wrong fixes the check refuses

### `layout_mode`: refused

Keeps the lines side by side ('left text | right text'), which is right for a table and wrong for two columns of prose.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=columns
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=layout
run: python -m local_rag ingest pdfs
```

The check says:

```text
FAIL  the sentence reads as written in one chunk: Customers may return unused goods within 30 days...
        no stored chunk contains it. The stored page reads: Corner Shop policies Shop policies Returns policy | Delivery policy Customers may return unused goods | Orders above 50 EUR ship free of within 30 days of delivery for a full | charge. Standard delivery takes 3 to refund. The goods must be in their | 5 working
FAIL  the sentence reads as written in one chunk: Orders above 50 EUR ship free of charge. Standar...
        no stored chunk contains it. The stored page reads: Corner Shop policies Shop policies Returns policy | Delivery policy Customers may return unused goods | Orders above 50 EUR ship free of within 30 days of delivery for a full | charge. Standard delivery takes 3 to refund. The goods must be in their | 5 working
```

### `bigger_chunks`: refused

The whole page in one chunk is still the interleaved page.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=columns
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_CHUNK_SIZE=3000
run: python -m local_rag ingest pdfs
```

The check says:

```text
FAIL  the sentence reads as written in one chunk: Customers may return unused goods within 30 days...
        no stored chunk contains it. The stored page reads: Corner Shop policies Page 1 of 1 Shop policies Returns policy Delivery policy Customers may return unused goods Orders above 50 EUR ship free of within 30 days of delivery for a full charge. Standard delivery takes 3 to refund. The goods must be in their 5 wor
FAIL  the sentence reads as written in one chunk: Orders above 50 EUR ship free of charge. Standar...
        no stored chunk contains it. The stored page reads: Corner Shop policies Page 1 of 1 Shop policies Returns policy Delivery policy Customers may return unused goods Orders above 50 EUR ship free of within 30 days of delivery for a full charge. Standard delivery takes 3 to refund. The goods must be in their 5 wor
```

### `retrieve_more`: refused

The garbled text is what gets retrieved, however many times.

What changes:

```text
set LOCAL_RAG_EXTRACT_MODE=columns
run: python -m local_rag ingest pdfs
set LOCAL_RAG_EXTRACT_MODE=plain
run: python -m local_rag ingest pdfs
set LOCAL_RAG_K=12
```

The check says:

```text
FAIL  the sentence reads as written in one chunk: Customers may return unused goods within 30 days...
        no stored chunk contains it. The stored page reads: Corner Shop policies Page 1 of 1 Shop policies Returns policy Delivery policy Customers may return unused goods Orders above 50 EUR ship free of within 30 days of delivery for a full charge. Standard delivery takes 3 to refund. The goods must be in their 5 wor
FAIL  the sentence reads as written in one chunk: Orders above 50 EUR ship free of charge. Standar...
        no stored chunk contains it. The stored page reads: Corner Shop policies Page 1 of 1 Shop policies Returns policy Delivery policy Customers may return unused goods Orders above 50 EUR ship free of within 30 days of delivery for a full charge. Standard delivery takes 3 to refund. The goods must be in their 5 wor
```

