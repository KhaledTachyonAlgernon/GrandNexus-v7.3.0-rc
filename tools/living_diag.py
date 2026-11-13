#!/usr/bin/env python
"""
Diagnosis of the level-1 shortfall of phase C (logbook 85-86), sandbox, on debug seeds only (never 13).

Phase C kept only the tables, so its misses cannot be traced. This tool re-runs the lexicon pipeline of phase C at one
level on debug worlds and keeps everything: for each session, the names offered to the translator, the program it
wrote; for each fact, whether the translator wrote the ontology's statement for it, with the paraphrase form used and,
for a role, whether the role's name already existed in memory; for each question, the goal and the statements used.
It then sorts the failed questions by cause. The worlds are synthetic: printing their sentences reveals no test item.
Hypotheses under test (logbook 85): (1) a role first met as an activity ("Carol plays music") gets its own name before
any role noun exists; (2) a first residence phrased "has a flat in" is not read as lives_in, so the move closes nothing.

  python tools/living_diag.py --seed 11 --worlds 10 --level 1 --dry-run

Repairs of logbook 90 (the gate of logbook 88-89 ignored the 50 readings that failed with the API unavailable):
- transient API errors are retried with growing waits by the translator itself (translator_v5.Translator._create);
- a reading that still fails is logged with its facts, each counted as NOT read (reading_failed: true), so every
  rate over facts, the gate included, has the bench's facts as denominator, whatever the API did;
- whether a residence fact is a move comes from the world, not from the readings that happened to succeed (before,
  a move whose first residence was in a failed reading was counted as a first residence);
- the number of failed readings, the facts they held and the retries are printed and written, next to the gate.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import re
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from living_bench import MEASURED_SEEDS, WorldV2                                           # noqa: E402
from living_language import Paraphraser                                                    # noqa: E402
from living_llm import READ_QUERY, Memory, lexicon_block, node                             # noqa: E402

FORM_NAMES = {"instance_of": {1: ["works as a <role>", "<activity verb>"]},
              "lives in": {1: ["first: resides in / moved: moved to", "first: has a flat in / moved: now lives in"]}}


def norm(stmt: str) -> str:
    s = re.sub(r"\b[A-Z][A-Za-z0-9_]*\b", "V", stmt.strip().rstrip("."))
    return re.sub(r"\s+", " ", s.replace(" ,", ","))


def expected(meta) -> str:
    a, rel, b, pol = meta
    if rel == "instance_of":
        return f"{node(b)}({node(a)})"
    if rel == "is_a":
        return f"{node(a)}(V) => {node(b)}(V)"
    if rel == "has_property":
        return f"{node(a)}(V) => {'' if pol else 'not '}{b}(V)"
    return f"lives_in({node(a)}, {node(b)})"


def session_facts(world: WorldV2, s: int, facts: list, texts: list, program: list, failed: bool, moved_seen: set,
                  pred_names: set, para) -> list:
    """Every fact the bench gave in session s, with whether the program wrote the ontology's statement for it; the facts
    of a failed reading count as not read; a residence is a move when the world gave that person a residence before."""
    normed = {norm(x.replace("  [knowledge]", "")) for x in program} if not failed else set()
    rows = []
    for i, (f, t) in enumerate(zip(facts, texts)):
        meta = world.meta[f]
        rel = meta[1]
        exp = expected(meta)
        extra = {}
        if rel == "instance_of":
            extra["role_name_known_before"] = node(meta[2]) in pred_names
        if rel == "lives in":
            extra["move"] = meta[0] in moved_seen          # from the world, whatever the readings did
            moved_seen.add(meta[0])
            # reported, not used by the gate: the same person moves again later in this very session, so a reader that
            # writes only the current city (one city at a time) leaves this one unwritten without misreading it
            extra["superseded_in_session"] = any(world.meta[g][1] == "lives in" and world.meta[g][0] == meta[0]
                                                 for g in facts[i + 1:])
        rows.append({"session": s, "rel": rel, "surface": t, "form": para.forms.get(t), "expected": exp,
                     "read_as_expected": (not failed) and norm(exp) in normed, "reading_failed": failed, **extra})
    return rows


def gate_of(facts: list) -> dict:
    """The gate of logbook 88 over every fact of the bench (logbook 90)."""
    first = [f for f in facts if f["rel"] == "lives in" and not f.get("move")]
    roles = [f for f in facts if f["rel"] == "instance_of"]
    r1 = sum(f["read_as_expected"] for f in first) / max(1, len(first))
    r2 = sum(f["read_as_expected"] for f in roles) / max(1, len(roles))
    return {"first_residences": round(r1, 4), "role_facts": round(r2, 4), "n_first_residences": len(first),
            "n_role_facts": len(roles), "pass": r1 >= 0.95 and r2 >= 0.95}


def run_world(tr, world: WorldV2, level: int, seed: int, version: int = 1, ontology: int = 1) -> dict:
    para = Paraphraser(level, seed * 10 + level, version)
    mem = Memory()
    facts_log, questions_log, sessions_log = [], [], []
    moved_seen: set = set()
    failed_readings = 0
    for s, (facts, qs) in enumerate(world.sessions):
        texts = [para(f, world.meta[f], s) for f in facts]
        mem.new_session()
        names_before = {"preds": sorted(f"{p}/{n}" for p, n in mem.preds), "consts": sorted(mem.consts)}
        program, failed = [], False
        if texts:
            try:
                prog = tr.translate(" ".join(texts), READ_QUERY, lexicon_block(mem, True, ontology))["parsed"]
            except Exception as e:  # noqa: BLE001  (an API error that outlived the retries)
                prog, failed = None, True
                failed_readings += 1
                program = [f"(reading failed: {type(e).__name__})"]
            if prog is not None:
                program = [str(l) + ("  [knowledge]" if k else "") for l, _sid, k in prog.facts] + \
                          [str(r) + ("  [knowledge]" if r.knowledge else "") for r in prog.rules]
            facts_log += session_facts(world, s, facts, texts, program, failed, moved_seen,       # every fact, read or not
                                       {p for p, _n in mem.preds}, para)
            if prog is not None:
                mem.add_program(prog)
        sessions_log.append({"session": s, "texts": texts, "names_before": names_before, "program": program,
                             "reading_failed": failed})
        for kind, q, gold in qs:
            ans, n, goal, lines = mem.decide(q, detail=True)
            questions_log.append({"session": s, "kind": kind, "question": q, "gold": gold, "answer": ans, "goal": goal, "used": lines})
    return {"facts": facts_log, "questions": questions_log, "sessions": sessions_log, "failed_readings": failed_readings}


def analyse(worlds: list) -> dict:
    facts = [f for w in worlds for f in w["facts"]]
    qs = [q for w in worlds for q in w["questions"]]
    out = {"reading": {}, "roles": {}, "residence": {}, "failed": Counter()}
    print("\nREADING: facts written as the ontology's statement, by kind of fact and paraphrase form")
    by = defaultdict(lambda: [0, 0])
    for f in facts:
        k = (f["rel"], f["form"], f.get("move"))
        by[k][0] += f["read_as_expected"]
        by[k][1] += 1
    for (rel, form, move), (ok, n) in sorted(by.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), str(kv[0][2]))):
        label = FORM_NAMES.get(rel, {}).get(1, [None, None])[form] if form is not None and rel in FORM_NAMES else f"form {form}"
        if rel == "lives in":
            label += " (move)" if move else " (first residence)"
        print(f"   {rel:13} {label:46} {ok:>3}/{n:<3}")
        out["reading"][f"{rel}|{form}|{move}"] = [ok, n]
    roles = [f for f in facts if f["rel"] == "instance_of"]
    for known in (True, False):
        sub = [f for f in roles if f["role_name_known_before"] == known]
        out["roles"][str(known)] = [sum(f["read_as_expected"] for f in sub), len(sub)]
        print(f"   role facts, role name {'already in memory' if known else 'not yet in memory'}: "
              f"{sum(f['read_as_expected'] for f in sub)}/{len(sub)} read as the role predicate")
    print("\nFAILED QUESTIONS by kind (answer given):")
    for q in qs:
        if q["answer"] != q["gold"]:
            out["failed"][f"{q['kind']} -> {q['answer']}"] += 1
    for k, v in out["failed"].most_common():
        print(f"   {k:28} {v}")
    print("\nEXAMPLES (synthetic worlds):")
    shown = Counter()
    for w in worlds:
        for q in w["questions"]:
            if q["answer"] == q["gold"] or shown[q["kind"]] >= 3:
                continue
            shown[q["kind"]] += 1
            person = q["question"].split()[1]
            related = [f for f in w["facts"] if f["surface"].startswith(person) or person in f["surface"]][:6]
            print(f"   [{q['kind']}] {q['question']} gold {q['gold']} -> {q['answer']} | goal {q['goal']} | used {q['used']}")
            for f in related:
                print(f"        s{f['session']} {f['surface']!r} expected {f['expected']} -> {'ok' if f['read_as_expected'] else 'NOT read as expected'}")
            for sess in w["sessions"]:
                for f in related:
                    if f["session"] == sess["session"] and not f["read_as_expected"]:
                        print(f"        s{sess['session']} program: {sess['program']}")
                        break
    return out


def regate(path: str) -> dict:
    """Recompute the gate of an archived run of this tool from the programs it recorded (0 API call): the worlds and
    their paraphrases are regenerated from the recorded arguments (and checked against the recorded texts), the facts
    of failed readings count as not read, and moves come from the world (logbook 90)."""
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    a = d["args"]
    if a["seed"] in MEASURED_SEEDS:
        raise SystemExit(f"seed {a['seed']} holds measured worlds: never read them for a diagnosis")
    facts, failed_readings, readings = [], 0, 0
    for w, rec in enumerate(d["worlds"]):
        world = WorldV2(a["seed"] * 1000 + w, a["sessions"], 5, 3)
        para = Paraphraser(a["level"], (a["seed"] * 1000 + w) * 10 + a["level"], a.get("paraphraser", 1))
        moved_seen: set = set()
        for s, (fs, _qs) in enumerate(world.sessions):
            texts = [para(f, world.meta[f], s) for f in fs]
            sess = rec["sessions"][s]
            if texts != sess["texts"]:
                raise SystemExit(f"world {w} session {s}: regenerated texts differ from the archive (version mismatch)")
            if not texts:
                continue
            readings += 1
            failed = bool(sess["program"]) and str(sess["program"][0]).startswith("(reading failed")
            failed_readings += failed
            facts += session_facts(world, s, fs, texts, sess["program"], failed, moved_seen, set(), para)
    g = {**gate_of(facts), "failed_readings": failed_readings, "readings": readings,
         "facts_in_failed_readings": sum(f["reading_failed"] for f in facts)}
    print(f"archived gate:   {d.get('gate')}")
    print(f"repaired gate:   first residences {100 * g['first_residences']:.1f}% of {g['n_first_residences']}, role facts "
          f"{100 * g['role_facts']:.1f}% of {g['n_role_facts']} -> {'PASS' if g['pass'] else 'FAIL'} "
          f"({failed_readings}/{readings} readings failed, {g['facts_in_failed_readings']} facts counted as not read)")
    ok = [f for f in facts if not f["reading_failed"]]
    g_ok = gate_of(ok)
    miss = [f for f in ok if f["rel"] == "lives in" and not f["move"] and not f["read_as_expected"]]
    g_ok["first_residence_misses"] = len(miss)
    g_ok["of_which_superseded_in_session"] = sum(f["superseded_in_session"] for f in miss)
    print(f"successful readings only, moves from the world: first residences {100 * g_ok['first_residences']:.1f}% of "
          f"{g_ok['n_first_residences']}, role facts {100 * g_ok['role_facts']:.1f}% of {g_ok['n_role_facts']}; "
          f"first-residence misses {len(miss)}, of which superseded by a move in the same session "
          f"{g_ok['of_which_superseded_in_session']} (reported, not used by the gate)")
    return {"repaired": g, "successful_readings_only": g_ok, "archived": d.get("gate")}


def main(argv=None, client=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--worlds", type=int, default=10)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--paraphraser", type=int, default=1, help="1: logbook 86-87; 2: logbook 88")
    ap.add_argument("--ontology", type=int, default=1, help="1: logbook 86-87; 2: logbook 88")
    ap.add_argument("--gate", action="store_true", help="evaluate the gate of logbook 88 (first residences and role facts >= 95%%)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--regate", metavar="RESULT_JSON", help="recompute the gate of an archived run of this tool, 0 API call")
    a = ap.parse_args(argv)
    if a.regate:
        r = regate(a.regate)
        if not a.no_write:
            d = ROOT / "tests_lab" / "resultats" / "living"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"living_regate_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
            path.write_text(json.dumps({"source": a.regate, **r}, indent=1), encoding="utf-8")
            print(f"written: {path.relative_to(ROOT)}")
        return r
    if a.seed in MEASURED_SEEDS:
        raise SystemExit(f"seed {a.seed} holds measured worlds (seeds {MEASURED_SEEDS}): diagnose on other seeds")
    worlds = [WorldV2(a.seed * 1000 + w, a.sessions, 5, 3) for w in range(a.worlds)]
    n_read = sum(1 for w in worlds for f, _ in w.sessions if f)
    print(f"seed {a.seed}, {a.worlds} worlds, level {a.level}: {n_read} readings with the lexicon (+ corrective rounds, about 15%); "
          f"estimated ${n_read * 1.15 * 0.0034:.2f} at the standard rate with the cache; no other call")
    if a.dry_run:
        return {"readings": n_read}
    logging.disable(logging.CRITICAL)
    from grandnexus.llm_interface.translator_v5 import Translator
    import cost
    tr = Translator(client=client, model=a.model) if client is not None else Translator(model=a.model)
    res = []
    for w, world in enumerate(worlds):
        res.append(run_world(tr, world, a.level, a.seed * 1000 + w, a.paraphraser, a.ontology))
        print(f"  world {w + 1}/{len(worlds)} done ({len(tr.receipts)} calls so far)")
    qs = [q for r in res for q in r["questions"]]
    right = sum(q["answer"] == q["gold"] for q in qs)
    asserted = sum(q["answer"] in ("yes", "no", "contradictory") and q["answer"] != q["gold"] for q in qs)
    print(f"\nllm_lexicon at level {a.level}: {right}/{len(qs)} right ({100 * right / max(1, len(qs)):.1f}%), {asserted} asserted errors")
    summary = analyse(res)
    c = cost.from_receipts(tr.receipts, a.model)
    if c:
        print(f"\ncost: ${c['usd']:.3f} ({c['calls']} calls)")
    all_facts = [f for r in res for f in r["facts"]]
    failed = {"readings": sum(r["failed_readings"] for r in res), "readings_total": n_read,
              "facts_in_failed_readings": sum(f["reading_failed"] for f in all_facts),
              "retries": len(tr.retry_log), "retried_errors": dict(Counter(x["error"] for x in tr.retry_log))}
    print(f"API: {failed['readings']}/{n_read} readings failed after the retries ({failed['facts_in_failed_readings']} facts, "
          f"counted as not read); {failed['retries']} transient errors retried {failed['retried_errors'] or ''}")
    out = {"args": vars(a), "right": right, "n": len(qs), "asserted_errors": asserted, "summary": summary, "worlds": res,
           "cost": c, "failed": failed}
    if a.gate:
        out["gate"] = {**gate_of(all_facts), "failed_readings": failed["readings"]}
        g = out["gate"]
        print(f"\nGATE (logbook 88, counted as repaired in logbook 90: every fact of the bench, failed readings as not read): "
              f"first residences read as lives_in {100 * g['first_residences']:.1f}% of {g['n_first_residences']}, role facts "
              f"read as the role predicate {100 * g['role_facts']:.1f}% of {g['n_role_facts']} (both >= 95%) -> "
              f"{'PASS' if g['pass'] else 'FAIL'}"
              + (f"  [{failed['readings']} failed readings inside]" if failed["readings"] else ""))
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_diag_L{a.level}_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"written: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
