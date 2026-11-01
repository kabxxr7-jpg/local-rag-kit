# Eval: 30 answerable and 9 unanswerable questions, real models

Recorded run: 2026-11-01 14:29:36, Ollama 0.40.13, `llama3.2:1b` (answers) and `nomic-embed-text` (search). Settings: k=4, min_score=0.6, chunk_size=500, chunk_overlap=80, extract_mode=layout, num_ctx=4096. Documents: the three fictional PDFs in `samples/pdfs` (24 chunks). Raw results: `eval-results.json`. Reproduce: `python scripts/run_eval.py` (needs Ollama).

The eval was run twice, half an hour apart (14:01 and 14:29). The two runs gave identical retrievals and identical answers for all 39 questions (temperature 0, seed 0). The second run added the two "fact in passage" lines below and is the one recorded.

## How it is scored

- The questions are in `eval/questions.json`. They were written before the first eval run and have not been edited since. Each answerable question names the file and page that holds the fact and a list of accepted strings.
- **Retrieval** is scored separately from the answer: a *hit* means the right file and page are among the 4 retrieved passages (hit@k), or are the best passage (hit@1). It does not depend on the model. It is a page-level check: the retrieved chunk on that page may be another chunk than the one holding the fact.
- **Answer correctness** is a case-insensitive substring match: one of the accepted strings must appear in the answer, and a refusal is never correct. It cannot judge a right answer in other words, and a short string such as `25` would also match inside `125`.
- **Citation** is scored separately: the right file and page must be among the cited ones. The citations are the pages of the passages that went into the prompt, not a claim about which one the model used.
- **Unanswerable** questions are right when the answer is the refusal sentence (below the score threshold, or declined by the model), and wrong when the model answers anyway.
- **Prompt-tuning rounds: 0.** The prompt in `local_rag/prompt.py` was written once and never changed after seeing eval results. The only tuning before the eval was one calibration of `min_score` on 16 probe questions that are not in the eval set (`scripts/calibrate.py`, output in `REAL-RUNS.md`). Nothing was tuned on these 39 questions, because tuning on them would turn them into training data and the numbers below into a claim they could no longer support.

## Numbers

| | result |
|---|---|
| Retrieval, right file and page in the top 4 | **29 of 30** |
| Retrieval, right file and page is the best passage | **27 of 30** |
| Answer contains an accepted string | **20 of 30** |
| ... and the right page is cited | 20 of 30 |
| Answers that are right, given that the model was asked with a hit in the top 4 | 20 of 26 |
| Unanswerable questions refused with the refusal sentence | **5 of 9** |
| Unanswerable questions answered anyway (strict count) | 4 of 9: U02, U03, U04, U08 |
| Generous check: an accepted string appears somewhere in the prompt | 27 of 30 (short strings can match by accident, for example P03's `15`) |
| Time for all 39 questions, model already loaded | 31.2 s (median 0.7 s per question) |

Where the 10 answerable questions that are not correct went (every one is in the table below):

- **3 were refused by the score threshold although retrieval had found the right page** (H12, K07, P02: best scores 0.545, 0.535 and 0.575, `min_score` is 0.60). The model never saw them.
- **6 were answered wrongly although the right page was the best match and an accepted string was somewhere in the prompt**: H02 ("2" for remote days, the text says three), H06 ("6 weeks" for parental leave: the handbook gives the primary carer 18 weeks and the other parent 6, the model answered with the wrong parent), H09 ("Page 3 of 4"), H11 ("10"), K01 (the minimum fill level instead of the maximum) and P04 ("9 EUR").
- **1 was a retrieval miss** (P03: the discount question; the right page was not among the top 4 and the model answered "40 percent off the Plus plan" from another passage).

The unanswerable questions, read by a person instead of by the strict rule: U01, U05, U09 were stopped by the threshold, U06 and U07 were declined by the model. Of the four that were answered, **U02 and U08 said in their own words that the passages do not contain the information** (the right behaviour, but not the fixed sentence, so the strict count calls them wrong), **U04 invented an answer** ("No, the Meridian Business plan does not include phone support"; the document says nothing about phone support) and **U03 pasted an unrelated passage**. So by a stricter human reading 5 of 9 are handled well by the rule, 7 of 9 if "in its own words" counts, and 2 are real failures.

## What this says, and what it does not

- Retrieval is good on this tiny corpus (24 chunks). That says little about a corpus a hundred times larger.
- The weak part is the 1B model: when it was asked, with the right page as the best match, it still got 6 of 26 wrong. The instruction "keep the answer short" sometimes produces a bare number without the context that would make it checkable ("2", "10").
- A score threshold cannot separate near-topic unanswerable questions from answerable ones: U02 to U04 and U08 scored 0.67 to 0.77, higher than several answerable questions. Lowering `min_score` to rescue H12, K07 and P02 would let U01 (0.568) and U05 (0.587) through to the model. The 0.60 default is a compromise made before the eval, and this eval does not show it is the best value.
- 39 questions about three fictional documents measure this setup on these questions. They are not an accuracy figure for any other documents, model or question style.

## All 39 questions

| id | question | retrieval (file p.page, score) | answer | right? | cited | note |
|---|---|---|---|---|---|---|
| H01 | What are the core hours at Harbor & Pine Studio? | harbor-pine-handbook p.1 (0.78) | 1. 10:00 to 15:00 Central European Time. | yes | yes | retrieval hit |
| H02 | How many days per week may staff work remotely? | harbor-pine-handbook p.1 (0.895) | 2 | NO | yes | retrieval hit |
| H03 | On which day of the week are there no meetings? | harbor-pine-handbook p.1 (0.626) | There are no meetings on Wednesdays. | yes | yes | retrieval hit |
| H04 | How many days of paid annual leave does each employee get per year? | harbor-pine-handbook p.2 (0.843) | 25 | yes | yes | retrieval hit |
| H05 | How many unused leave days can be carried over to the next year? | harbor-pine-handbook p.2 (0.788) | Up to 5 unused days may be carried over and must be taken by 31 March of the following year; anything left after that date expires. | yes | yes | retrieval hit |
| H06 | How many weeks of parental leave does the primary carer receive? | harbor-pine-handbook p.2 (0.859) | 6 weeks | NO | yes | retrieval hit |
| H07 | Within how many days must an expense claim be submitted? | harbor-pine-handbook p.3 (0.801) | 30 | yes | yes | retrieval hit |
| H08 | What is the maximum hotel reimbursement per night when travelling? | harbor-pine-handbook p.3 (0.784) | 8. Travel When travelling for work, meals are reimbursed up to 45 EUR per day and hotels up to 140 EUR per night. | yes | yes | retrieval hit |
| H09 | How much is the yearly learning budget per person? | harbor-pine-handbook p.3 (0.797) | Page 3 of 4 | NO | yes | retrieval hit |
| H10 | In which months do performance reviews take place? | harbor-pine-handbook p.4 (0.748) | May and November. | yes | yes | retrieval hit |
| H11 | How long is the probation period for new employees? | harbor-pine-handbook p.4 (0.845) | 10 | NO | yes | retrieval hit |
| H12 | Who is the trust person for raising harassment concerns? | harbor-pine-handbook p.4 (0.545) | I could not find an answer to that in the ingested documents. | NO | no | retrieval hit |
| K01 | What is the maximum fill level of the Aurora AK-200? | aurora-kettle-manual p.1 (0.802) | 1. The minimum fill level is 0.5 litres. | NO | yes | retrieval hit |
| K02 | What does the display show when the kettle is switched on without water? | aurora-kettle-manual p.1 (0.702) | E1: dry-boil protection has switched the kettle off. | yes | yes | retrieval hit |
| K03 | Which temperature preset is for green tea? | aurora-kettle-manual p.2 (0.758) | 80 degrees. | yes | yes | retrieval hit |
| K04 | For how long does the keep-warm function hold the temperature? | aurora-kettle-manual p.2 (0.651) | 30 minutes | yes | yes | retrieval hit |
| K05 | How do you activate the child lock? | aurora-kettle-manual p.2 (0.791) | To lock the controls, hold the preset button for 3 seconds until the lock symbol lights up. | yes | yes | retrieval hit |
| K06 | How often should the kettle be descaled? | aurora-kettle-manual p.3 (0.82) | Every 4 weeks, or sooner when the ring light blinks amber. | yes | yes | retrieval hit |
| K07 | What does error code E3 mean? | aurora-kettle-manual p.3 (0.535) | I could not find an answer to that in the ingested documents. | NO | no | retrieval hit |
| K08 | How long is the warranty on the Aurora AK-200? | aurora-kettle-manual p.3 (0.868) | 2 years | yes | yes | retrieval hit |
| K09 | What is the code for ordering a spare limescale filter? | aurora-kettle-manual p.4 (0.62) | AF-20 | yes | yes | retrieval hit |
| K10 | How long is the mains cable of the kettle? | aurora-kettle-manual p.4 (0.742) | 0.75 m | yes | yes | retrieval hit |
| P01 | How much does the Pro plan cost per month? | meridian-price-list p.1 (0.607) | 29 | yes | yes | retrieval hit |
| P02 | How many users are included in the Business plan? | harbor-pine-handbook p.3 (0.575) | I could not find an answer to that in the ingested documents. | NO | no | hit, not first |
| P03 | How much discount do you get for paying a full year in advance? | meridian-price-list p.2 (0.633) | You get 40 percent off the Plus plan. | NO | no | retrieval MISS (wanted meridian-price-list p.1) |
| P04 | How much does the priority support add-on cost per month? | meridian-price-list p.2 (0.717) | 9 EUR | NO | yes | retrieval hit |
| P05 | Within how many days of a payment is a refund possible? | harbor-pine-handbook p.3 (0.668) | 10 days | yes | yes | hit, not first |
| P06 | What is the largest single file that can be uploaded? | meridian-price-list p.3 (0.669) | 50 GB | yes | yes | retrieval hit |
| P07 | How much is the service credit if the monthly uptime falls below 99.9 percent? | meridian-price-list p.3 (0.68) | 10 percent of that month's fee. | yes | yes | retrieval hit |
| P08 | In which countries are the data centres located? | meridian-price-list p.3 (0.636) | Finland and Ireland. | yes | yes | retrieval hit |
| U01 | What is the capital of Portugal? | harbor-pine-handbook p.1 (0.568) | I could not find an answer to that in the ingested documents. | refused (right) | - | below_threshold |
| U02 | How much does the Aurora AK-200 kettle cost? | aurora-kettle-manual p.1 (0.774) | [2] (aurora-kettle-manual.pdf, page 4) The cost of the Aurora AK-200 kettle is not mentioned in the provided passages. | ANSWERED (wrong) | - | answered |
| U03 | What is the dress code at Harbor & Pine Studio? | harbor-pine-handbook p.1 (0.756) | [3] (harbor-pine-handbook.pdf, page 4) Onboarding, feedback and conduct  10. Onboarding and probation Every new employee is paired with a buddy for the first... | ANSWERED (wrong) | - | answered |
| U04 | Does the Meridian Business plan include phone support? | meridian-price-list p.2 (0.666) | No, the Meridian Business plan does not include phone support. | ANSWERED (wrong) | - | answered |
| U05 | How many calories are in a cup of green tea? | aurora-kettle-manual p.2 (0.587) | I could not find an answer to that in the ingested documents. | refused (right) | - | below_threshold |
| U06 | What is the name of the chief executive of Meridian Cloud Storage? | meridian-price-list p.1 (0.704) | I could not find an answer to that in the ingested documents. | refused (right) | - | model_declined |
| U07 | Can the Aurora AK-200 be used on a gas stove? | aurora-kettle-manual p.1 (0.733) | I could not find an answer to that in the ingested documents. | refused (right) | - | model_declined |
| U08 | What is the salary of a senior designer at Harbor & Pine Studio? | harbor-pine-handbook p.1 (0.687) | There is no information about the salary of a senior designer at Harbor & Pine Studio in the provided passages. | ANSWERED (wrong) | - | answered |
| U09 | Who won the football world cup in 2018? | harbor-pine-handbook p.4 (0.485) | I could not find an answer to that in the ingested documents. | refused (right) | - | below_threshold |
