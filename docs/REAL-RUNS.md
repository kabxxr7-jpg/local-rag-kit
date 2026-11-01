# Real runs: what actually happened with the real models

Everything here comes from runs against a real Ollama server on 2026-11-01. Nothing is simulated. Where something went wrong, it is written down.

## Machine and versions

| | |
|---|---|
| Machine | Apple M1, 8 CPU cores, 8 GB memory, macOS 27.2 (the OS version string the machine reports), busy with other programs during all runs |
| Ollama | 0.40.13 (server at `http://127.0.0.1:11434`) |
| Answer model | `llama3.2:1b`, digest `baf6a787fdff`, 1.2B parameters, quantisation Q8_0, 1.3 GB |
| Embedding model | `nomic-embed-text:latest`, digest `0a109f422b47`, 137M parameters, F16, 274 MB, 768 dimensions |
| Python | 3.11.14 |
| Packages | exactly `requirements.txt`; the ones that matter: faiss-cpu 1.15.1, numpy 2.4.6, pypdf 6.21.4, langchain-text-splitters 1.1.3, langchain-ollama 1.1.0, langchain-core 1.7.3, ollama (client) 0.6.3, pytest 9.2.0, reportlab 5.1.0 |
| Settings | the defaults in `local_rag/config.py` unless a run says otherwise |

## How the runs were made, and what went wrong with the runs themselves

The machine was shared with other programs, so every heavy job waits for a calm machine first (`scripts/loadgate.py`). That shaped the runs, and the rule itself changed once:

- **The first gate looked at swap and was wrong for this machine.** It required swap used below 4000 MB. macOS keeps the swap figure high long after the pressure that caused it is gone (it stayed between 3 and 5.5 GB for hours, including long stretches when the load was low), so jobs waited for a state that did not come back. The gate is now: 1-minute load average below 6 **and** at least 35 percent of the memory free (`memory_pressure`), with a looser pause (load below 10, 20 percent free) between the items of a job that is already running, because loading the two models takes about 20 points of free memory by itself. Swap is not part of the rule.
- Which runs used which gate: the first mutation run, the lab, the eval (both runs) and the first live suite run (13:40) used the swap-based gate. Only the live suite run of 15:21 used the final rule. The mutation check's logic did not change between its runs, only how long it waited.
- The first attempt at the full lab against the real server stopped after 20 minutes of waiting at 14.7 load average (the gate gave up on purpose). It had passed the first scenario (stale store) before. The whole lab was re-run later and is the recorded one.
- The first attempt at the live suite passed 7 tests, then the 8th failed because the gate gave up waiting and I stopped the run. The first attempt at the eval was stopped by hand after one question for the same reason. Both were re-run from the start.
- A third attempt at the live suite (14:44) ended with **13 errors, all from the gate** giving up after 20 minutes. No live test ran in it. It is not a live result and is not counted anywhere.
- One short probe of the server during development (a few requests of a truncation experiment) ran at a load average of 10.95, which is above the limit. It is noted here because it is outside the rule.

## The live suite (13 tests, `python -m pytest -m live`)

**13 passed, 0 failed, 0 errors, 0 skipped** on the finished repository (2026-11-01 15:21, with the final gate): 49.01 s in total, of which 30 s are the setup of the first test (30 s is the gate's polling interval, so the gate most likely waited one round before the suite started; pytest hides that message for passing tests); the tests themselves took about 19 s. The slowest: the server-cuts-the-prompt test 8.4 s, the command line end to end 3.4 s, the first real question 2.7 s. An earlier full run at 13:40 (swap-based gate) also passed 13 of 13, in 20.96 s, with identical answers and scores. What the tests saw:

| Test | What the real server and the code did |
|---|---|
| doctor against the real server | no problems: Ollama 0.40.13 answers, both models installed, 11 pages of text in the three PDFs, a full set of passages (about 720 tokens) fits into the 3776 tokens left of `num_ctx=4096` |
| embeddings | 768 numbers per text; related sentence 0.891 cosine to the question, unrelated 0.437; first call 0.6 s |
| ingest of the three PDFs | 24 chunks (handbook 11, kettle manual 8, price list 5) in 0.6 s |
| ingest again | nothing re-embedded, "unchanged" for all three, 0.01 s, the store's statistics unchanged |
| a known question | "How many days of annual leave do employees get?" answered **"Employees get 25 days of paid annual leave per calendar year."** with best score 0.846, 511 prompt tokens, 2.7 s. Cited: handbook p.2 (the page with the fact), p.1 and p.4 (the other two passages in the prompt) |
| an unrelated question | "Who painted the Mona Lisa?" refused at best score 0.463, the model was never called. (At the earlier `min_score` of 0.55 the answer to "What is the capital of Portugal?" had been "Porto": a score of 0.5 something got through. That is why the default is 0.60.) |
| a prompt that is too big (`num_ctx=1024`, k=12, no threshold) | 8 of 12 passages dropped before asking (estimate 653 tokens against a budget of 704), a warning names them; the server evaluated 505 tokens, i.e. all of the trimmed prompt. The answer to the vague question was "You need to know about leave, travel, and expenses." (true, useless) |
| the same, with the size check fooled (`chars_per_token=100`) | nothing dropped; the server evaluated only **514 tokens** of a prompt of about 5,000 characters and cut the rest without any message; the second line of defence flagged it ("probably cut the prompt. Do not trust this answer."). The answer began "According to the Harbor & Pine Studio staff handbook, here are the key points to know about leave, travel, and expenses:" and then listed the remote-work and opening-hours rules under "Leave" and "Travel": fluent and wrong, which is the point of the warning |
| a PDF without text | reported as failed: "'scanned-notice.pdf' has 1 page(s) but none has extractable text. It is probably a scan or a picture of text. This kit does not do OCR: run the file through an OCR tool first, then ingest the searchable PDF." |
| a model that is not pulled | `llama3.2:3b`: "Ollama is running at http://127.0.0.1:11434 but does not have the model 'llama3.2:3b'. Pull it with: ollama pull llama3.2:3b (or set the model name to one that `ollama list` shows)." |
| a store built with other vectors | "The question was embedded into 256 dimensions but the store holds 768-dimensional vectors (built with 'nomic-embed-text'). Rebuild the store: python -m local_rag ingest --rebuild <pdfs>" |
| Ollama not running (port 4799, nothing listening) | doctor: "[PROBLEM] Ollama does not answer at http://127.0.0.1:4799 ... Ollama is not running, or it listens on another address. Open the Ollama app or run `ollama serve`, then try again."; ingest: "Ollama does not answer at http://127.0.0.1:4799 (ConnectionError). Start it (open the Ollama app or run `ollama serve`) or fix ollama_host / LOCAL_RAG_OLLAMA_HOST." |
| the command line, end to end | `ingest` then `ask --json "How long is the warranty on the Aurora AK-200?"` answered "2 years", cited the kettle manual p.3 first, exit code 0 |

The full doctor output with the server down and the PDFs of `samples/pdfs` (captured separately):

```text
[PROBLEM] Ollama does not answer at http://127.0.0.1:4799
          (URLError: [Errno 61] Connection refused) Ollama is not running, or it listens on another address. Open the Ollama app or run `ollama serve`, then try again. If it runs elsewhere, set LOCAL_RAG_OLLAMA_HOST.
[warning] No store in '.rag-store' yet
          Nothing has been ingested here. Run: python -m local_rag ingest <pdf or folder>
[ok]      A full set of passages (about 720 tokens) fits into the 3776 tokens left of num_ctx=4096
[ok]      aurora-kettle-manual.pdf: text found on all 4 page(s)
[ok]      harbor-pine-handbook.pdf: text found on all 4 page(s)
[ok]      meridian-price-list.pdf: text found on all 3 page(s)
[PROBLEM] scanned-notice.pdf: no extractable text
          'scanned-notice.pdf' has 1 page(s) but none has extractable text. It is probably a scan or a picture of text. This kit does not do OCR: run the file through an OCR tool first, then ingest the searchable PDF.

2 problem(s).
```

## Questions and answers, including the wrong ones

The 39 eval questions with the real answers, scores and verdicts are in `EVAL.md` and `eval-results.json`, wrong answers included: for example "6 weeks" for the primary carer's parental leave (the other parent's figure), "Page 3 of 4" for the learning budget, "9 EUR" for the priority-support price, and a made-up "No, the Meridian Business plan does not include phone support" for a question the documents do not answer. 20 of 30 answerable questions were answered correctly. The two eval runs, half an hour apart, gave the same answers for all 39 questions.

## Calibration of the refusal threshold

`python scripts/calibrate.py samples/pdfs`: best retrieval score for 16 probe questions that are not in the eval. This is how `min_score = 0.60` was chosen, once, before the eval.

```text
--- ANSWERABLE
  0.787  harbor-pine-handbook.pdf p.1  What is the length of the standard working week?
  0.807  harbor-pine-handbook.pdf p.2  How many weeks of parental leave does the other parent get?
  0.813  harbor-pine-handbook.pdf p.3  What is the equipment budget for a laptop?
  0.844  aurora-kettle-manual.pdf p.2  How many temperature presets does the kettle have?
  0.803  aurora-kettle-manual.pdf p.1  What is the minimum amount of water for the kettle?
  0.641  meridian-price-list.pdf p.1  What is the price of the Starter plan?
  0.636  harbor-pine-handbook.pdf p.4  How long is the free trial?
  0.763  meridian-price-list.pdf p.3  What happens to deleted files in Meridian storage?
  min 0.636  max 0.844
--- UNANSWERABLE
  0.557  harbor-pine-handbook.pdf p.3  What is the best programming language for beginners?
  0.539  aurora-kettle-manual.pdf p.4  How tall is Mount Everest?
  0.791  aurora-kettle-manual.pdf p.4  What colour is the Aurora AK-200 kettle?
  0.703  harbor-pine-handbook.pdf p.1  Does Harbor & Pine Studio offer a pension plan?
  0.697  meridian-price-list.pdf p.2  Which payment methods does Meridian accept?
  0.558  aurora-kettle-manual.pdf p.1  How do I bake sourdough bread?
  0.585  harbor-pine-handbook.pdf p.1  Who is the managing partner of the studio?
  0.582  harbor-pine-handbook.pdf p.1  What is the weather in Lisbon today?
  min 0.539  max 0.791
```

0.60 sits above the off-topic questions (0.54 to 0.59) and below the lowest answerable one (0.636). It cannot separate unanswerable questions that are about the same topic (0.70 to 0.79) from answerable ones, and the eval shows the cost on both sides.

## The context window: what the server does with a prompt that is too long

`python scripts/measure_truncation.py` (same question, more and more passages). "server prompt tokens" is `prompt_eval_count` from the server.

```text
24 passages available; question: How many days of paid annual leave does each employee get per year?
num_ctx passages  chars  server prompt tokens  chars/token  answer
   4096        2   1362                   350         3.89  '25'
   4096        4   2175                   552         3.94  '25'
   4096        6   2801                   711         3.94  '[2] (harbor-pine-handbook.pdf, page 2)\nEvery emplo'
   4096        8   3487                   888         3.93  '[2] (harbor-pine-handbook.pdf, page 2)\nEvery emplo'
   4096       12   4954                  1274         3.89  '25'
   4096       16   6578                  1685         3.90  '25'
   1024        2   1362                   350         3.89  '25'
   1024        4   2175                   552         3.94  '25'
   1024        6   2801                   711         3.94  '[2] (harbor-pine-handbook.pdf, page 2)\nEvery emplo'
   1024        8   3487                   888         3.93  '[2] (harbor-pine-handbook.pdf, page 2)\nEvery emplo'
   1024       12   4954                   514         9.64  'According to the text, each employee gets 36 hours'
   1024       16   6578                   514        12.80  'According to the text, each employee gets 365 days'
```

- English text from these PDFs is **3.9 characters per token** for this model, so the default estimate of 3.0 is pessimistic on purpose.
- With `num_ctx=1024` a prompt of 4,954 characters (about 1,270 tokens) is not rejected and not reported: the server evaluates **514 tokens** (half the window plus two) and silently drops the rest, keeping the end of the prompt. The same for 6,578 characters. Neither `num_predict` nor the answer text tells you.
- That is why there are two defences in `local_rag/ask.py`: the size check before the call (trim visibly, or refuse), and a check after the call that compares the server's token count with the prompt (a count at or above `num_ctx - 8`, or more than 5.5 characters per token, is flagged).
- At 6 and 8 passages the model answered by copying a passage header (`[2] (harbor-pine-handbook.pdf, page 2) ...`) instead of answering. That is a weak-model behaviour, not a pipeline fault, and it is visible in the eval as well (U03).

## Embedding with the answer model

`llama3.2:1b` cannot be used as the embedder: the server answers HTTP 501, "does not support embeddings". The dimension-mismatch scenario therefore changes `embed_dimensions` (nomic-embed-text can return shorter vectors) instead of switching model.

## The inherited-pipeline lab against the real server

`python scenarios/run.py --backend ollama --record`, 2026-11-01 14:01 to 14:06 (4 min 27 s for everything): 11 scenarios, **11 behave as designed, 16 of 16 fixes pass the check, 38 of 38 wrong fixes are refused.** The output of every command is in `SCENARIOS.md` and `scenarios/`.

## The mutation check

See `MUTATION.md`. First run 68 of 72 killed, final run 72 of 72.
