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
- GrandNexus's key is only ever read from `GRANDNEXUS_API_KEY`:
  - on Khaled's PC, a user environment variable he set once in his own terminal;
  - in a Claude Code cloud environment, an environment variable Khaled enters himself in the environment settings
    (a key held by the agent proxy is impossible: it refuses Anthropic domains, logbook 66). Only a dedicated key
    with a spending limit goes there. If the variable is absent, there is no API run in the cloud.
  Pass it only to the Python process of a bench, and never print it, echo it, or write it to a file:
  - bash: `ANTHROPIC_API_KEY="$GRANDNEXUS_API_KEY" python tools/bench_folio.py ...`
  - PowerShell: `$env:ANTHROPIC_API_KEY = $env:GRANDNEXUS_API_KEY; python tools/bench_folio.py ...; Remove-Item Env:ANTHROPIC_API_KEY`
- Before an API run, print its expected number of calls and wait for Khaled's go. The benches print their cost;
  after the first run in a new environment, Khaled checks that the API usage matches that cost (a much larger bill
  would mean Claude Code's own work went to the API key: stop and remove the key).

## Environment (once)
- Python 3.11+, git. In the repository: `python -m venv .venv`, activate it, then
  `pip install anthropic clingo sympy networkx psutil`.
- Windows: set `PYTHONUTF8=1` (user variable) so every file is read as UTF-8, child processes included.
- FOLIO is downloaded on first use into `tests_lab/data/` (git-ignored).

## Current state
- The current version and what is pending are in `STATUS.md` (section Handover); this file does not repeat them, so it
  cannot go stale (it said v7.3.0 until v7.7.3).
- Offline checks (0 API call) can be run at any time: every `tests_lab/test_*.py` with `python -W ignore` (each must exit
  0 and its last line must not start with FAIL), and `python -W ignore tools/boot_profiles.py` (four PASS lines).
- The next task comes from Khaled, with its criteria written in LOGBOOK.md first.
