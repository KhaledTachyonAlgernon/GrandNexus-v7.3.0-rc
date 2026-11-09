# GrandNexus — status (2026-11-09, v7.2.5-rc)

**An anchored translator and a reference engine that decide without inventing, and a laboratory to measure whether a loop learns.**
Read this file first; `LOGBOOK.md` holds every hypothesis -> result -> decision (63 entries).

## The core (what is demonstrated)
| Part | File |
|---|---|
| Language spec, parser, reference engine (disjunctions, formula questions, reductio, universal questions), clingo export, bridge | `grandnexus/nexus_logic/` (ENGINE_VERSION ref-2.3) |
| Claude as anchored translator into that language (prompt v5.4, cached system prompt), Claude-alone control, reflective correction | `grandnexus/llm_interface/translator_v5.py` |
| Pathways (grammar, JSON, nx) -> reference engine -> strict verdict | `grandnexus/cognition/reasoning/text_reasoner.py` |
| Experience memory (verified corrections, TF-IDF retrieval) — measured, no effect shown (logbook 62) | `grandnexus/cognition/experience.py` |
| Benches | `tools/bench_folio.py`, `tools/bench_learning.py` (story-aware, read items excluded, power and cost printed, checkpoint/resume), `tools/story_split.py`, `tools/cost.py`, `tools/bench_deliberation.py`, `tools/diff_engines.py`, `tools/test_bench.py` |
| Colab harness | `tools/colab_save.py` (saves the repository it belongs to and checks the zip), `tools/experience_pools.py` |

Everything else (2025 scaffolding: memories, graph, orchestrator, 15/05 layer, ~100 modules) is an experimental ground, runnable, not demonstrated.

## Measured (claude-sonnet-5-5, strict = premises only)
- FOLIO v2 validation, 203 items, 6 runs: **83.1% ± 1.7** (ref-2.3 offline replay 84.0%), asserted errors **7**/run; Claude alone 84.5%, asserted errors **22-25**. Clingo agrees on 1,218/1,218 real programs. Literature (GPT-4, FOLIO v1, 2023-24): Logic-LM 78.9, Logic-LM++ 84.8, SymbCoT 83.3, LINC 72.5 — indicative only.
- FOLIO train, 100 fresh items: 78 vs Claude alone 79; asserted errors 2 vs 11.
- **The loop that learns: not demonstrated** (point 3 closed, logbook 62). Two pre-registered tests failed: run 4 (200 items) 9/6, run 5a (recall, 68 items) 3/1; together 12/7, p = 0.36. The effect of the earlier runs was recall of the same story, a selection artefact that did not replicate. Transfer with "lessons" (branch `lessons`) is parked, not rejected: FOLIO has 130 never-read items left, enough to see only a gain of about 7 points, while the effects seen are 2-3 points.

## Costs (logbook 63)
- The translator's system prompt is sent to the API prompt cache: same answers (API documentation), the cached part billed at 5% of the input price on Sonnet 5.5; estimated -25% per run.
- Every bench row records input, output, cache-read and cache-write tokens; the benches print the run's cost and what it would have cost without the cache (`tools/cost.py`, prices of 2026-11-09).
- Next lever, not done: the Batch API (-50% on everything, asynchronous), when a large run is planned.
- Before any run, the dry run prints the smallest gain the set can detect (80% power): do not launch a run that cannot conclude.

## Open experiments
- None. The cost check of this version (`notebooks/GrandNexus_v7_2_5-rc_cost_check.ipynb`, 5 seen validation items, about 6 calls) only confirms that the cache works and prints the real split.

## Work order (validated 2026-11-02, updated 2026-11-09)
1. v7.1.0 stable — done. 2. The comparable number (validation 203 x 3, literature read) — done. 3. The loop that learns — closed, not demonstrated (logbook 62). 4. Minimal boot profile: NexusCore as orchestrator only, modules tagged core / supported / experimental / archive — next, v7.3.0.

## Conventions
- Verdicts: yes / no / unknown / contradictory (French labels of the old frozen sets are mapped at load time; a set frozen with French labels has another content sha but the same ids).
- Answer = strict verdict; the background-knowledge verdict is reported apart, never counted.
- Test sets frozen by CONTENT sha (id, text, query, expected) before measuring; item texts never printed; criteria written in the logbook before measuring; paired sign tests; an item read for diagnosis becomes "seen". Draws are disjoint by story and exclude every item an experience phase has read; `--dry-run` prints the frozen set and its power before any call.
- Code, notebooks, benches, logbook, README in English (GitHub). Conversation in French.
- Each release: complete zip (with .git) for Drive, source notebook for the project folder, LOGBOOK_vX.md, a self-contained bench notebook (imports in every cell, 1-call pre-flight check, save with `tools/colab_save.py`). `-rc` until the criteria pass on unseen items.
- Execution on Colab; the Colab assistant sometimes rewrites cells: check that the executed protocol is the planned one (the result JSON records its exact command), and log it as executed if not. Notebooks stop with STOP when the repository is not the expected version; the save names the zip after what it holds.

## Known gaps
- Remaining FOLIO errors: mostly "unknown" where common sense is needed (refused by design) or a reading is incomplete; a few probable label errors (308, 929, 995, 1335).
- Legacy modules keep French comments/logs; slow shutdown and dead addressing in the live mode (see the end of LOGBOOK.md).
- `tools/bench_folio.py` still writes its results at the end of a run (checkpoint/resume exists in the learning bench only); no Batch mode yet.
