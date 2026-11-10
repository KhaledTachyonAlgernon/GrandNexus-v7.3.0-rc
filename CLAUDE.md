# GrandNexus — instructions for Claude Code

Read `STATUS.md` first (current state), then `LOGBOOK.md` (every hypothesis -> result -> decision) and `MODULES.md`
(status of every module). These files win over anything remembered from a conversation.
Talk with Khaled in French. Code, commits, benches, notebooks, LOGBOOK, STATUS and README stay in English.

## Measurement protocol (non-negotiable)
- Criteria are written in `LOGBOOK.md` BEFORE any measurement. Test sets are frozen by content sha (`--dry-run` shows it).
- Run exactly the command written in the logbook or in STATUS. Never change a bench, a criterion, a seed or a set to make
  a run pass. If something does not match (sha, version, missing file), STOP and report; do not improvise.
- Never print, quote or summarise the text of a test item. An item read for a diagnosis becomes "seen" (log it).
- Trivial controls and paired sign tests are part of every comparison. No claim without a pre-registered test on
  independent items. If a run deviates from the plan, it is archived "as executed" in the logbook, never hidden.
- Repair before replacing: no rewrite, reduction or "simplified version" without Khaled's explicit agreement.
  Everything is committed; a rework is a branch.

## API key (cost safety)
- Claude Code itself must run on Khaled's Claude subscription. NEVER set `ANTHROPIC_API_KEY` for the session, in a
  settings file or in a `.env` file: Claude Code would use it and bill its own work to the API account.
- The key lives in the variable `GRANDNEXUS_API_KEY`, never in `ANTHROPIC_API_KEY`:
  - on Khaled's PC, a user environment variable he set once in his own terminal;
  - in a Claude Code cloud environment, the real key is an API credential held by the agent proxy for
    `api.anthropic.com`; the environment variables only hold the placeholder `GRANDNEXUS_API_KEY=proxy-injected`.
  Pass it only to the Python process of a bench, and never print it or write it to a file:
  - Git Bash: `ANTHROPIC_API_KEY="$GRANDNEXUS_API_KEY" python tools/bench_folio.py ...`
  - PowerShell: `$env:ANTHROPIC_API_KEY = $env:GRANDNEXUS_API_KEY; python tools/bench_folio.py ...; Remove-Item Env:ANTHROPIC_API_KEY`
- Before an API run, print its expected number of calls and wait for Khaled's go. The benches print their cost;
  after the first run in a new environment, Khaled checks that the API usage matches that cost (a much larger bill
  would mean Claude Code's own work went to the API key: stop and remove the credential).

## Environment (once)
- Python 3.11+, git. In the repository: `python -m venv .venv`, activate it, then
  `pip install anthropic clingo sympy networkx psutil`.
- Windows: set `PYTHONUTF8=1` (user variable) so every file is read as UTF-8, child processes included.
- FOLIO is downloaded on first use into `tests_lab/data/` (git-ignored).

## Current task: the v7.3.0 check (logbook 64-65), the local equivalent of `notebooks/GrandNexus_v7_3_0-rc_check.ipynb`
1. `git describe --tags` must print `v7.3.0-rc`. Otherwise STOP.
2. Offline tests, 0 API call: run every `tests_lab/test_*.py` with `python -W ignore`; each must exit 0 and its last line
   must not start with FAIL.
3. Boot profiles, 0 API call: `python -W ignore tools/boot_profiles.py`: four PASS lines expected.
4. Prompt cache on the real API, about 6 calls (ask Khaled first):
   `python tools/bench_folio.py --split validation --n 5 --seed 0 --modes translator --strict` with the key passed as above.
   Expected: a `cost TOTAL ... saved N%` line, and cache reads > 0 in the rows of the result JSON
   (`tests_lab/resultats/folio_validation_5_*.json`, fields `cache_read`).
5. If 2, 3 and 4 pass: `git add -A`, commit `v7.3.0 check (local): all criteria pass`, then `git tag v7.3.0`.
   Otherwise commit `v7.3.0 check (local): NOT all criteria pass`, no tag. Show Khaled the outputs of steps 3 and 4.
