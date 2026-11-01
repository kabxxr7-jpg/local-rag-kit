# 04. PDF text garbage: ligatures and line-end hyphens

`extraction-ligatures-hyphens`  |  run against: real Ollama (nomic-embed-text, llama3.2:1b)  |  result: **OK**

The PDF was typeset with ligature glyphs (fi, fl) and hyphenates words at the end of a line. pypdf hands them over faithfully: 'first' with the fi ligature U+FB01 is one character, 'stair-' and 'case' are two lines. The inherited cleaner only collapses whitespace, so the garbage is embedded, stored and quoted.

## Symptom (real output, broken state)

```text
$ python -m local_rag ask --debug --show-prompt When does the fire drill take place?
Answer: The fire drill takes place on the first Monday of every month at 11:15.
Sources: office-notes-ligatures.pdf p.1

-- debug --
retrieved 1 passage(s), k=4, min_score=0.6
  1. score 0.739  office-notes-ligatures.pdf p.1 chunk 0  [in prompt]  'Safety notes for the ofﬁce\n\nThe ﬁre drill takes place on the ﬁrst Monday of every month at'
prompt: about 257 tokens estimated (budget 3776, num_ctx 4096); server evaluated 216

-- prompt --
Passages:

[1] (office-notes-ligatures.pdf, page 1)
Safety notes for the ofﬁce

The ﬁre drill takes place on the ﬁrst Monday of every month at 11:15.
Staff must leave their ﬂoor by the nearest stair-
case and meet at the car park behind the building.
The ﬁrst-aid kit is kept in the kitchen cup-
board above the sink, and the defibrillator is at the recep-
tion desk. A ﬁre warden is named on every ﬂoor plan.

Question: When does the fire drill take place?
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
[ok]      A full set of passages (about 720 tokens) fits into the 3776 tokens left of num_ctx=4096
[ok]      office-notes-ligatures.pdf: text found on all 1 page(s)

No problems found.
```

## The check

The same check runs after every change. It decides; nothing else does.

Healthy state (control): **passes**

```text
PASS  the stored text has no ligature characters
PASS  words broken at the end of a line are joined (staircase, cupboard, reception)
PASS  the fire drill sentence can be found as written
PASS  the word 'office' in the heading is a word again
```

Broken state: **fails**

```text
FAIL  the stored text has no ligature characters
        stored text still contains U+FB01, U+FB02 (for example: 'the ofﬁce The ﬁre ')
FAIL  words broken at the end of a line are joined (staircase, cupboard, reception)
        not found in the stored text: ['staircase', 'cupboard', 'reception desk']
FAIL  the fire drill sentence can be found as written
        the sentence is not in the stored text
FAIL  the word 'office' in the heading is a word again
        assertion failed
```

Not part of the verdict, what the user would see in the broken state:

```text
$ python -m local_rag ask When does the fire drill take place?
Answer: The fire drill takes place on the first Monday of every month at 11:15.
Sources: office-notes-ligatures.pdf p.1
```

## Fixes that pass the check

### `restore_the_cleaner_and_rebuild`: passes

NFKC turns the ligature characters into letters, soft hyphens vanish, a hyphen before a line break followed by a lower case letter is joined. The rebuild matters: the PDF did not change, so a plain `ingest` skips it.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/clean.py
    -    text = unicodedata.normalize("NFKC", text)
    -    text = text.translate(_INVISIBLE)
    -    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    +    # inherited cleaner: whitespace only
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/clean.py
    -    # inherited cleaner: whitespace only
    +    text = unicodedata.normalize("NFKC", text)
    +    text = text.translate(_INVISIBLE)
    +    text = _HYPHEN_BREAK.sub(r"\1\2", text)
run: python -m local_rag ingest --rebuild pdfs
```

```text
PASS  the stored text has no ligature characters
PASS  words broken at the end of a line are joined (staircase, cupboard, reception)
PASS  the fire drill sentence can be found as written
PASS  the word 'office' in the heading is a word again
```

Not part of the verdict, what the user sees now:

```text
$ python -m local_rag ask When does the fire drill take place?
Answer: The fire drill takes place on the first Monday of every month at 11:15.
Sources: office-notes-ligatures.pdf p.1
```

## Wrong fixes the check refuses

### `normalise_but_do_not_dehyphenate`: refused

The ligatures are gone, 'stair- case' is still two words.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/clean.py
    -    text = unicodedata.normalize("NFKC", text)
    -    text = text.translate(_INVISIBLE)
    -    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    +    # inherited cleaner: whitespace only
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/clean.py
    -    # inherited cleaner: whitespace only
    +    text = unicodedata.normalize("NFKC", text)
run: python -m local_rag ingest --rebuild pdfs
```

The check says:

```text
PASS  the stored text has no ligature characters
FAIL  words broken at the end of a line are joined (staircase, cupboard, reception)
        not found in the stored text: ['staircase', 'cupboard', 'reception desk']
PASS  the fire drill sentence can be found as written
PASS  the word 'office' in the heading is a word again
```

### `dehyphenate_but_keep_ligatures`: refused

'staircase' is whole, the first/fire ligature is still one odd character, so 'first Monday' cannot be found.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/clean.py
    -    text = unicodedata.normalize("NFKC", text)
    -    text = text.translate(_INVISIBLE)
    -    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    +    # inherited cleaner: whitespace only
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/clean.py
    -    # inherited cleaner: whitespace only
    +    text = _HYPHEN_BREAK.sub(r"\1\2", text)
run: python -m local_rag ingest --rebuild pdfs
```

The check says:

```text
FAIL  the stored text has no ligature characters
        stored text still contains U+FB01, U+FB02 (for example: 'the ofﬁce The ﬁre ')
PASS  words broken at the end of a line are joined (staircase, cupboard, reception)
FAIL  the fire drill sentence can be found as written
        the sentence is not in the stored text
FAIL  the word 'office' in the heading is a word again
        assertion failed
```

### `strip_non_ascii`: refused

Deletes the ligature characters instead of converting them: 'office' becomes 'ofce', 'first' becomes 'rst'.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/clean.py
    -    text = unicodedata.normalize("NFKC", text)
    -    text = text.translate(_INVISIBLE)
    -    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    +    # inherited cleaner: whitespace only
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/clean.py
    -    # inherited cleaner: whitespace only
    +    text = re.sub(r"[^\x00-\x7f]", "", text)
run: python -m local_rag ingest --rebuild pdfs
```

The check says:

```text
PASS  the stored text has no ligature characters
FAIL  words broken at the end of a line are joined (staircase, cupboard, reception)
        not found in the stored text: ['staircase', 'cupboard', 'reception desk']
FAIL  the fire drill sentence can be found as written
        the sentence is not in the stored text
FAIL  the word 'office' in the heading is a word again
        assertion failed
```

### `fix_the_code_but_do_not_rebuild`: refused

The store still holds the old text: the file is unchanged, so nothing is re-read until `--rebuild`.

What changes:

```text
run: python -m local_rag ingest pdfs
edit local_rag/clean.py
    -    text = unicodedata.normalize("NFKC", text)
    -    text = text.translate(_INVISIBLE)
    -    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    +    # inherited cleaner: whitespace only
run: python -m local_rag ingest --rebuild pdfs
edit local_rag/clean.py
    -    # inherited cleaner: whitespace only
    +    text = unicodedata.normalize("NFKC", text)
    +    text = text.translate(_INVISIBLE)
    +    text = _HYPHEN_BREAK.sub(r"\1\2", text)
```

The check says:

```text
FAIL  the stored text has no ligature characters
        stored text still contains U+FB01, U+FB02 (for example: 'the ofﬁce The ﬁre ')
FAIL  words broken at the end of a line are joined (staircase, cupboard, reception)
        not found in the stored text: ['staircase', 'cupboard', 'reception desk']
FAIL  the fire drill sentence can be found as written
        the sentence is not in the stored text
FAIL  the word 'office' in the heading is a word again
        assertion failed
```

