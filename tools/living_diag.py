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

from living_bench import WorldV2                                                           # noqa: E402
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


def run_world(tr, world: WorldV2, level: int, seed: int) -> dict:
    para = Paraphraser(level, seed * 10 + level)
    mem = Memory()
    facts_log, questions_log, sessions_log = [], [], []
    moved_seen: set = set()
    for s, (facts, qs) in enumerate(world.sessions):
        texts = [para(f, world.meta[f], s) for f in facts]
        mem.new_session()
        names_before = {"preds": sorted(f"{p}/{n}" for p, n in mem.preds), "consts": sorted(mem.consts)}
        program = []
        if texts:
            try:
                prog = tr.translate(" ".join(texts), READ_QUERY, lexicon_block(mem, True))["parsed"]
            except Exception as e:  # noqa: BLE001
                prog = None
                program = [f"(reading failed: {type(e).__name__})"]
            if prog is not None:
                program = [str(l) + ("  [knowledge]" if k else "") for l, _sid, k in prog.facts] + \
                          [str(r) + ("  [knowledge]" if r.knowledge else "") for r in prog.rules]
                pred_names = {p for p, _n in mem.preds}
                normed = {norm(x.replace("  [knowledge]", "")) for x in program}
                for f, t in zip(facts, texts):
                    meta = world.meta[f]
                    rel = meta[1]
                    exp = expected(meta)
                    extra = {}
                    if rel == "instance_of":
                        extra["role_name_known_before"] = node(meta[2]) in pred_names
                    if rel == "lives in":
                        extra["move"] = meta[0] in moved_seen
                        moved_seen.add(meta[0])
                    facts_log.append({"session": s, "rel": rel, "surface": t, "form": para.forms.get(t), "expected": exp,
                                      "read_as_expected": norm(exp) in normed, **extra})
                mem.add_program(prog)
        sessions_log.append({"session": s, "texts": texts, "names_before": names_before, "program": program})
        for kind, q, gold in qs:
            ans, n, goal, lines = mem.decide(q, detail=True)
            questions_log.append({"session": s, "kind": kind, "question": q, "gold": gold, "answer": ans, "goal": goal, "used": lines})
    return {"facts": facts_log, "questions": questions_log, "sessions": sessions_log}


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


def main(argv=None, client=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--worlds", type=int, default=10)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.seed == 13:
        raise SystemExit("seed 13 holds the measured worlds of logbook 84-85: diagnose on other seeds")
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
        res.append(run_world(tr, world, a.level, a.seed * 1000 + w))
        print(f"  world {w + 1}/{len(worlds)} done ({len(tr.receipts)} calls so far)")
    qs = [q for r in res for q in r["questions"]]
    right = sum(q["answer"] == q["gold"] for q in qs)
    asserted = sum(q["answer"] in ("yes", "no", "contradictory") and q["answer"] != q["gold"] for q in qs)
    print(f"\nllm_lexicon at level {a.level}: {right}/{len(qs)} right ({100 * right / max(1, len(qs)):.1f}%), {asserted} asserted errors")
    summary = analyse(res)
    c = cost.from_receipts(tr.receipts, a.model)
    if c:
        print(f"\ncost: ${c['usd']:.3f} ({c['calls']} calls)")
    out = {"args": vars(a), "right": right, "n": len(qs), "asserted_errors": asserted, "summary": summary, "worlds": res, "cost": c}
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_diag_L{a.level}_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"written: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
