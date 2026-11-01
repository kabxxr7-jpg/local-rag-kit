# 07. Page numbers wrong: citations point at the wrong page

`citations-wrong-page`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

The inherited ingest joins all pages of a file, splits the text once and estimates each chunk's page as 'position in the list x pages / chunks'. That is exact only if every page has the same amount of text. These pages do not, so later pages are cited as earlier ones and some chunks contain two pages.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask Who is the trust person for raising harassment concerns?
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.545 is below min_score 0.6; the model was not asked)
```

```text
$ python -m local_rag ask In which countries are the data centres located?
Answer: Ireland and Finland.
Sources: meridian-price-list.pdf p.2
```

## Diagnosis

```text
$ python -m local_rag ask --debug Who is the trust person for raising harassment concerns?
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.545 is below min_score 0.6; the model was not asked)

-- debug --
retrieved 4 passage(s), k=4, min_score=0.6
  1. score 0.545  harbor-pine-handbook.pdf p.4 chunk 10  [not used]  '11. Feedback and salary\nPerformance reviews take place twice a year, in May and in Novembe'
  2. score 0.494  meridian-price-list.pdf p.3 chunk 3  [not used]  'Uptime promise\nMeridian aims for 99.9 percent availability per month. If the monthly uptim'
  3. score 0.462  harbor-pine-handbook.pdf p.2 chunk 3  [not used]  '3. Devices and security\nEvery laptop uses full-disk encryption and must lock itself after '
  4. score 0.458  harbor-pine-handbook.pdf p.4 chunk 9  [not used]  'Harbor & Pine Studio - Staff handbook 2026\n\nOnboarding, feedback and conduct\n\n10. Onboardi'
prompt: about None tokens estimated (budget 3776, num_ctx 4096); server evaluated None
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  '25 days of paid annual leave' is stored as harbor-pine-handbook.pdf p.2
PASS  'maximum fill level is 1.7 litres' is stored as aurora-kettle-manual.pdf p.1
PASS  'Pro | 5 TB | 10 | 29 EUR' is stored as meridian-price-list.pdf p.1
PASS  'code AF-20' is stored as aurora-kettle-manual.pdf p.4
PASS  'Finland and Ireland' is stored as meridian-price-list.pdf p.3
PASS  'Ines Carvalho' is stored as harbor-pine-handbook.pdf p.4
PASS  the best passage for a question about harbor-pine-handbook.pdf p.2 cites page 2
PASS  the best passage for a question about aurora-kettle-manual.pdf p.1 cites page 1
PASS  the best passage for a question about meridian-price-list.pdf p.1 cites page 1
PASS  the best passage for a question about aurora-kettle-manual.pdf p.4 cites page 4
PASS  the best passage for a question about meridian-price-list.pdf p.3 cites page 3
PASS  the best passage for a question about harbor-pine-handbook.pdf p.4 cites page 4
```

Broken state: **fails**

```text
PASS  '25 days of paid annual leave' is stored as harbor-pine-handbook.pdf p.2
PASS  'maximum fill level is 1.7 litres' is stored as aurora-kettle-manual.pdf p.1
PASS  'Pro | 5 TB | 10 | 29 EUR' is stored as meridian-price-list.pdf p.1
FAIL  'code AF-20' is stored as aurora-kettle-manual.pdf p.4
        stored under [('aurora-kettle-manual.pdf', 3)]
FAIL  'Finland and Ireland' is stored as meridian-price-list.pdf p.3
        stored under [('meridian-price-list.pdf', 2)]
PASS  'Ines Carvalho' is stored as harbor-pine-handbook.pdf p.4
PASS  the best passage for a question about harbor-pine-handbook.pdf p.2 cites page 2
PASS  the best passage for a question about aurora-kettle-manual.pdf p.1 cites page 1
PASS  the best passage for a question about meridian-price-list.pdf p.1 cites page 1
FAIL  the best passage for a question about aurora-kettle-manual.pdf p.4 cites page 4
        best passage is cited as aurora-kettle-manual.pdf p.3
FAIL  the best passage for a question about meridian-price-list.pdf p.3 cites page 3
        best passage is cited as meridian-price-list.pdf p.2
PASS  the best passage for a question about harbor-pine-handbook.pdf p.4 cites page 4
```

## Fixes that pass the check

### `split_page_by_page_and_rebuild`: passes

Chunk each page on its own, so the page is known by construction, then rebuild: the PDFs did not change, so a plain `ingest` would skip them.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    +    by_source: dict[str, list[Page]] = {}
    +    for p in pages:
    +        by_source.setdefault(p.source, []).append(p)
    +    splitter = make_splitter(cfg)
    +    chunks: list[Chunk] = []
    +    for source, ps in by_source.items():
    +        pieces = [x.strip() for x in splitter.split_text("\n\n".join(p.text for p in ps)) if x.strip()]
    +        for i, piece in enumerate(pieces):
    +            page = ps[0].page + (i * len(ps)) // len(pieces)
    +            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    +    return chunks
    +
    +
    +def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/chunk.py
    -    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    -    by_source: dict[str, list[Page]] = {}
    -    for p in pages:
    -        by_source.setdefault(p.source, []).append(p)
    -    splitter = make_splitter(cfg)
    -    chunks: list[Chunk] = []
    -    for source, ps in by_source.items():
    -        pieces = [x.strip() for x in splitter.split_text("\n\n".join(p.text for p in ps)) if x.strip()]
    -        for i, piece in enumerate(pieces):
    -            page = ps[0].page + (i * len(ps)) // len(pieces)
    -            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    -    return chunks
    -
    -
    -def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:
run: python -m local_rag ingest --rebuild pdfs
```

```text
PASS  '25 days of paid annual leave' is stored as harbor-pine-handbook.pdf p.2
PASS  'maximum fill level is 1.7 litres' is stored as aurora-kettle-manual.pdf p.1
PASS  'Pro | 5 TB | 10 | 29 EUR' is stored as meridian-price-list.pdf p.1
PASS  'code AF-20' is stored as aurora-kettle-manual.pdf p.4
PASS  'Finland and Ireland' is stored as meridian-price-list.pdf p.3
PASS  'Ines Carvalho' is stored as harbor-pine-handbook.pdf p.4
PASS  the best passage for a question about harbor-pine-handbook.pdf p.2 cites page 2
PASS  the best passage for a question about aurora-kettle-manual.pdf p.1 cites page 1
PASS  the best passage for a question about meridian-price-list.pdf p.1 cites page 1
PASS  the best passage for a question about aurora-kettle-manual.pdf p.4 cites page 4
PASS  the best passage for a question about meridian-price-list.pdf p.3 cites page 3
PASS  the best passage for a question about harbor-pine-handbook.pdf p.4 cites page 4
```

## Wrong fixes the check refuses

### `add_one_to_every_page`: refused

Right for a few chunks by luck, wrong for the rest: the error is not a constant.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    +    by_source: dict[str, list[Page]] = {}
    +    for p in pages:
    +        by_source.setdefault(p.source, []).append(p)
    +    splitter = make_splitter(cfg)
    +    chunks: list[Chunk] = []
    +    for source, ps in by_source.items():
    +        pieces = [x.strip() for x in splitter.split_text("\n\n".join(p.text for p in ps)) if x.strip()]
    +        for i, piece in enumerate(pieces):
    +            page = ps[0].page + (i * len(ps)) // len(pieces)
    +            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    +    return chunks
    +
    +
    +def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/chunk.py
    -page = ps[0].page + (i * len(ps)) // len(pieces)
    +page = ps[0].page + (i * len(ps)) // len(pieces) + 1
run: python -m local_rag ingest --rebuild pdfs
```

The check says:

```text
FAIL  '25 days of paid annual leave' is stored as harbor-pine-handbook.pdf p.2
        stored under [('harbor-pine-handbook.pdf', 3)]
FAIL  'maximum fill level is 1.7 litres' is stored as aurora-kettle-manual.pdf p.1
        stored under [('aurora-kettle-manual.pdf', 2)]
FAIL  'Pro | 5 TB | 10 | 29 EUR' is stored as meridian-price-list.pdf p.1
        stored under [('meridian-price-list.pdf', 2)]
PASS  'code AF-20' is stored as aurora-kettle-manual.pdf p.4
PASS  'Finland and Ireland' is stored as meridian-price-list.pdf p.3
FAIL  'Ines Carvalho' is stored as harbor-pine-handbook.pdf p.4
        stored under [('harbor-pine-handbook.pdf', 5)]
FAIL  the best passage for a question about harbor-pine-handbook.pdf p.2 cites page 2
        best passage is cited as harbor-pine-handbook.pdf p.3
FAIL  the best passage for a question about aurora-kettle-manual.pdf p.1 cites page 1
        best passage is cited as aurora-kettle-manual.pdf p.2
FAIL  the best passage for a question about meridian-price-list.pdf p.1 cites page 1
        best passage is cited as meridian-price-list.pdf p.2
PASS  the best passage for a question about aurora-kettle-manual.pdf p.4 cites page 4
PASS  the best passage for a question about meridian-price-list.pdf p.3 cites page 3
FAIL  the best passage for a question about harbor-pine-handbook.pdf p.4 cites page 4
        best passage is cited as harbor-pine-handbook.pdf p.5
```

### `cite_the_last_page`: refused

Every chunk of a file is cited with its last page.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    +    by_source: dict[str, list[Page]] = {}
    +    for p in pages:
    +        by_source.setdefault(p.source, []).append(p)
    +    splitter = make_splitter(cfg)
    +    chunks: list[Chunk] = []
    +    for source, ps in by_source.items():
    +        pieces = [x.strip() for x in splitter.split_text("\n\n".join(p.text for p in ps)) if x.strip()]
    +        for i, piece in enumerate(pieces):
    +            page = ps[0].page + (i * len(ps)) // len(pieces)
    +            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    +    return chunks
    +
    +
    +def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/chunk.py
    -page = ps[0].page + (i * len(ps)) // len(pieces)
    +page = ps[-1].page
run: python -m local_rag ingest --rebuild pdfs
```

The check says:

```text
FAIL  '25 days of paid annual leave' is stored as harbor-pine-handbook.pdf p.2
        stored under [('harbor-pine-handbook.pdf', 4)]
FAIL  'maximum fill level is 1.7 litres' is stored as aurora-kettle-manual.pdf p.1
        stored under [('aurora-kettle-manual.pdf', 4)]
FAIL  'Pro | 5 TB | 10 | 29 EUR' is stored as meridian-price-list.pdf p.1
        stored under [('meridian-price-list.pdf', 3)]
PASS  'code AF-20' is stored as aurora-kettle-manual.pdf p.4
PASS  'Finland and Ireland' is stored as meridian-price-list.pdf p.3
PASS  'Ines Carvalho' is stored as harbor-pine-handbook.pdf p.4
FAIL  the best passage for a question about harbor-pine-handbook.pdf p.2 cites page 2
        best passage is cited as harbor-pine-handbook.pdf p.4
FAIL  the best passage for a question about aurora-kettle-manual.pdf p.1 cites page 1
        best passage is cited as aurora-kettle-manual.pdf p.4
FAIL  the best passage for a question about meridian-price-list.pdf p.1 cites page 1
        best passage is cited as meridian-price-list.pdf p.3
PASS  the best passage for a question about aurora-kettle-manual.pdf p.4 cites page 4
PASS  the best passage for a question about meridian-price-list.pdf p.3 cites page 3
PASS  the best passage for a question about harbor-pine-handbook.pdf p.4 cites page 4
```

### `fix_the_code_but_do_not_rebuild`: refused

The store still holds the wrongly numbered chunks: the files are unchanged, so nothing is re-read until `--rebuild`.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/chunk.py
    +    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    +    by_source: dict[str, list[Page]] = {}
    +    for p in pages:
    +        by_source.setdefault(p.source, []).append(p)
    +    splitter = make_splitter(cfg)
    +    chunks: list[Chunk] = []
    +    for source, ps in by_source.items():
    +        pieces = [x.strip() for x in splitter.split_text("\n\n".join(p.text for p in ps)) if x.strip()]
    +        for i, piece in enumerate(pieces):
    +            page = ps[0].page + (i * len(ps)) // len(pieces)
    +            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    +    return chunks
    +
    +
    +def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/chunk.py
    -    # inherited: split the whole document once, then work out each chunk's page from its position in the list
    -    by_source: dict[str, list[Page]] = {}
    -    for p in pages:
    -        by_source.setdefault(p.source, []).append(p)
    -    splitter = make_splitter(cfg)
    -    chunks: list[Chunk] = []
    -    for source, ps in by_source.items():
    -        pieces = [x.strip() for x in splitter.split_text("\n\n".join(p.text for p in ps)) if x.strip()]
    -        for i, piece in enumerate(pieces):
    -            page = ps[0].page + (i * len(ps)) // len(pieces)
    -            chunks.append(Chunk(chunk_id(source, page, i, piece), source, page, i, piece))
    -    return chunks
    -
    -
    -def _chunk_pages_one_page_at_a_time(pages: list[Page], cfg: Config) -> list[Chunk]:
```

The check says:

```text
PASS  '25 days of paid annual leave' is stored as harbor-pine-handbook.pdf p.2
PASS  'maximum fill level is 1.7 litres' is stored as aurora-kettle-manual.pdf p.1
PASS  'Pro | 5 TB | 10 | 29 EUR' is stored as meridian-price-list.pdf p.1
FAIL  'code AF-20' is stored as aurora-kettle-manual.pdf p.4
        stored under [('aurora-kettle-manual.pdf', 3)]
FAIL  'Finland and Ireland' is stored as meridian-price-list.pdf p.3
        stored under [('meridian-price-list.pdf', 2)]
PASS  'Ines Carvalho' is stored as harbor-pine-handbook.pdf p.4
PASS  the best passage for a question about harbor-pine-handbook.pdf p.2 cites page 2
PASS  the best passage for a question about aurora-kettle-manual.pdf p.1 cites page 1
PASS  the best passage for a question about meridian-price-list.pdf p.1 cites page 1
FAIL  the best passage for a question about aurora-kettle-manual.pdf p.4 cites page 4
        best passage is cited as aurora-kettle-manual.pdf p.3
FAIL  the best passage for a question about meridian-price-list.pdf p.3 cites page 3
        best passage is cited as meridian-price-list.pdf p.2
PASS  the best passage for a question about harbor-pine-handbook.pdf p.4 cites page 4
```

