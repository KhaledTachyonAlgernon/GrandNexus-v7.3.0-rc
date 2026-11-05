# GrandNexus — status (2026-11-05, v7.2.4-rc)

**An anchored translator and a reference engine that decide without inventing, and a laboratory to measure whether a loop learns.**
Read this file first; `LOGBOOK.md` holds every hypothesis -> result -> decision (58 entries).

## The core (what is demonstrated)
| Part | File |
|---|---|
| Language spec, parser, reference engine (disjunctions, formula questions, reductio, universal questions), clingo export, bridge | `grandnexus/nexus_logic/` (ENGINE_VERSION ref-2.3) |
| Claude as anchored translator into that language (prompt v5.4), Claude-alone control, reflective correction | `grandnexus/llm_interface/translator_v5.py` |
| Pathways (grammar, JSON, nx) -> reference engine -> strict verdict | `grandnexus/cognition/reasoning/text_reasoner.py` |
| Experience memory (verified corrections, TF-IDF retrieval) | `grandnexus/cognition/experience.py` |
| Benches | `tools/bench_folio.py`, `tools/bench_learning.py` (story-aware), `tools/story_split.py`, `tools/bench_deliberation.py`, `tools/diff_engines.py`, `tools/test_bench.py` |

Everything else (2025 scaffolding: memories, graph, orchestrator, 15/05 layer, ~100 modules) is an experimental ground, runnable, not demonstrated.

## Measured (claude-sonnet-5-5, strict = premises only)
- FOLIO v2 validation, 203 items, 6 runs: **83.1% ± 1.7** (ref-2.3 offline replay 84.0%), asserted errors **7**/run; Claude alone 84.5%, asserted errors **22-25**. Clingo agrees on 1,218/1,218 real programs. Literature (GPT-4, FOLIO v1, 2023-24): Logic-LM 78.9, Logic-LM++ 84.8, SymbCoT 83.3, LINC 72.5 — indicative only.
- FOLIO train, 100 fresh items: 78 vs Claude alone 79; asserted errors 2 vs 11.
- Learning loop (experience memory), 4 runs, 500 test items. Run 4 (pre-registered, 200 new items, memory fixed at 61): none 162, learned 165, paired 9/6 (p = 0.61), asserted errors 6 vs 8 -> **FAIL, no claim**. Post hoc (logbook 56): FOLIO asks several conclusions on one text ("story"); the whole effect of runs 1-4 sits on items whose story was already corrected in the memory (11/0 over 4 runs, p = 0.001) and vanishes on new stories (21/16, p = 0.51). The memory recalls a corrected reading of a text it has seen; it does not (yet) transfer a reading skill. These are now two separate, pre-registered questions.

## Open experiments
- **Run 5a — recall (pre-registered, logbook 57).** Memory fixed at 61; every never-used train item whose story is in the memory (68 items, 38 stories, sha 4895b2c3fc494d7a); none / random / learned:
  `python tools/bench_learning.py --split train --memory tests_lab/resultats/learning/memory_train_61exp_2026-11-04_191343.json --exp-n 0 --story-mode in-memory --test-n 0 --test-seed 7 --k 3 --conditions none,random,learned --exclude-from "tests_lab/resultats/learning/*.json" "tests_lab/resultats/folio/folio_train_*.json"`
  C-recall: paired sign test learned vs none p < 0.05 in favour of learned, asserted errors not above none; secondary learned > random. Notebook: `GrandNexus_bench_learning_run5a.ipynb`.
- **Run 5b — transfer (branch `lessons`, logbook 58, to pre-register after 5a).** Lessons (anchor span + abstract shape of each added statement, retrieved by logical cue words sentence by sentence) instead of whole programs, measured on story-disjoint items (`--story-mode disjoint`, 338 eligible items, sha 05635069103c4e77) against `none` and `lessons_random`.

## Work order (validated 2026-11-02)
1. v7.1.0 stable — done. 2. The comparable number (validation 203 x 3, literature read) — done. 3. The loop that learns — in progress: recall (run 5a) then transfer (run 5b). 4. Minimal boot profile: NexusCore as orchestrator only, modules tagged core / supported / experimental / archive — next.

## Conventions
- Verdicts: yes / no / unknown / contradictory (French labels of the old frozen sets are mapped at load time).
- Answer = strict verdict; the background-knowledge verdict is reported apart, never counted.
- Test sets frozen by CONTENT sha (id, text, query, expected) before measuring; item texts never printed; criteria written in the logbook before measuring; paired sign tests; an item read for diagnosis becomes "seen". Draws are disjoint by story (one key per premises text), not only by id; `--dry-run` prints the frozen set before any call.
- Code, notebooks, benches, logbook, README in English (GitHub). Conversation in French.
- Each release: complete zip (with .git) for Drive, source notebook for the project folder, LOGBOOK_vX.md, a self-contained bench notebook (imports in every cell, 1-call pre-flight check, Drive save). `-rc` until the criteria pass on unseen items.
- Execution on Colab; the Colab assistant sometimes rewrites protocols: check that the executed protocol is the planned one, and log it as executed if not. The learning bench checkpoints after every item and resumes after an interrupted session.

## Known gaps
- Remaining FOLIO errors: mostly "unknown" where common sense is needed (refused by design) or a reading is incomplete; a few probable label errors (308, 929, 995, 1335).
- Legacy modules keep French comments/logs; slow shutdown and dead addressing in the live mode (see the end of LOGBOOK.md).
- `tools/bench_folio.py` still writes its results at the end of a run (checkpoint/resume done for the learning bench only).
- The run-4 session started from a zip without the STATUS.md commit of v7.2.3-rc; STATUS.md is re-added here on top of the run-4 commit (documentation only, no code divergence).
