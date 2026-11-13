#!/usr/bin/env python
"""
"Questions in free language", phase D (logbook 91): the first crutch of the living bench to remove.

Until now every question was canonical ("Is Bob a chess player?") and a template mapped it to the ontology's names
without a call. Here each canonical question is reworded by another model than the reader, and the reader has to find
the names of the memory by itself.

1. The free questions (frozen before any reading)
   writer   claude-opus-5-5, one call per world: the canonical questions as a numbered list, the answers never shown
   checks   mechanical: the person's name and, for a residence, the city are there; no other person or city; one
            sentence of at most 25 words ending with "?"; no negation marker; not the original wording
   judge    claude-haiku-5-5, a third model, one call per pair: SAME or DIFFERENT
   a rewording that fails is rewritten alone, twice at most; then the question keeps its canonical wording (fallback)
   frozen   tests_lab/questions/free_questions_seed<seed>_<worlds>w_<sessions>s.json, with a content sha; an existing
            file is loaded, never regenerated. The texts of a non-debug seed are never printed.
2. Reading a question
   The translator (unchanged prompt) receives the question alone with the lexicon block: the ontology's conventions,
   the names in memory at that session and one line saying that a question is asked. Only its question line is kept
   (a question never writes into the memory). The structured memory and the reference engine decide, strict.
3. Pipelines, all on the same fact readings (level 2, shared lexicon, as in logbook 88)
   canon           canonical questions through the template: the pipeline of logbook 89, the reference
   free_names      free questions read with the names in memory: the system under test
   free_names_bfs  the same goals on the trivial memory (reported)
   free_nonames    free questions read with the ontology's conventions but without the names in memory
   free_template   free questions through the template: the dumb control
4. Pre-registered (logbook 91)
   V   validity: the template gives the canonical goal for at most 50% of the free questions (fallbacks included)
   D1  free_names >= 95% right and 0 asserted error
   D3  free_names at most 3 points below canon on the same questions, with no more asserted errors
   D2  secondary hypothesis, not part of the claim: free_names beats free_nonames, paired sign test p < 0.05
   A question whose reading call failed counts as wrong; a failed fact reading counts as an empty reading.
   Gate on debug worlds (--gate): G1 Khaled's audit of 30 pairs finds at most 1 unfaithful; G2 = D1 on the debug
   worlds; G3 = V on the debug set.
5. Phase D' (logbook 93-94): n°93 failed by one asserted error, the reader having replaced a quality absent from memory
   by a neighbouring name present in it. Repairs, on by default: the question note 2 (keep the question's own word for
   what no name in memory says) and the substitution check (a predicate or constant of the goal that does not appear
   in the question is checked by the fidelity judge against it; DIFFERENT -> unknown). free_names is the checked
   answer, free_names_unchecked the same readings without the check. --question-note 1 --no-substitution-check
   reproduces n°91. Phase D': --seed 23 --worlds 20 --batch --skip-nonames.

  step 1a  python tools/living_questions.py --seed 11 --worlds 5 --generate-only --audit-sheet
  step 1b  python tools/living_questions.py --seed 11 --worlds 5 --audit-verdict none        (or "4,17")
  step 1c  python tools/living_questions.py --seed 11 --worlds 5 --gate
  step 2   python tools/living_questions.py --seed 19 --worlds 10 --batch --state-dir <Drive folder>   (n°91; phase D':
           --seed 23 --worlds 20 --batch --skip-nonames, with the gate on the same debug set and audit)
  any step with --dry-run prints its calls and an estimated cost without a call
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
import random
import re
import shutil
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from living_bench import CITIES, DEBUG_SEEDS, KINDS_V2, NAMES, USED_SEEDS, WorldV2          # noqa: E402
import living_llm as B                                                                      # noqa: E402
from living_lab_language import reading, sign_test, surfaces                                # noqa: E402

WRITER_MODEL, JUDGE_MODEL, READER_MODEL = "claude-opus-5-5", "claude-haiku-5-5", "claude-sonnet-5-5"
GENERATION_VERSION = "g1"            # writer prompt, checks and judge prompt below; recorded in the frozen set
MAX_WORDS, MAX_REWRITES, AUDIT_N = 25, 2, 30
PIPELINES = ("canon", "free_names", "free_names_unchecked", "free_names_bfs", "free_nonames", "free_template")
QUESTIONS_DIR = ROOT / "tests_lab" / "questions"
RESULTS_DIR = ROOT / "tests_lab" / "resultats" / "living"

SYSTEM_WRITER = """You reword yes/no questions about people. For each question you are given, write ONE other way a person could ask the same thing.

Rules
1. Same meaning. In every possible situation, the answer to your question (yes, no, or not known) must be the answer to the original question.
2. Keep the names of people and cities exactly as they are written. Mention no other person and no other city.
3. Ask about what is the case now: present tense, no "used to", no "will".
4. No negation (not, never, no longer, ...) and no opposite word: do not turn "tidy" into "messy".
5. Add nothing: no detail, no reason, no assumption. Each question is reworded on its own; take nothing from the other questions of the list.
6. Do not repeat the original wording: change the words or the turn of the sentence, and vary your turns from one question to the next. You may name a role by what the person does, name a quality by a close synonym or by its noun, or build the sentence another way.
7. One sentence of at most 25 words, ending with a question mark.

Examples (other people, other words)
"Is Mona a singer?" -> "Does Mona sing?"
"Is Hugo tidy?" -> "Would you describe Hugo as a tidy person?"
"Does Lea live in Oslo?" -> "Is Oslo where Lea lives?"

Output
A JSON array with one object per question, in the same order, and nothing else:
[{"n": 1, "q": "..."}, {"n": 2, "q": "..."}]"""

SYSTEM_JUDGE = """You compare two yes/no questions about the same person. Reply SAME if the second is only another wording of the first: in every possible situation both have the same answer (yes, no, or not known). Naming a role by what the person does ("Is Mona a singer?" / "Does Mona sing?") or using a close synonym is SAME.
Reply DIFFERENT if the second asks something else: the opposite or a negated question, a past or future state instead of the present one, a stronger or weaker claim, another person or place, or added information.
Reply with one word: SAME or DIFFERENT."""

NEGATION = re.compile(r"\b(not|no|never|neither|nor|none|without|anymore|former|formerly|false|untrue|lacks?|lacking|"
                      r"fails?|unless|except)\b|n't\b|\bno longer\b|\bused to\b|\bany more\b")
REASONS = {"form": "it must be one sentence of at most 25 words ending with a question mark",
           "name": "the person's name must be kept exactly as written",
           "city": "the city's name must be kept exactly as written",
           "other name": "it must not mention another person or another city",
           "negation": "it must not use a negation",
           "same wording": "it must not repeat the original wording",
           "judge": "a checker judged that it does not ask the same thing as the original"}


# ----------------------------------------------------------------------------- the canonical questions of a seed
def canonical_items(seed: int, n_worlds: int, sessions: int) -> list:
    items = []
    for w in range(n_worlds):
        world = WorldV2(seed * 1000 + w, sessions, 5, 3)
        for s, (_facts, qs) in enumerate(world.sessions):
            for i, (kind, q, gold) in enumerate(qs):
                items.append({"world": w, "session": s, "index": i, "kind": kind, "gold": gold, "canonical": q})
    return items


def content_sha(items: list) -> str:
    rows = [[it["world"], it["session"], it["index"], it["kind"], it["canonical"], it["free"], it["gold"]] for it in items]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()


def _norm(q: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", q.lower()).strip()


def _who(canonical: str) -> tuple:
    m = re.match(r"Does (\w+) live in (\w+)\?$", canonical)
    if m:
        return m.group(1), m.group(2)
    return canonical.split()[1], None


def check(canonical: str, free) -> str | None:
    """Mechanical checks of a rewording: the reason it is refused, or None."""
    if not isinstance(free, str):
        return "form"
    t = free.strip()
    words = t.split()
    if "\n" in t or not t.endswith("?") or t.count("?") != 1 or not 2 <= len(words) <= MAX_WORDS:
        return "form"
    person, city = _who(canonical)
    has = lambda name: re.search(rf"\b{re.escape(name)}\b", t) is not None
    if not has(person):
        return "name"
    if city and not has(city):
        return "city"
    if any(has(n) for n in NAMES if n != person) or any(has(c) for c in CITIES if c != city):
        return "other name"
    if NEGATION.search(t.lower()):
        return "negation"
    if _norm(t) == _norm(canonical):
        return "same wording"
    return None


def template_share(items: list) -> float:
    """Share of the free questions for which the template still gives the canonical goal (validity check V)."""
    same = 0
    for it in items:
        g, c = B.goal_of(it["free"]), B.goal_of(it["canonical"])
        same += g is not None and c is not None and g[0] == c[0]
    return same / max(1, len(items))


# ----------------------------------------------------------------------------- writer, judge, generation
class Ledger:
    """Usage of the writer and judge calls, per model, and the retried transient errors."""
    def __init__(self) -> None:
        self.usage: dict = {}
        self.retries: list = []

    def add(self, model: str, resp) -> None:
        u = getattr(resp, "usage", None)
        g = lambda f: int(getattr(u, f, 0) or 0)
        t = self.usage.setdefault(model, {"tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "calls": 0})
        t["tokens_in"] += g("input_tokens"); t["tokens_out"] += g("output_tokens")
        t["cache_read"] += g("cache_read_input_tokens"); t["cache_write"] += g("cache_creation_input_tokens")
        t["calls"] += 1

    def cost(self) -> dict:
        import cost
        out = {m: cost.cost_usd(u, m) for m, u in self.usage.items()}
        out["usd"] = round(sum(c["usd"] for c in out.values() if c), 4)
        return out


def _ask(client, ledger: Ledger, model: str, system: str, user: str, max_tokens: int, **kw) -> str:
    from grandnexus.llm_interface.translator_v5 import create_with_retry
    resp = create_with_retry(client, log=ledger.retries, model=model, max_tokens=max_tokens, system=system,
                             messages=[{"role": "user", "content": user}], **kw)
    ledger.add(model, resp)
    return "".join(getattr(b, "text", "") for b in resp.content)


def _parse_list(reply: str, n: int) -> list | None:
    i, j = reply.find("["), reply.rfind("]")
    if i < 0 or j <= i:
        return None
    try:
        arr = json.loads(reply[i: j + 1])
    except ValueError:
        return None
    if not isinstance(arr, list) or len(arr) != n:
        return None
    out = []
    for k, x in enumerate(arr):
        q = x.get("q") if isinstance(x, dict) else x
        if isinstance(x, dict) and x.get("n") not in (None, k + 1):
            return None
        out.append(q.strip() if isinstance(q, str) else None)
    return out


def write_list(client, ledger: Ledger, model: str, questions: list) -> list:
    """One call for the questions of a world (a second one when the reply is not a well-formed list of the right
    length). Returns one rewording per question, or None where it must be written alone."""
    user = "Questions:\n" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    for _ in range(2):
        got = _parse_list(_ask(client, ledger, model, SYSTEM_WRITER, user, 200 + 60 * len(questions)), len(questions))
        if got is not None:
            return got
    return [None] * len(questions)


def write_one(client, ledger: Ledger, model: str, canonical: str, previous, reason) -> str | None:
    user = f"Questions:\n1. {canonical}"
    if reason:
        user += (f"\n\nYour previous rewording of this question was refused: {REASONS[reason]}."
                 + (f' It was: "{previous}"' if isinstance(previous, str) else "") + "\nWrite another one.")
    got = _parse_list(_ask(client, ledger, model, SYSTEM_WRITER, user, 300), 1)
    return got[0] if got else None


def judge_same(client, ledger: Ledger, model: str, canonical: str, free: str) -> bool:
    reply = _ask(client, ledger, model, SYSTEM_JUDGE, f"First: {canonical}\nSecond: {free}", 8)
    return reply.strip().upper().startswith("SAME")


# ---- the substitution check (logbook 94) ---------------------------------------------------------------------------
def _appears(token: str, words: list) -> bool:
    key = token[:4]
    return any(w.startswith(key) for w in words)


def substitutions(question: str, lits: list) -> list:
    """The names of the goal that come from nowhere in the question: a predicate or a constant none of whose parts
    (longer than 2 letters) starts a word of the question with its first four letters. Variables are not names."""
    words = re.findall(r"[a-z]+", question.lower())
    out = []
    for l in lits:
        names = [l.atom.pred] + [str(c) for c in l.atom.args if not str(c)[:1].isupper()]
        for n in names:
            parts = [t for t in n.split("_") if len(t) > 2]
            if parts and not any(_appears(t, words) for t in parts) and n not in out:
                out.append(n)
    return out


def render_goal(lits: list) -> str:
    """A goal as a plain yes/no question, for the judge: lives_in(rita, lyon) -> 'Is it true that Rita lives in Lyon?'."""
    nice = lambda c: str(c).replace("_", " ").title()
    clauses = []
    for l in lits:
        a = l.atom
        args, words = [nice(x) for x in a.args], a.pred.replace("_", " ")
        if a.pred == "lives_in" and len(args) == 2:
            c = f"{args[0]} lives in {args[1]}"
        elif len(args) == 1:
            c = f"{args[0]} is {words}"
        elif len(args) == 2:
            c = f"{args[0]} is {words} {args[1]}"
        else:
            c = f"{words} holds"
        clauses.append(("it is not the case that " if l.neg else "") + c)
    return "Is it true that " + " and ".join(clauses) + "?"


def check_substitution(client, ledger: Ledger, model: str, question: str, lits: list) -> dict:
    """{'checked': False} when the goal names only what the question says; otherwise the judge's verdict on the
    substitution (temperature 0): kept when the rendered goal asks the same thing as the question."""
    subs = substitutions(question, lits)
    if not subs:
        return {"checked": False}
    rendered = render_goal(lits)
    reply = _ask(client, ledger, model, SYSTEM_JUDGE, f"First: {question}\nSecond: {rendered}", 8, temperature=0.0)
    return {"checked": True, "names": subs, "rendered": rendered, "kept": reply.strip().upper().startswith("SAME")}


def frozen_path(seed: int, worlds: int, sessions: int, directory=None) -> pathlib.Path:
    return pathlib.Path(directory or QUESTIONS_DIR) / f"free_questions_seed{seed}_{worlds}w_{sessions}s.json"


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT)) if ROOT in path.parents else str(path)


ARCHIVE = True      # False with --no-write: an offline test with scripted stand-ins must leave nothing in the repository


def archive(path: pathlib.Path, directory: pathlib.Path) -> None:
    """A file kept outside the repository (on Colab: the Drive, so that a reset runtime loses nothing) is also copied
    into the repository, where the session save picks it up."""
    if ARCHIVE and path.exists() and path.parent.resolve() != directory.resolve():
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, directory / path.name)


def load_frozen(path: pathlib.Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    if content_sha(d["items"]) != d["sha"]:
        raise SystemExit(f"STOP: {path.name} does not match its content sha (the frozen set was modified)")
    return d


def generate(a, client) -> dict:
    """The frozen set of free questions for (seed, worlds, sessions): loaded when it exists, written otherwise
    (resumable world by world: an interrupted generation keeps the worlds already done)."""
    path = frozen_path(a.seed, a.worlds, a.sessions, a.questions_dir)
    repo_copy = frozen_path(a.seed, a.worlds, a.sessions)
    if not path.exists() and repo_copy.exists() and repo_copy != path:   # e.g. phase D' on Colab: the set of n°93
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_copy, path)
        print(f"frozen set taken from the repository: {repo_copy.name}")
    if path.exists():
        d = load_frozen(path)
        archive(path, QUESTIONS_DIR)
        print(f"frozen set loaded: {path.name}, {len(d['items'])} questions, sha {d['sha'][:16]} (0 call)")
        return d
    items = canonical_items(a.seed, a.worlds, a.sessions)
    partial = path.with_suffix(".partial.json")
    done = json.loads(partial.read_text(encoding="utf-8")) if partial.exists() else {}
    ledger = Ledger()
    for w in range(a.worlds):
        mine = [it for it in items if it["world"] == w]
        if str(w) in done:
            for it, saved in zip(mine, done[str(w)]):
                it.update(saved)
            continue
        first = write_list(client, ledger, a.writer, [it["canonical"] for it in mine]) if mine else []
        for it, cand in zip(mine, first):
            attempts, reason = [], "form"
            for k in range(1 + MAX_REWRITES):
                if k > 0 or cand is None:
                    cand = write_one(client, ledger, a.writer, it["canonical"], attempts[-1]["text"] if attempts else None,
                                     attempts[-1]["refused"] if attempts else None)
                reason = check(it["canonical"], cand)
                if reason is None and not judge_same(client, ledger, a.judge, it["canonical"], cand):
                    reason = "judge"
                attempts.append({"text": cand, "refused": reason})
                if reason is None:
                    break
            it["free"] = cand.strip() if reason is None else it["canonical"]
            it["fallback"] = reason is not None
            it["attempts"] = attempts
        done[str(w)] = [{k: it[k] for k in ("free", "fallback", "attempts")} for it in mine]
        path.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        print(f"  world {w + 1}/{a.worlds}: {len(mine)} questions reworded ({sum(u['calls'] for u in ledger.usage.values())} calls so far)")
    refused = [x["refused"] for it in items for x in it["attempts"] if x["refused"]]
    d = {"args": {"seed": a.seed, "worlds": a.worlds, "sessions": a.sessions, "writer": a.writer, "judge": a.judge,
                  "generation": GENERATION_VERSION},
         "sha": content_sha(items),
         "stats": {"questions": len(items), "fallbacks": sum(it["fallback"] for it in items),
                   "reworded_first_try": sum(len(it["attempts"]) == 1 and not it["fallback"] for it in items),
                   "refusals": {r: refused.count(r) for r in sorted(set(refused))},
                   "template_share": round(template_share(items), 4)},
         "cost": ledger.cost(), "retries": len(ledger.retries), "written": time.strftime("%Y-%m-%d %H:%M:%S"),
         "items": items}
    path.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    archive(path, QUESTIONS_DIR)
    if partial.exists():
        partial.unlink()
    print(f"frozen set written: {_rel(path)}, {len(items)} questions, sha {d['sha'][:16]}")
    print(f"  reworded at the first try {d['stats']['reworded_first_try']}, refusals {d['stats']['refusals'] or 'none'}, "
          f"fallbacks to the canonical wording {d['stats']['fallbacks']}; generation cost ${d['cost']['usd']:.3f}")
    return d


# ----------------------------------------------------------------------------- Khaled's audit (debug seeds only)
def audit_sample(frozen: dict) -> list:
    """Indices of the pairs Khaled reads: 30 distinct (canonical, free) pairs among the reworded questions, drawn with
    a seed fixed by the set (a question asked at two sessions is one pair)."""
    pool, seen = [], set()
    for k, it in enumerate(frozen["items"]):
        if not it["fallback"] and (it["canonical"], it["free"]) not in seen:
            seen.add((it["canonical"], it["free"]))
            pool.append(k)
    rng = random.Random(frozen["args"]["seed"] * 7919 + 1)
    return sorted(rng.sample(pool, min(AUDIT_N, len(pool))))


def audit_path(frozen: dict, directory=None) -> pathlib.Path:
    return pathlib.Path(directory or QUESTIONS_DIR) / f"audit_seed{frozen['args']['seed']}_{frozen['sha'][:12]}.json"


def audit_sheet(frozen: dict) -> None:
    if frozen["args"]["seed"] not in DEBUG_SEEDS:
        raise SystemExit("STOP: the questions of a non-debug seed are never printed")
    sample = audit_sample(frozen)
    print(f"\nAUDIT SHEET (debug worlds, seed {frozen['args']['seed']}; set sha {frozen['sha'][:16]}): {len(sample)} pairs.")
    print("For each pair: does the second question ask the same thing as the first (same answer in every situation)?\n")
    for n, k in enumerate(sample, 1):
        it = frozen["items"][k]
        print(f"{n:3}. {it['canonical']:38} ->  {it['free']}")
    refused = [(it["canonical"], x["text"]) for it in frozen["items"] for x in it["attempts"] if x["refused"] == "judge"]
    if refused:
        print(f"\nFor information, not counted: rewordings the judge refused ({len(refused)}; first 10)")
        for c, t in refused[:10]:
            print(f"     {c:38} ->  {t}")


def audit_verdict(frozen: dict, verdict: str, directory=None) -> dict:
    sample = audit_sample(frozen)
    v = verdict.strip().lower()
    bad = [] if v in ("none", "0", "[]", "") else sorted({int(x) for x in re.split(r"[,\s]+", v.strip("[] ")) if x})
    if any(not 1 <= n <= len(sample) for n in bad):
        raise SystemExit(f"STOP: the numbers must be between 1 and {len(sample)}")
    d = {"sha": frozen["sha"], "seed": frozen["args"]["seed"], "n": len(sample), "sample": sample, "unfaithful": bad,
         "auditor": "Khaled", "date": time.strftime("%Y-%m-%d %H:%M:%S")}
    p = audit_path(frozen, directory)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    archive(p, QUESTIONS_DIR)
    print(f"audit recorded: {len(bad)} of {len(sample)} pairs judged unfaithful {bad or ''} -> {p.name}")
    return d


def audit_ok(frozen: dict, directory=None) -> tuple:
    """(G1, the recorded audit or None): the audit is of this very set, covers its whole sheet, and finds at most 1
    unfaithful pair."""
    p = audit_path(frozen, directory)
    if not p.exists() and audit_path(frozen).exists():                       # the audit of n°93, kept in the repository
        p = audit_path(frozen)
    audit = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    g1 = bool(audit) and audit["sha"] == frozen["sha"] and audit["n"] == len(audit_sample(frozen)) and len(audit["unfaithful"]) <= 1
    return g1, audit


def audit_text(audit) -> str:
    return "missing" if not audit else f"{len(audit['unfaithful'])} unfaithful of {audit['n']}"


# ----------------------------------------------------------------------------- reading a question, the jobs
def read_question(tr, question: str, block: str) -> dict:
    """The translator reads a question asked alone. Its program is the question line; anything else it writes is
    ignored. One more round when no valid question line came back."""
    import grandnexus.llm_interface.translator_v5 as T
    from grandnexus.nexus_logic import parse
    user = block + T._user(B.QUESTION_TEXT, question)
    program = T.extract_program(tr._call(T.SYSTEM_TRANSLATE, user, "question"))
    prog, rounds = parse(program), 0
    if not prog.questions and tr.corrective_rounds > 0:
        rounds = 1
        msg = (user + "\n\nYOUR PROGRAM:\n```nx\n" + program.strip() + "\n```\n\nThe checker found no valid question line"
               + (":\n" + "\n".join(str(r) for r in prog.rejections) if prog.rejections else ".")
               + "\n\nReturn the program again in the same format: exactly one line starting with \"?\" and ending with "
                 "\".\", and nothing else.")
        program = T.extract_program(tr._call(T.SYSTEM_TRANSLATE, msg, "correct"))
    return {"program": program, "rounds": rounds}


def fact_chain(tr, sess: list, ontology: int, note: int = 1) -> list:
    """Job: the lexicon readings of one world, session after session (as in logbook 88). Per session: the parsed
    program (None when there is no text or the reading failed), and the two blocks a question asked at that session
    receives."""
    mem, out = B.Memory(), []
    for texts, _qs in sess:
        mem.new_session()
        prog, failed = None, False
        if texts:
            prog = reading(tr, " ".join(texts), B.lexicon_block(mem, True, ontology))
            failed = prog is None
            if prog is not None:
                mem.add_program(prog)
        out.append({"prog": prog, "failed": failed, "names": B.question_block(mem, True, ontology, note),
                    "nonames": B.question_block(mem, False, ontology)})
    return out


def question_job(tr, question: str, block: str) -> dict:
    try:
        return {**read_question(tr, question, block), "failed": False}
    except Exception as e:  # noqa: BLE001  (an API error that outlived the retries, an errored batch request)
        return {"program": "", "rounds": 0, "failed": True, "error": type(e).__name__}


# ----------------------------------------------------------------------------- the run
def run(a, client=None) -> dict:
    logging.disable(logging.CRITICAL)
    from grandnexus.llm_interface.translator_v5 import Translator, _default_client
    from grandnexus.nexus_logic import parse
    import cost
    debug = a.seed in DEBUG_SEEDS
    mode = "gate" if a.gate else "sandbox" if a.sandbox else "measurement"
    if mode == "measurement" and not a.no_write:      # a seed is measured once: a second run would be a second draw
        for d in {RESULTS_DIR} | ({pathlib.Path(a.state_dir)} if a.state_dir else set()):
            for f in sorted(d.glob("living_questions_D_measurement_*.json")):
                if json.loads(f.read_text(encoding="utf-8")).get("args", {}).get("seed") == a.seed:
                    raise SystemExit(f"STOP: seed {a.seed} has already been measured ({f.name}). A measurement is made once; "
                                     f"send that result.")
    raw = client if client is not None else _default_client()
    frozen = generate(a, raw)
    if a.gate:                                     # G1 first: without a passing audit the gate cannot pass, so nothing is read
        g1, audit = audit_ok(frozen, a.questions_dir)
        if not g1:
            print(f"\nGATE (logbook 91): G1 audit {audit_text(audit)} (at most 1) FAIL  ->  FAIL; no reading was made. "
                  f"Run --audit-sheet, read the pairs, then --audit-verdict.")
            return {"args": vars(a), "mode": mode, "questions_sha": frozen["sha"],
                    "gate": {"G1": False, "G1_audit": audit and {"unfaithful": audit["unfaithful"], "n": audit["n"]},
                             "G2": None, "G3": None, "pass": False}}
    items = {(it["world"], it["session"], it["index"]): it for it in frozen["items"]}
    share = template_share(frozen["items"])
    conds = ("names",) if ((a.gate and not a.nonames) or a.skip_nonames) else ("names", "nonames")
    worlds = [WorldV2(a.seed * 1000 + w, a.sessions, 5, 3) for w in range(a.worlds)]
    surf = {w: surfaces(worlds[w], a.level, a.seed * 1000 + w, a.paraphraser) for w in range(a.worlds)}
    session = None
    if a.batch:
        from batch_runner import BatchSession
        key = hashlib.sha256(json.dumps([a.seed, a.worlds, a.sessions, a.level, a.model, a.paraphraser, a.ontology,
                                         frozen["sha"], list(conds)] + ([a.question_note] if a.question_note != 1 else [])
                                        ).encode()).hexdigest()[:10]
        out_dir = pathlib.Path(a.state_dir) if a.state_dir else RESULTS_DIR
        session = BatchSession(raw, out_dir / f"batch_state_phaseD_{key}.json")
        tr = Translator(client=session, model=a.model)
    else:
        tr = Translator(client=raw, model=a.model)
    # ---- 1. the fact readings (one sequential chain per world)
    chain_jobs = {f"lex|{w}": (lambda sess=sess: fact_chain(tr, sess, a.ontology, a.question_note)) for w, sess in surf.items()}
    print(f"{len(chain_jobs)} lexicon chains ({sum(1 for s in surf.values() for t, _ in s if t)} fact readings), then "
          f"{len(items) * len(conds)} question readings ({', '.join(conds)})")
    if session is not None:
        chains = session.run(chain_jobs)
    else:
        chains = {}
        for k, f in chain_jobs.items():
            chains[k] = f()
            print(f"  facts of world {len(chains)}/{len(chain_jobs)} read ({len(tr.receipts)} calls so far)")
    for k, v in chains.items():
        if isinstance(v, Exception):
            raise v
    # ---- 2. the question readings (each needs only the block of its session)
    q_jobs = {}
    for (w, s, i), it in items.items():
        for c in conds:
            q_jobs[f"q|{c}|{w}|{s}|{i}"] = (lambda q=it["free"], block=chains[f"lex|{w}"][s][c]: question_job(tr, q, block))
    if session is not None:
        qres = session.run(q_jobs)
    else:
        qres = {}
        for k, f in q_jobs.items():
            qres[k] = f()
            if len(qres) % 50 == 0:
                print(f"  {len(qres)}/{len(q_jobs)} questions read ({len(tr.receipts)} calls so far)")
    # ---- 3. offline: memories rebuilt from the chains, every pipeline decided
    rows, questions = [], []
    failed = {"fact_readings": 0, "question_names": 0, "question_nonames": 0}
    checks, check_ledger = {"checked": 0, "kept": 0, "refused": 0}, Ledger()
    for w, sess in surf.items():
        mem, chain = B.Memory(), chains[f"lex|{w}"]
        for s, (texts, qs) in enumerate(sess):
            mem.new_session()
            if chain[s]["prog"] is not None:
                mem.add_program(chain[s]["prog"])
            failed["fact_readings"] += chain[s]["failed"]
            for i, (kind, q, gold) in enumerate(qs):
                it = items[(w, s, i)]
                assert it["canonical"] == q and it["gold"] == gold, "the frozen set does not match the worlds"
                rec = {"key": f"{w}|{s}|{i}", "kind": kind, "gold": gold, "fallback": it["fallback"],
                       "goal_canon": B.goal_of(q)[0]}
                ans = {"canon": (*mem.decide(q), False), "free_template": (*mem.decide(it["free"]), False)}
                for c in conds:
                    r = qres[f"q|{c}|{w}|{s}|{i}"]
                    if isinstance(r, Exception) or r["failed"]:
                        failed[f"question_{c}"] += 1
                        ans[f"free_{c}"] = ("unknown", 0, True)
                        if c == "names":
                            ans["free_names_bfs"] = ans["free_names_unchecked"] = ("unknown", 0, True)
                        rec[f"goal_{c}"] = None
                        continue
                    prog = parse(r["program"])
                    ans[f"free_{c}"] = (*mem.decide_goal(prog), False)
                    if c == "names":
                        ans["free_names_bfs"] = (*mem.decide_goal(prog, trivial=True), False)
                        ans["free_names_unchecked"] = ans["free_names"]
                        g = B.goal_of_program(prog)
                        if a.substitution_check and g is not None and not g[2]:
                            chk = check_substitution(raw, check_ledger, a.judge, it["free"], g[1])
                            if chk["checked"]:
                                checks["checked"] += 1
                                checks["kept" if chk["kept"] else "refused"] += 1
                                rec["check"] = "kept" if chk["kept"] else "refused"
                                if debug:
                                    rec["check_rendered"] = chk["rendered"]
                                if not chk["kept"]:
                                    ans["free_names"] = ("unknown", 0, False)          # the system abstains
                    rec[f"goal_{c}"] = (B.goal_of_program(prog) or (None,))[0]
                    rec[f"rounds_{c}"] = r["rounds"]
                    if debug:
                        rec[f"program_{c}"] = r["program"]
                if debug:                                   # debug worlds: everything is kept for a diagnosis
                    rec.update({"canonical": q, "free": it["free"], "names_in_memory": chain[s]["names"].split("NAMES ALREADY IN MEMORY: ")[-1].split("\n")[0]})
                for p, (verdict, n, call_failed) in ans.items():
                    rows.append({"key": rec["key"], "world": w, "kind": kind, "gold": gold, "pipeline": p, "answer": verdict,
                                 "facts": n, "failed": call_failed})
                    rec[p] = verdict
                questions.append(rec)
    ok = lambda r: r["answer"] == r["gold"] and not r["failed"]              # a failed call is never a right answer
    asserted = lambda rs: sum(r["answer"] in ("yes", "no", "contradictory") and r["answer"] != r["gold"] for r in rs)
    by = {p: [r for r in rows if r["pipeline"] == p] for p in PIPELINES}
    n_q = len(questions)
    floor = 100 * sum(q["gold"] == "unknown" for q in questions) / max(1, n_q)
    out = {"args": vars(a), "mode": mode, "questions_sha": frozen["sha"], "generation": frozen["stats"],
           "failed_calls": failed, "pipelines": {}, "criteria": {}, "rows": rows, "questions": questions}
    print(f"\n=== phase D, {mode}: seed {a.seed}, {a.worlds} worlds, facts at level {a.level}, {n_q} questions "
          f"(set sha {frozen['sha'][:16]}; always-unknown floor {floor:.1f}%)")
    print(f"{'pipeline':15} {'right':>7} " + " ".join(f"{k:>10}" for k in KINDS_V2) + f" {'asserted err':>13} {'facts/q':>8}")
    for p in PIPELINES:
        rs = by[p]
        if not rs:
            continue
        per = {k: (sum(ok(r) for r in rs if r["kind"] == k), sum(r["kind"] == k for r in rs)) for k in KINDS_V2}
        st = {"n": len(rs), "pct": round(100 * sum(map(ok, rs)) / len(rs), 2), "asserted_errors": asserted(rs),
              "facts_per_question": round(sum(r["facts"] for r in rs) / len(rs), 2), "per_kind": per}
        out["pipelines"][p] = st
        print(f"{p:15} {st['pct']:6.1f}% " + " ".join(f"{c:>4}/{k:<5}" for c, k in per.values())
              + f" {st['asserted_errors']:>13} {st['facts_per_question']:>8.2f}")
    agree = sum(q.get("goal_names") == q["goal_canon"] for q in questions)
    print(f"goal read with the names = canonical goal: {agree}/{n_q} ({100 * agree / max(1, n_q):.1f}%, reported)")
    out["substitution_check"] = {**checks, "on": a.substitution_check, "question_note": a.question_note,
                                 "per_kind": {k: [sum(q.get("check") == v and q["kind"] == k for q in questions)
                                                  for v in ("kept", "refused")] for k in KINDS_V2}}
    print(f"question note {a.question_note}; substitution check {'on' if a.substitution_check else 'off'}: "
          f"{checks['checked']} goals named something the question does not say, {checks['kept']} kept by the judge, "
          f"{checks['refused']} refused (answered unknown)")
    print(f"failed calls: {failed} (a failed question reading counts as wrong, a failed fact reading as an empty reading)")
    # ---- criteria (logbook 91)
    P = out["pipelines"]
    v_ok = share <= 0.50
    d1 = P["free_names"]["pct"] >= 95 and P["free_names"]["asserted_errors"] == 0
    d3 = P["free_names"]["pct"] >= P["canon"]["pct"] - 3 and P["free_names"]["asserted_errors"] <= P["canon"]["asserted_errors"]
    crit = {"V": v_ok, "V_template_share": round(share, 4), "D1": d1, "D3": d3,
            "D3_detail": f"free_names {P['free_names']['pct']:.1f}% / {P['free_names']['asserted_errors']} asserted; "
                         f"canon {P['canon']['pct']:.1f}% / {P['canon']['asserted_errors']} asserted",
            "goal_agreement": [agree, n_q]}
    print(f"\nV  validity: the template still gives the canonical goal for {100 * share:.1f}% of the free questions "
          f"(fallbacks {frozen['stats']['fallbacks']}; at most 50%)  {'PASS' if v_ok else 'FAIL'}")
    tag = "" if mode == "measurement" else f"  ({mode}: no claim)"
    print(f"D1 free_names >= 95% right and 0 asserted error: {P['free_names']['pct']:.1f}%, {P['free_names']['asserted_errors']}  "
          f"{'PASS' if d1 else 'FAIL'}{tag}")
    print(f"D3 free_names at most 3 points below canon, no more asserted errors: {crit['D3_detail']}  {'PASS' if d3 else 'FAIL'}{tag}")
    if "free_nonames" in P:
        w_ = sum(ok(x) and not ok(y) for x, y in zip(by["free_names"], by["free_nonames"]))
        l_ = sum(ok(y) and not ok(x) for x, y in zip(by["free_names"], by["free_nonames"]))
        crit["D2"], crit["D2_paired"] = w_ > l_ and sign_test(w_, l_) < 0.05, [w_, l_, sign_test(w_, l_)]
        print(f"D2 (secondary, not part of the claim) free_names beats free_nonames: only with names right {w_} | only without "
              f"names right {l_} | sign test p = {sign_test(w_, l_):.2g}  {'PASS' if crit['D2'] else 'FAIL'}{tag}")
    if mode == "measurement":
        crit["claim"] = v_ok and d1 and d3
        print(f"CLAIM (V, D1 and D3): {'ESTABLISHED within the scope of logbook 91' if crit['claim'] else 'NOT established'}")
    out["criteria"] = crit
    if a.gate:
        g1, audit = audit_ok(frozen, a.questions_dir)
        out["gate"] = {"G1": g1, "G1_audit": ({"unfaithful": audit["unfaithful"], "n": audit["n"]} if audit else None),
                       "G2": d1, "G3": v_ok, "pass": g1 and d1 and v_ok}
        print(f"\nGATE (logbook 91): G1 audit {audit_text(audit)} (at most 1) {'PASS' if g1 else 'FAIL'} | "
              f"G2 = D1 on the debug worlds {'PASS' if d1 else 'FAIL'} | G3 = V {'PASS' if v_ok else 'FAIL'}  ->  "
              f"{'PASS' if out['gate']['pass'] else 'FAIL'}")
    if debug and a.show_failures:
        bad = [q for q in questions if q["free_names"] != q["gold"]][: a.show_failures]
        if bad:
            print(f"\nfree_names failures on the debug worlds (first {len(bad)}):")
        for q in bad:
            print(f"   [{q['kind']}] {q['canonical']}  ->  {q['free']} | goal read: {q.get('goal_names')} (canonical {q['goal_canon']}) "
                  f"| answer {q['free_names']}, gold {q['gold']}")
    # ---- cost
    u = session.usage() if session is not None else None
    c = cost.cost_usd(u, a.model) if u else cost.from_receipts(tr.receipts, a.model)
    cc = check_ledger.cost()
    out["cost"] = {"reader": c, "generation": frozen["cost"], "checks": cc,
                   "usd": round((c["usd"] if c else 0) + frozen["cost"]["usd"] + cc["usd"], 4)}
    out["retries"] = len(tr.retry_log)
    if c:
        print(f"\ncost: reader ${c['usd']:.3f} ({c['calls']} calls{', Batch API' if session is not None else ''}) + questions "
              f"${frozen['cost']['usd']:.3f} (writer and judge, paid once) + checks ${cc['usd']:.3f} = ${out['cost']['usd']:.3f}; "
              f"{len(tr.retry_log) + len(check_ledger.retries)} transient errors retried")
    if session is not None:
        out["batches"] = session.batches_created
        session.finish()
    if not a.no_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"living_questions_D_{mode}_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
        print(f"written: {_rel(path)}")
        if a.state_dir:                              # a second copy next to the batch state (on Colab: the Drive)
            archive(path, pathlib.Path(a.state_dir))
    return out


def dry_run(a) -> dict:
    worlds = [WorldV2(a.seed * 1000 + w, a.sessions, 5, 3) for w in range(a.worlds)]
    n_read = sum(1 for w in worlds for f, _ in w.sessions if f)
    n_q = sum(len(q) for w in worlds for _, q in w.sessions)
    conds = 1 if ((a.gate and not a.nonames) or a.skip_nonames) else 2
    exists = frozen_path(a.seed, a.worlds, a.sessions, a.questions_dir).exists() or frozen_path(a.seed, a.worlds, a.sessions).exists()
    half = 0.5 if a.batch else 1.0
    gen = 0.0 if exists else a.worlds * 0.03 + n_q * 0.00003
    usd = gen + n_read * 1.15 * 0.0038 * half + n_q * conds * 1.05 * 0.0016 * half + (n_q * 0.08 * 0.0002 if a.substitution_check else 0)
    print(f"seed {a.seed}, {a.worlds} worlds, level {a.level}: questions {'already frozen (0 call)' if exists else f'{a.worlds} writer calls + about {n_q} judge calls + rewrites'}; "
          f"{n_read} fact readings (+ corrective rounds, about 15%); {n_q} questions x {conds} reading(s) -> about "
          f"{int(n_read * 1.15 + n_q * conds * 1.05)} reader calls; estimated ${usd:.2f}"
          + (" with the Batch API (about 14 successive batches, 1.5-2.5 h, resumable)" if a.batch else " at the standard rate"))
    return {"fact_readings": n_read, "questions": n_q, "estimated_usd": round(usd, 2)}


def main(argv=None, client=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--worlds", type=int, default=10)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--level", type=int, default=2, help="paraphrase level of the facts (logbook 91: 2)")
    ap.add_argument("--model", default=READER_MODEL, help="the reader")
    ap.add_argument("--writer", default=WRITER_MODEL)
    ap.add_argument("--judge", default=JUDGE_MODEL)
    ap.add_argument("--paraphraser", type=int, default=2)
    ap.add_argument("--ontology", type=int, default=2)
    ap.add_argument("--generate-only", action="store_true", help="write (or load) the frozen set of free questions and stop")
    ap.add_argument("--audit-sheet", action="store_true", help=f"print the {AUDIT_N} pairs to audit (debug seeds only)")
    ap.add_argument("--audit-verdict", metavar="NUMBERS", help='Khaled\'s verdict on the audit sheet: "none", or the numbers of the unfaithful pairs, e.g. "4,17"')
    ap.add_argument("--gate", action="store_true", help="step 1 of logbook 91 on a debug seed: G1 (audit), G2, G3")
    ap.add_argument("--nonames", action="store_true", help="with --gate: also read the questions without the names (information)")
    ap.add_argument("--sandbox", action="store_true", help="a run on a debug seed without gate: no claim (offline tests)")
    ap.add_argument("--show-failures", type=int, default=12, help="debug seeds: print that many free_names failures")
    ap.add_argument("--question-note", type=int, default=2, choices=(1, 2), help="1: logbook 91; 2: logbook 94 (default)")
    ap.add_argument("--no-substitution-check", dest="substitution_check", action="store_false",
                    help="answer the goal read with the names as it is (logbook 91); default: the check of logbook 94")
    ap.add_argument("--skip-nonames", action="store_true", help="do not read the questions without the names (phase D')")
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--state-dir", help="where the batch state is kept and the result copied (on Colab: a Drive folder, so that a reset runtime resumes)")
    ap.add_argument("--questions-dir", help="where the frozen sets and the audit live (default: tests_lab/questions; on Colab: a Drive folder; "
                                            "they are copied into tests_lab/questions as well)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    global ARCHIVE
    ARCHIVE = not a.no_write
    debug = a.seed in DEBUG_SEEDS
    if a.audit_sheet:
        a.generate_only = True                      # the sheet is printed from the frozen set, nothing is read
    if (a.gate or a.sandbox or a.audit_sheet or a.audit_verdict) and not debug:
        raise SystemExit(f"STOP: gate, sandbox and audit work on the debug seeds {DEBUG_SEEDS} only")
    if not (a.gate or a.sandbox or a.dry_run or debug) and a.seed in USED_SEEDS:
        raise SystemExit(f"STOP: seed {a.seed} has already been used; a measurement needs never-used worlds (phase D', logbook 94: seed 23)")
    if debug and not (a.gate or a.sandbox or a.generate_only or a.audit_verdict is not None or a.dry_run):
        raise SystemExit(f"STOP: seed {a.seed} is a debug seed: use --gate (step 1 of logbook 91) or --sandbox (no claim)")
    if a.dry_run:
        return dry_run(a)
    if a.audit_verdict is not None:
        path = frozen_path(a.seed, a.worlds, a.sessions, a.questions_dir)
        if not path.exists():
            raise SystemExit("STOP: no frozen set to audit; run --generate-only --audit-sheet first")
        return audit_verdict(load_frozen(path), a.audit_verdict, a.questions_dir)
    if a.generate_only:
        logging.disable(logging.CRITICAL)
        if client is None:
            from grandnexus.llm_interface.translator_v5 import _default_client
            client = _default_client()
        frozen = generate(a, client)
        print(f"validity check V on this set: the template still gives the canonical goal for "
              f"{100 * template_share(frozen['items']):.1f}% of the questions (at most 50%)")
        if a.audit_sheet:
            audit_sheet(frozen)
        return frozen
    return run(a, client)


if __name__ == "__main__":
    main()
