# Mutation check

Question: if someone breaks the code in a small, plausible way, do the offline tests notice? 72 hand-picked bugs ("mutants") were put into the code one at a time and the offline tests were run against each. A mutant is **killed** when a named test fails because of it, and **survives** when every test still passes.

Run it: `python scripts/mutation_check.py` (the full run), `--list`, `--validate`, `--only id1,id2`, `--json out.json`, `--markdown out.md`, `--selftest`. The mutants are in `scripts/mutants.py` (id, area, file, what the bug is, the exact text replaced).

## Result

| | mutants | killed | survived | unconfirmed | timeout | error |
|---|---|---|---|---|---|---|
| **First run** (`mutation-first-run.json`, taken before any test was added for it) | 72 | **68** | **4** | 0 | 0 | 0 |
| **Final run** (`mutation-final-run.json`, after 4 tests were added to close the survivors) | 72 | **72** | 0 | 0 | 0 | 0 |

**The final 72 of 72 was shaped by looking at the first run.** The four tests that close the survivors were written after seeing which mutants survived, so the final figure says "these 72 bugs are caught", not "the tests are 100 percent good". The first-run figure (68 of 72, 94 percent) is the one that was not tuned. Both runs took the offline tests without the live suite, without the scenario tests and without the tests of the tooling itself: 175 tests in the first run, 179 in the final one.

The first run reported 4 survivors, and all four were real gaps, none an equivalent mutant (a change that cannot alter behaviour):

| survivor | the bug | why no test saw it | test added |
|---|---|---|---|
| `clean-blank-lines-kept` | three or four newlines in a row are not collapsed (only five or more are) | the one existing test used five | `test_three_and_four_newlines_already_collapse_to_one_blank_line` |
| `extract-columns-split-point` | `columns` mode splits the page at one third of its width instead of the middle | every test PDF has its columns far from the split, so any split between them gave the same answer | `test_columns_mode_splits_at_the_middle_of_the_page_not_somewhere_else` (text starting at 40 and 60 percent of the width) |
| `prompt-keeps-last-three` | only the last three passages are written into the prompt | tests built prompts of at most three passages | `test_render_includes_every_passage_it_is_given` |
| `prompt-fit-boundary` | a prompt exactly as long as the budget is treated as too long | no test had an estimate equal to the budget | `test_a_prompt_exactly_as_long_as_the_budget_fits_and_one_token_less_does_not` |

The first run took 4490 s of which almost all was waiting: the load gate (below) held it back whenever the machine, which other programs were using heavily at the time, was busy. The final run took 1000 s. The test time itself is about 14 s for the unmutated baseline and a few seconds per mutant.

Mutants by area: prompt assembly 11, dedupe 10, config 8, chunking 7, cleaning 7, store 7, extraction 5, refusal 5, threshold 4, citations 3, doctor 3, cli 2.

## How the runner keeps itself honest

- **One mutant at a time, on a copy.** The repository is copied into a temporary folder (without `.venv`, `.git`, `.work`), the text is replaced there, the tests run, the file is restored and checked to be byte-identical again. The real files are never touched and the copy is deleted at the end. Bytecode is not written, so a stale `.pyc` of the previous mutant cannot be run by mistake.
- **A mutant must apply cleanly.** The text to replace must occur exactly once, must change the file, and the result must compile. `--validate` checks all of this (and that there are at least 30 mutants covering chunking, dedupe, threshold, citations, refusal, prompt assembly and config), the unit tests run it too.
- **The unmutated copy must be green first**, otherwise nothing is reported.
- **Every pytest run is a process group of its own.** On a timeout the whole group gets SIGKILL and is reaped; if anything of the group is still alive afterwards the run is an error.
- **A timeout is not a kill.** A mutant whose tests hang is reported as `timeout` and the run exits with code 2. Nothing in either run timed out.
- **A kill needs a named failing test that fails again when its file runs alone.** The complete test run is read from pytest's JUnit file. Then the file of a failing test is run alone, with the mutant still applied, and the same test has to fail again. If not, the status is `unconfirmed` and it does not count as a kill (this catches failures that depend on test order or leftovers). A pytest exit with failures but no named test (collection error, crash) is `error`. Every one of the 72 kills in the final run names its test in the table below.
- **A load gate.** Strict limits (1-minute load average below 6 and swap used below 4000 MB) before the baseline; a looser pause (load below 10, swap below 5500 MB) before each mutant, for at most 20 minutes, then the run stops instead of running on. The looser limit between items exists because a job on this 8 GB machine that loads a model raises swap by itself.
- **Exit codes:** 0 all killed, 1 survivors or unconfirmed kills, 2 the run cannot be trusted (timeout, error, baseline red, machine too busy).

### The self test

`python scripts/mutation_check.py --selftest` runs the same engine on a tiny throwaway project with four planted mutants and checks the verdict of each:

| planted | expected | what it proves |
|---|---|---|
| `add-minus` (`+` becomes `-`) | killed, by `tests/test_target.py::test_add` | a plain kill is found and named |
| `label-boundary` (`>` becomes `>=`, no test looks there) | survived | a gap is reported as a survivor, not hidden |
| `work-hangs` (starts a child process, then sleeps forever) | timeout | the group kill works; the child is gone afterwards (checked with `ps` for a unique marker) |
| `pollute-order` (fails only after another test file ran first) | unconfirmed | a failure that does not repeat when its file runs alone is not counted as a kill |

It also checks that no process is left and that the temporary folders are gone. It takes about 13 s. As a negative check, the group kill was replaced by a kill of the leader only (the child survives); the self test then failed with "processes still running after the run", so it does notice a broken kill.

## What this does and does not show

- The mutants were chosen by the person who wrote the code and the tests. A mutation tool that generates mutants mechanically would find other gaps. 72 is a sample of the bugs that are possible, not all of them.
- Only the package `local_rag/` is mutated. Scripts, the scenario lab and the tests are not.
- The scenario lab (`docs/SCENARIOS.md`) is a second line of defence that the mutation run leaves out for time: each wrong fix there is, in effect, a mutant that a check has to refuse.
- No equivalent mutants were found among the 72, but nobody proved there are none.

## Every mutant in the final run

| # | mutant | area | the bug | killed by |
|---|---|---|---|---|
| 1 | `chunk-id-ignores-page` | chunking | two pages with the same text get the same chunk id | `tests/test_chunk.py::test_chunk_id_is_deterministic_and_depends_on_every_part` |
| 2 | `chunk-id-ignores-source` | chunking | two files with the same text get the same chunk id | `tests/test_chunk.py::test_chunk_id_is_deterministic_and_depends_on_every_part` |
| 3 | `chunk-page-zero-based` | chunking | chunks are stored with a zero-based page | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 4 | `chunk-overlap-ignored` | chunking | chunk_overlap is not passed to the splitter | `tests/test_chunk.py::test_neighbouring_chunks_share_text_when_overlap_is_set` |
| 5 | `chunk-size-doubled` | chunking | chunks are twice as long as chunk_size | `tests/test_chunk.py::test_no_chunk_is_longer_than_chunk_size` |
| 6 | `chunk-index-from-one` | chunking | the index inside a page starts at 1 | `tests/test_chunk.py::test_index_counts_chunks_inside_each_page_from_zero` |
| 7 | `chunk-pages-joined` | chunking | all pages are split as one text and every chunk gets the first page | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 8 | `clean-no-nfkc` | cleaning | ligature characters are kept | `tests/test_clean.py::test_ligature_characters_become_letters` |
| 9 | `clean-hyphen-joins-capitals` | cleaning | a hyphen before a capital letter is also joined | `tests/test_clean.py::test_hyphen_before_a_capital_or_digit_is_kept` |
| 10 | `clean-wide-gap-two` | cleaning | two spaces already count as a column gap | `tests/test_clean.py::test_wide_gap_becomes_a_column_bar_and_single_spaces_stay` |
| 11 | `clean-blank-lines-kept` | cleaning | four blank lines in a row survive | `tests/test_clean.py::test_three_and_four_newlines_already_collapse_to_one_blank_line` (survived the first run) |
| 12 | `clean-keeps-invisible` | cleaning | soft hyphens and zero width characters stay | `tests/test_clean.py::test_soft_hyphen_and_zero_width_characters_are_removed` |
| 13 | `clean-lines-not-stripped` | cleaning | leading and trailing blanks of a line stay | `tests/test_clean.py::test_lines_are_stripped_but_not_merged` |
| 14 | `clean-old-mac-newlines` | cleaning | a lone carriage return is not a line break | `tests/test_clean.py::test_windows_and_old_mac_line_endings` |
| 15 | `extract-pages-from-zero` | extraction | page numbers start at 0 | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 16 | `extract-empty-pages-unlisted` | extraction | pages without text are skipped without saying so | `tests/test_doctor.py::test_a_half_scanned_pdf_is_a_warning` |
| 17 | `extract-scan-accepted` | extraction | a PDF with no text at all is accepted | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 18 | `extract-columns-split-point` | extraction | the column split is at one third of the page | `tests/test_extract.py::test_columns_mode_splits_at_the_middle_of_the_page_not_somewhere_else` (survived the first run) |
| 19 | `extract-columns-right-first` | extraction | the right column is read before the left one | `tests/test_extract.py::test_two_columns_interleave_in_plain_and_layout_but_not_in_columns_mode` |
| 20 | `store-no-normalisation` | store | vectors are not normalised, scores are no cosine | `tests/test_store.py::test_search_returns_best_first_with_cosine_scores_and_metadata` |
| 21 | `store-add-without-dedupe` | store | a chunk id that is already stored is added again | `tests/test_store.py::test_adding_the_same_chunk_twice_stores_it_once` |
| 22 | `store-remove-keeps-file-entry` | store | removing a file leaves its entry in meta | `tests/test_store.py::test_remove_source_removes_vectors_and_records_but_only_that_file` |
| 23 | `store-search-no-dimension-guard` | store | a query of the wrong size reaches faiss | `tests/test_ask.py::test_same_name_but_other_dimension_is_a_plain_error_not_a_crash` |
| 24 | `store-model-name-not-compared` | store | another embedding model name is accepted | `tests/test_ask.py::test_asking_with_another_embedding_model_is_refused_before_embedding` |
| 25 | `store-dimension-not-compared` | store | another vector size is accepted for the same model name | `tests/test_ingest.py::test_same_model_name_with_other_dimension_is_refused` |
| 26 | `store-ids-reused` | store | the id counter does not move after an add | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 27 | `ingest-never-skips` | dedupe | an unchanged file is processed again | `tests/test_cli.py::test_ingest_of_only_good_files_exits_0_and_a_repeat_says_unchanged` |
| 28 | `ingest-skip-ignores-settings` | dedupe | a changed chunk size does not trigger a new ingest | `tests/test_ingest.py::test_changing_the_chunk_size_reingests_and_replaces_the_old_chunks` |
| 29 | `ingest-skip-ignores-content` | dedupe | a changed file with the same name is skipped | `tests/test_ingest.py::test_a_changed_file_replaces_its_old_chunks_and_leaves_the_others` |
| 30 | `ingest-keeps-old-chunks` | dedupe | the old chunks of a re-ingested file are not removed | `tests/test_ingest.py::test_changing_the_chunk_size_reingests_and_replaces_the_old_chunks` |
| 31 | `ingest-signature-without-extract-mode` | dedupe | a changed extraction mode does not trigger a new ingest | `tests/test_ingest.py::test_changing_the_extract_mode_reingests` |
| 32 | `ingest-one-bad-pdf-aborts-all` | dedupe | a PDF without text stops the whole ingest | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 33 | `ingest-rebuild-ignored` | dedupe | --rebuild does not delete the old store | `tests/test_cli.py::test_rebuild_flag_resets_the_store` |
| 34 | `ingest-same-name-allowed` | dedupe | two different files with one name are not noticed | `tests/test_ingest.py::test_two_different_files_with_one_name_are_refused` |
| 35 | `ingest-folder-unsorted` | dedupe | files of a folder are taken in directory order | `tests/test_ingest.py::test_find_pdfs_takes_files_and_folders_sorted_and_without_repeats` |
| 36 | `ingest-model-check-after-embedding` | dedupe | the model name is only compared after the chunks were embedded | `tests/test_ingest.py::test_another_embedding_model_is_refused_before_anything_is_touched` |
| 37 | `ask-threshold-strict` | threshold | a best score equal to min_score is refused | `tests/test_ask.py::test_the_threshold_decides_both_ways` |
| 38 | `ask-threshold-inverted` | threshold | weak matches are answered, strong ones refused | `tests/test_ask.py::test_a_question_the_documents_answer_gets_the_fact_and_its_page` |
| 39 | `ask-weak-passages-in-prompt` | threshold | passages below min_score reach the prompt | `tests/test_ask.py::test_passages_below_the_threshold_never_reach_the_prompt` |
| 40 | `ask-usable-strict` | threshold | a passage exactly at min_score is left out of the prompt | `tests/test_ask.py::test_the_threshold_decides_both_ways` |
| 41 | `ask-refusal-answer-empty` | refusal | a refused question gets an empty answer | `tests/test_ask.py::test_below_the_threshold_the_answer_is_the_fixed_refusal_and_the_model_is_never_asked` |
| 42 | `ask-model-decline-ignored` | refusal | the model saying it does not know is treated as an answer | `tests/test_ask.py::test_when_the_model_declines_the_result_is_a_refusal_without_citations` |
| 43 | `ask-decline-reason` | refusal | a model refusal is reported with the wrong reason | `tests/test_ask.py::test_when_the_model_declines_the_result_is_a_refusal_without_citations` |
| 44 | `prompt-refusal-text-changed` | refusal | the fixed refusal sentence is different | `tests/test_ask.py::test_below_the_threshold_the_answer_is_the_fixed_refusal_and_the_model_is_never_asked` |
| 45 | `prompt-instructions-lose-refusal` | refusal | the model is not told which sentence to answer with | `tests/test_prompt.py::test_refusal_text_is_the_fixed_sentence_and_the_prompt_asks_for_exactly_it` |
| 46 | `ask-cites-everything-retrieved` | citations | citations name every retrieved page, not the ones in the prompt | `tests/test_ask.py::test_too_many_passages_are_trimmed_visibly_and_the_citations_follow` |
| 47 | `ask-citations-repeat` | citations | the same page is cited several times | `tests/test_ask.py::test_citations_are_the_files_and_pages_of_the_passages_in_the_prompt_without_repeats` |
| 48 | `ask-cites-dropped-passages` | citations | citations include passages that were trimmed away | `tests/test_ask.py::test_too_many_passages_are_trimmed_visibly_and_the_citations_follow` |
| 49 | `prompt-numbering-from-zero` | prompt assembly | passages are numbered from 0 | `tests/test_prompt.py::test_passages_are_numbered_from_one_and_name_file_and_page` |
| 50 | `prompt-keeps-last-three` | prompt assembly | only the last three passages are rendered | `tests/test_prompt.py::test_render_includes_every_passage_it_is_given` (survived the first run) |
| 51 | `prompt-estimate-rounds-down` | prompt assembly | the token estimate rounds down | `tests/test_prompt.py::test_estimate_rounds_up_and_uses_the_ratio` |
| 52 | `prompt-budget-ignores-reserve` | prompt assembly | the budget forgets the room for the template | `tests/test_prompt.py::test_budget_is_the_window_minus_the_answer_and_the_template` |
| 53 | `prompt-budget-ignores-answer-room` | prompt assembly | the budget forgets the room for the answer | `tests/test_prompt.py::test_budget_is_the_window_minus_the_answer_and_the_template` |
| 54 | `prompt-drops-best-first` | prompt assembly | when the prompt is too long the best passage goes first | `tests/test_ask.py::test_too_many_passages_are_trimmed_visibly_and_the_citations_follow` |
| 55 | `prompt-fit-boundary` | prompt assembly | a prompt exactly as long as the budget does not fit | `tests/test_prompt.py::test_a_prompt_exactly_as_long_as_the_budget_fits_and_one_token_less_does_not` (survived the first run) |
| 56 | `prompt-refuse-mode-ignored` | prompt assembly | on_overflow=refuse still trims | `tests/test_ask.py::test_refuse_on_overflow_does_not_ask_the_model` |
| 57 | `ask-overflow-silent` | prompt assembly | dropped passages are not reported | `tests/test_ask.py::test_too_many_passages_are_trimmed_visibly_and_the_citations_follow` |
| 58 | `ask-cut-prompt-at-limit-missed` | prompt assembly | a server reporting the window size is not flagged | `tests/test_ask.py::test_a_server_that_reports_the_window_size_is_flagged` |
| 59 | `ask-cut-prompt-ratio-missed` | prompt assembly | a server reading far fewer tokens than the prompt has is not flagged | `tests/test_ask.py::test_a_server_that_reports_far_fewer_tokens_than_the_prompt_has_is_flagged` |
| 60 | `config-flag-below-env` | config | a command line flag no longer beats the environment | `tests/test_cli.py::test_flags_beat_the_environment` |
| 61 | `config-env-below-file` | config | the environment no longer beats the config file | `tests/test_config.py::test_file_is_below_environment_and_flags_are_above` |
| 62 | `config-overlap-may-equal-size` | config | chunk_overlap equal to chunk_size is accepted | `tests/test_config.py::test_validation_rejects_contradictions[changes0-chunk_overlap]` |
| 63 | `config-min-score-above-one` | config | min_score above 1 is accepted | `tests/test_config.py::test_validation_rejects_contradictions[changes4-min_score]` |
| 64 | `config-unknown-file-key-ignored` | config | a typo in a config file is silently ignored | `tests/test_config.py::test_unknown_key_in_file_lists_the_known_ones` |
| 65 | `config-num-predict-may-equal-ctx` | config | num_predict equal to num_ctx is accepted | `tests/test_config.py::test_validation_rejects_contradictions[changes7-num_predict]` |
| 66 | `config-default-threshold` | config | the default refusal threshold is 0.3 | `tests/test_config.py::test_defaults_are_the_documented_ones` |
| 67 | `config-default-k` | config | the default k is 3 | `tests/test_config.py::test_defaults_are_the_documented_ones` |
| 68 | `cli-failed-pdf-exit-zero` | cli | an ingest with a failed PDF exits 0 | `tests/test_cli.py::test_ingest_prints_what_it_did_and_exits_1_because_the_scan_failed` |
| 69 | `cli-error-exit-code` | cli | a plain error exits with 1 instead of 2 | `tests/test_cli.py::test_errors_are_one_line_on_stderr_with_exit_code_2_and_no_traceback` |
| 70 | `doctor-tag-prefix-match` | doctor | a model name matches any installed name that starts with it | `tests/test_doctor.py::test_a_name_without_tag_matches_latest_but_a_tag_must_match` |
| 71 | `doctor-store-model-not-compared` | doctor | a store built with another model is reported healthy | `tests/test_doctor.py::test_store_built_with_another_model_is_the_dimension_mismatch_story` |
| 72 | `doctor-dimension-probe-skipped` | doctor | the dimension of the embedding model is not probed | `tests/test_doctor.py::test_same_name_other_dimension_is_found_by_probing_the_model` |
