# local-rag-kit

Ask questions about PDFs using only local models (Ollama: `llama3.2:1b` for answers, `nomic-embed-text` for search). Nothing leaves the machine.
It is a small, readable RAG pipeline (pypdf, LangChain text splitter and Ollama clients, a faiss index) built to be debugged: every stage can be
inspected, and the usual reasons a RAG pipeline "works but answers badly" each have a check, a message in plain words, or a test.

**Status:** working and measured on one machine only (Apple M1, 8 GB, macOS, Python 3.11, Ollama 0.40.13) on 2026-11-01. 214 offline tests pass and 13 live tests pass against the real Ollama. On a 39-question eval about fictional documents the right page is retrieved for 29 of 30 answerable questions but the 1B model answers only 20 of 30 correctly (details and every wrong answer in `docs/EVAL.md`). The mutation check caught 68 of 72 planted bugs on its first run and 72 of 72 after four tests were added for the survivors. The GitHub Actions file in `.github/workflows/ci.yml` has never run. Read "What this does not prove" before relying on any of it.

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.2:1b && ollama pull nomic-embed-text       # once; needs the Ollama app or `ollama serve` running

python -m local_rag doctor samples/pdfs                       # is everything in place? (plain-word report)
python -m local_rag ingest samples/pdfs/harbor-pine-handbook.pdf samples/pdfs/aurora-kettle-manual.pdf samples/pdfs/meridian-price-list.pdf
python -m local_rag ask "How many days of annual leave do employees get?"
python -m local_rag ask --debug "How many days of annual leave do employees get?"    # scores, what went into the prompt, what was dropped
```

`samples/pdfs` also holds `scanned-notice.pdf`, a picture of text with no text layer. Ingesting the whole folder reports it as failed
("This kit does not do OCR ...", exit code 1) and still ingests the others.

What a run looks like (real output from the live suite, `docs/REAL-RUNS.md` has the rest, including wrong answers):

```text
$ python -m local_rag ask "How many days of annual leave do employees get?"
Answer: Employees get 25 days of paid annual leave per calendar year.
Sources: harbor-pine-handbook.pdf p.2; harbor-pine-handbook.pdf p.1; harbor-pine-handbook.pdf p.4

$ python -m local_rag ask "Who painted the Mona Lisa?"
Answer: I could not find an answer to that in the ingested documents.
(best match score 0.463 is below min_score 0.6; the model was not asked)
```

The sources are the pages of the passages that went into the prompt; the model does not say which of them it used.

## What is in the pipeline

| Stage | What it does | Where |
|---|---|---|
| Extract | pypdf, one page at a time, three modes: `plain`, `layout` (table rows stay on one line, the default) and `columns` (two column pages, left column first). A PDF with no text at all is refused with a plain message; single empty pages are reported and skipped. | `local_rag/extract.py` |
| Clean | Unicode NFKC (so `\ufb01` becomes `fi`), invisible characters removed, words broken at a line-end hyphen joined, a wide gap inside a line turned into ` \| `. | `local_rag/clean.py` |
| Chunk | LangChain `RecursiveCharacterTextSplitter`, sizes in **characters**, applied page by page so a chunk always knows its page. Chunk ids are a hash of file, page, position and text. | `local_rag/chunk.py` |
| Embed | `nomic-embed-text` through `langchain-ollama`, with the `search_document:` / `search_query:` prefixes that model needs. | `local_rag/embed.py` |
| Store | faiss inner-product index over normalised vectors (cosine), plus `records.json` and `meta.json`. Remembers the embedding model name and the vector size and refuses a mismatch. Re-ingesting an unchanged file is a no-op; a changed file replaces its old chunks. | `local_rag/store.py`, `local_rag/ingest.py` |
| Ask | Retrieve `k` passages. If the best score is below `min_score` the answer is a fixed refusal sentence and **the model is not asked**. Otherwise only the passages above `min_score` go into the prompt, the prompt size is checked against `num_ctx`, `llama3.2:1b` answers, and the citations are the file and page of the passages that were really in the prompt. | `local_rag/ask.py`, `local_rag/prompt.py` |
| Doctor | Looks at the usual reasons nothing works and says what to do: Ollama not running, model not pulled, store built with another embedding model, PDFs without text, a prompt budget that cannot fit `k` passages. | `local_rag/doctor.py` |

## Settings

Order of precedence: defaults, then a TOML file (`--config file.toml` or `LOCAL_RAG_CONFIG`), then environment variables `LOCAL_RAG_<NAME>`, then command line flags (`--store`, `-k`). Unknown names and out-of-range values are rejected in plain words.

| Setting | Default | Meaning |
|---|---|---|
| `ollama_host` | `http://127.0.0.1:11434` | where Ollama listens |
| `embed_model` / `llm_model` | `nomic-embed-text` / `llama3.2:1b` | the two local models |
| `embed_doc_prefix` / `embed_query_prefix` | `search_document: ` / `search_query: ` | prefixes nomic-embed-text needs; set both to empty for other models |
| `embed_dimensions` | `0` | 0 = the model's own size (768); a positive number asks for shorter vectors |
| `store_dir` | `.rag-store` | where the index lives (relative to where you run the command) |
| `extract_mode` | `layout` | `plain`, `layout` (table rows stay on one line) or `columns` (two column pages) |
| `chunk_size` / `chunk_overlap` | `500` / `80` | **characters**, not tokens |
| `k` | `4` | passages retrieved per question |
| `min_score` | `0.60` | cosine score of the best passage below which the model is not asked; picked from `scripts/calibrate.py` on probe questions that are not in the eval |
| `num_ctx` / `num_predict` | `4096` / `256` | context window asked of Ollama / tokens reserved for the answer |
| `chars_per_token` | `3.0` | pessimistic estimate for the prompt size check |
| `on_overflow` | `trim` | when the passages do not fit: `trim` drops the lowest ranked ones (reported) or `refuse` does not ask the model |
| `request_timeout` | `120` | seconds before an Ollama call is given up |
| `embedder` / `llm` | `ollama` | `fake` selects the offline test doubles (`local_rag/testing.py`) |

## The inherited-pipeline lab

The task this kit was built around: "debug and complete an existing RAG pipeline". The lab does it 11 times, on purpose. Each scenario starts from a healthy copy of the pipeline, breaks it in one of the usual ways, and then:

1. shows the **symptom** with the real commands and real output,
2. shows the **diagnosis** (which command or measurement points at the cause),
3. has a **check** that fails on the broken state and passes on the healthy one,
4. applies **every real fix** (some scenarios have two) and requires the check to pass after each,
5. applies **the tempting wrong fixes** (3 or 4 per scenario) and requires the check to refuse each one.

Run against the real Ollama (`python scenarios/run.py --backend ollama --record`, 2026-11-01): **11 of 11 scenarios behave as designed, 16 of 16 fixes pass, 38 of 38 wrong fixes are refused.** Nine scenarios also run offline with the fake embedder and fake model (as tests, marker `scenarios`); two need the real server (context truncation, model not pulled).

| # | Scenario | Real fixes | Wrong fixes the check refuses |
|---|---|---|---|
| 01 | Stale vector store: embedding settings changed, the store did not | rebuild the store; revert the setting | re-ingest without `--rebuild`; delete `meta.json`; swallow the assertion; lower the threshold |
| 02 | Duplicated chunks after re-ingest | content-based ids, replace on re-ingest, rebuild; the same without the rebuild | rebuild only (ids still random); dedupe when answering; raise `k` |
| 03 | Chunks too small (`chunk_size` read as tokens, applied as characters) | restore the defaults and ingest; set 600/100 and ingest | raise `k`; change the setting but do not ingest; add overlap only |
| 04 | PDF text garbage: ligatures and line-end hyphens | restore the cleaner and rebuild | normalise but do not dehyphenate; dehyphenate but keep ligatures; strip non-ASCII; fix the code but do not rebuild |
| 05 | Two columns merged | read the page column by column | layout mode; bigger chunks; retrieve more |
| 06 | Table flattened into nonsense | layout extraction | columns mode; bigger chunks; retrieve more |
| 07 | Citations point at the wrong page | split page by page and rebuild | add one to every page; cite the last page; fix the code but do not rebuild |
| 08 | Retrieval is right, the prompt never contains the page | keep every passage | raise `k`; lower the threshold; rewrite the instructions |
| 09 | Refusal threshold too high (and what happens when it is too low) | calibrated threshold; a bit higher | threshold 0; a bit lower; retrieve more; friendlier refusal text |
| 10 | Context silently truncated by `num_ctx` (real server only) | restore the size check; raise `num_ctx` | put the best passage last; raise `num_predict`; ten passages instead of twelve; shorter instructions |
| 11 | Ollama is up but the model is not pulled (real server only) | use an installed model and translate the errors | translate errors only; change the model only; catch everything; point at another host |

Each scenario's story, real output, fixes and wrong fixes are in `docs/SCENARIOS.md` and `docs/scenarios/`. The scenarios are staged: the breaks were made by hand and the checks written knowing the fixes (see "What this does not prove").

## Numbers

| | |
|---|---|
| Offline tests (`python -m pytest`) | 214 (core 179, of which the mutation check runs these; tooling 26; lab 9) |
| Live tests (`python -m pytest -m live`, needs Ollama) | 13, all passed on 2026-11-01 |
| Eval, retrieval: right file and page in top 4 / is the best passage | 29 of 30 / 27 of 30 |
| Eval, answer contains an accepted string | **20 of 30** |
| Eval, unanswerable questions refused with the fixed sentence | 5 of 9 (4 answered anyway, 2 of those said "not in the passages" in their own words) |
| Eval, prompt-tuning rounds | 0 (one calibration of `min_score` on 16 probe questions that are not in the eval) |
| Mutation check, first run | 68 of 72 killed, 4 survived |
| Mutation check, final | 72 of 72 killed, after 4 tests were added to close the survivors (so the final number was shaped by the first run) |
| Mutation runner self test | planted hang, survivor and order-dependent test reported as expected; nothing left running |

## What this does not prove

- **No client PDFs.** Every PDF here is fictional and generated by `samples/make_pdfs.py`. Real documents have headers, footers, footnotes, tables spanning pages, scans, forms and encodings that these do not.
- **No big models.** Everything was measured with `llama3.2:1b` (1.2B parameters, 8-bit) and `nomic-embed-text`. Nothing is claimed about 7B, 70B or hosted models, except that the pipeline code does not depend on the model name.
- **No GPU tuning, no speed claims beyond the timings written down.** One Apple M1 with 8 GB of memory that was busy with other work; the timings in `docs/REAL-RUNS.md` are what that machine did, not a benchmark.
- **No OCR.** Scanned PDFs are detected and refused, not read.
- **No scale.** The largest index here is a few dozen chunks. Nothing was tried with thousands of pages, concurrent users or an index that does not fit in memory (the index is a flat faiss index: exact, and linear in the number of chunks).
- **No production use.** There is no authentication, no multi-user handling, no upgrade path for the store format, no monitoring. The CI file has never run.
- **No accuracy claim beyond the measured eval.** The eval is 30 answerable and 9 unanswerable questions about three fictional documents, scored by substring. Its numbers say how this setup did on those questions, not how it will do on yours.
- **The 1B model is weak.** Some of its answers in the eval are wrong, and they are listed in `docs/EVAL.md` next to the right ones.
- **The scenarios are staged.** The broken states were made by hand on purpose, and the checks were written knowing the fixes. They show a method (a check that fails on the broken state, passes on every real fix and refuses the tempting wrong fixes). They do not show that real inherited code breaks in these ways.
- **The mutation score is bounded by the 72 mutants chosen.** A killed mutant means the tests notice that particular bug.

## Known limits of the code

- **No OCR.** A scanned PDF is detected and reported (`doctor`, `ingest`), not read. Run it through an OCR tool first.
- **`--rebuild` after changing how text is read.** Changing `chunk_size`, `chunk_overlap` or `extract_mode` re-ingests changed files automatically. Changing the *code* of the extractor or the cleaner does not: unchanged files are skipped by hash, so use `ingest --rebuild`. Several scenarios use this as a trap.
- **Dehyphenation guesses.** A word broken at a line-end hyphen is joined (`inter-` / `national` becomes `international`). A real compound that happens to break at its hyphen (`twenty-` / `four`) is joined too.
- **`columns` mode splits the page in the middle.** A heading that spans both columns lands in the left column. Pages with three columns or irregular layouts are not handled.
- **The prompt size is an estimate.** The size check assumes 3 characters per token (the measured value on this text is about 3.9), which is deliberately pessimistic and may drop a passage that would have fitted. A second check after the call notices when the server reports far fewer prompt tokens than the prompt has characters for.
- **The refusal threshold is a blunt tool.** Cosine scores of unanswerable questions that are close to the topic of a document overlap with scores of answerable ones, so `min_score` only removes clearly off-topic questions. See the eval for what gets through.
- **A 1B model is weak.** It sometimes answers from the wrong passage, copies the wrong number, or ignores the instruction to refuse. The eval reports those answers as they were.
- **String matching in the eval cannot judge paraphrases.** An answer that is right in other words counts as wrong.

## Reproducing

```bash
python -m pytest                                  # offline tests, about 70 s (the lab is most of it)
python -m pytest -m live                          # live suite; needs Ollama with both models; writes .live-observations.jsonl (git-ignored)
python scripts/run_eval.py                        # the eval; writes docs/eval-results.json and docs/eval-table.md
python scenarios/run.py --backend ollama --record # the lab against the real server; rewrites docs/scenarios and docs/SCENARIOS.md
python scripts/mutation_check.py --selftest       # the runner proves itself (about 15 s)
python scripts/mutation_check.py                  # the full mutation run (minutes)
python samples/make_pdfs.py                       # regenerate the fictional PDFs (byte-identical)
```

The heavy scripts and the live suite wait for a calm machine first (`scripts/loadgate.py`: 1-minute load average below 6 and at least 35 percent of the memory free according to `memory_pressure`, a looser pause of load below 10 and 20 percent free between their items) because they were written for an 8 GB laptop that was doing other things. Swap used is deliberately not part of the rule: macOS keeps that figure high long after the pressure is gone. They give up after 20 minutes instead of running on a busy machine.

## Layout

```text
local_rag/            the pipeline (extract, clean, chunk, embed, store, ingest, prompt, ask, doctor, cli)
samples/              fictional PDFs and the script that generates them (make_pdfs.py); nothing real
scenarios/            the inherited-pipeline lab: framework, check process, 11 scenario definitions, extra PDFs
eval/questions.json   the 39 eval questions (written before the first eval run)
scripts/              eval, mutation check (+ mutants), calibration probe, load gate, process helper
tests/                offline tests, the lab as tests, the live suite (marker `live`)
docs/                 recorded real runs: SCENARIOS, REAL-RUNS, EVAL, MUTATION
.github/workflows/    CI (offline checks only; has never run)
```
