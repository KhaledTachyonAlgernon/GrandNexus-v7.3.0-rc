#!/usr/bin/env python
"""
"The real language", phase C (logbook 84): the lab version of phase B, criteria written before measuring.

Worlds v2 never used (--seed 13), facts paraphrased at levels 1, 2 (criteria) and 3 (exploratory), questions canonical.
Pipelines (reference engine, strict):
  grammar            the grammar pathway feeds graph+episodic (floor, no call)
  llm_lexicon        the translator reads each session with the shared lexicon; 2025 graph engine + repaired episodic memory
  llm_lexicon_bfs    the same readings, trivial control (reported)
  llm_nolexicon      each session read without lexicon, same memories
  llm_concat_onto    the translator reads every fact so far and the question in one go, WITH the ontology conventions,
                     on the questions of the first --concat-worlds worlds
API work is split into jobs run through the Message Batches API (tools/batch_runner.py, --batch): one job per
(level, world) for the lexicon readings (sequential: each reading uses the names of the previous ones), one per
(level, world, session) for the readings without lexicon, one per question for llm_concat_onto. Everything else is
offline. Re-running the same command resumes. A reading that fails after its corrective round counts as empty.
Criteria (levels 1 and 2 separately): C1 llm_lexicon >= 95% right and 0 asserted error; C2 llm_lexicon beats
llm_nolexicon, paired sign test p < 0.05; C3 on the concat subset llm_lexicon >= llm_concat_onto - 2 points, with
<= 20% of its facts per question and no more asserted errors.

  python tools/living_lab_language.py --seed 13 --worlds 10 --levels 1,2,3 --concat-worlds 4 --batch --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
import sys
import time
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from living_bench import KINDS_V2, WorldV2                                                 # noqa: E402
from living_language import Paraphraser                                                    # noqa: E402
from living_llm import ONTOLOGY, READ_QUERY, Memory, lexicon_block                         # noqa: E402

PIPELINES = ("grammar", "llm_lexicon", "llm_lexicon_bfs", "llm_nolexicon", "llm_concat_onto")
CRITERION_LEVELS = (1, 2)


def sign_test(w: int, l: int) -> float:
    n = w + l
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(w, l) + 1)) / 2 ** n)


def surfaces(world: WorldV2, level: int, seed: int) -> list:
    """[(session texts, questions)] for one world at one level (deterministic)."""
    para = Paraphraser(level, seed * 10 + level)
    return [([para(f, world.meta[f], s) for f in facts], qs) for s, (facts, qs) in enumerate(world.sessions)]


def reading(tr, text: str, block: str):
    """One reading -> parsed program, or None when the call failed."""
    try:
        return tr.translate(text, READ_QUERY, block)["parsed"]
    except Exception:  # noqa: BLE001  (an errored batch request, an API error)
        return None


def lexicon_chain(tr, sess: list) -> list:
    """Job: the lexicon readings of one world, session after session; returns the answers to every question at the
    session it is asked, for llm_lexicon and its trivial control, plus the number of failed readings."""
    mem, out, failed = Memory(), [], 0
    for texts, qs in sess:
        mem.new_session()
        if texts:
            prog = reading(tr, " ".join(texts), lexicon_block(mem, True))
            if prog is None:
                failed += 1
            else:
                mem.add_program(prog)
        for kind, q, gold in qs:
            out.append({"q": q, "kind": kind, "gold": gold, "llm_lexicon": mem.decide(q), "llm_lexicon_bfs": mem.decide(q, trivial=True)})
    return {"answers": out, "failed": failed}


def run(a, client=None) -> dict:
    logging.disable(logging.CRITICAL)
    import living_lab as LAB
    from grandnexus.cognition.perception.premise_extractor import PremiseExtractor
    from grandnexus.llm_interface.translator_v5 import Translator, _default_client
    import cost
    levels = [int(x) for x in a.levels.split(",")]
    worlds = [WorldV2(a.seed * 1000 + w, a.sessions, 5, 3) for w in range(a.worlds)]
    surf = {(L, w): surfaces(worlds[w], L, a.seed * 1000 + w) for L in levels for w in range(a.worlds)}
    session = None
    if a.batch:
        from batch_runner import BatchSession
        key = hashlib.sha256(json.dumps([a.seed, a.worlds, a.sessions, a.levels, a.concat_worlds, a.model]).encode()).hexdigest()[:10]
        out_dir = pathlib.Path(a.state_dir) if a.state_dir else ROOT / "tests_lab" / "resultats" / "living"
        session = BatchSession(client or _default_client(), out_dir / f"batch_state_phaseC_{key}.json")
        tr = Translator(client=session, model=a.model)
    else:
        tr = Translator(client=client, model=a.model) if client is not None else Translator(model=a.model)
    jobs = {}
    for (L, w), sess in surf.items():
        jobs[f"lex|{L}|{w}"] = (lambda sess=sess: lexicon_chain(tr, sess))
        for s, (texts, _qs) in enumerate(sess):
            if texts:
                jobs[f"nolex|{L}|{w}|{s}"] = (lambda texts=texts: reading(tr, " ".join(texts), ""))
        if w < a.concat_worlds:
            seen = []
            for s, (texts, qs) in enumerate(sess):
                seen = seen + texts
                for i, (_k, q, _g) in enumerate(qs):
                    jobs[f"concat|{L}|{w}|{s}|{i}"] = (lambda text=" ".join(seen), q=q: tr.answer(text, q, ONTOLOGY + "\n\n"))
    print(f"{len(jobs)} API jobs ({sum(k.startswith('lex|') for k in jobs)} lexicon chains, {sum(k.startswith('nolex|') for k in jobs)} readings "
          f"without lexicon, {sum(k.startswith('concat|') for k in jobs)} concat questions)")
    res = session.run(jobs) if session is not None else {k: f() for k, f in jobs.items()}
    # ---- offline: grammar pipeline, nolex memories, assembly
    extractor = PremiseExtractor()
    rows, failed = [], {"lexicon": 0, "nolexicon": 0, "concat": 0}
    for (L, w), sess in surf.items():
        lex = res[f"lex|{L}|{w}"]
        if isinstance(lex, Exception):
            raise lex
        failed["lexicon"] += lex["failed"]
        st, mem_nl = LAB.Structured(), Memory()
        qi = 0
        for s, (texts, qs) in enumerate(sess):
            st.new_session()
            mem_nl.new_session()
            for t in texts:
                ex = extractor.extract(t)
                for it in [("fact", x) for x in ex.facts] + [("univ", u["category"], u["clause"].obj, u["clause"]) for u in ex.universals]:
                    st.add(it)
            if texts:
                prog = res[f"nolex|{L}|{w}|{s}"]
                if prog is None or isinstance(prog, Exception):
                    failed["nolexicon"] += 1
                else:
                    mem_nl.add_program(prog)
            for i, (kind, q, gold) in enumerate(qs):
                ans = {}
                goals = extractor.extract(q).goals
                m = LAB.ATOM.match(goals[0] if goals else "")
                if m:
                    _n, rel, x, y = m.groups()
                    items = st.live_episodic(goals[0]) if rel == "live" else st.path_graph(x, y)
                    ans["grammar"] = (LAB.verdict(items, goals[0]), len(items))
                else:
                    ans["grammar"] = ("unknown", 0)
                rec = lex["answers"][qi]
                assert rec["q"] == q
                qi += 1
                ans["llm_lexicon"], ans["llm_lexicon_bfs"] = tuple(rec["llm_lexicon"]), tuple(rec["llm_lexicon_bfs"])
                ans["llm_nolexicon"] = mem_nl.decide(q)
                ck = f"concat|{L}|{w}|{s}|{i}"
                if ck in res:
                    r = res[ck]
                    if isinstance(r, Exception):
                        failed["concat"] += 1
                        ans["llm_concat_onto"] = ("unknown", sum(len(t) for t, _ in sess[: s + 1]))
                    else:
                        ans["llm_concat_onto"] = (r["verdict_strict"], sum(len(t) for t, _ in sess[: s + 1]))
                for p, (verdict, n) in ans.items():
                    rows.append({"level": L, "world": w, "kind": kind, "gold": gold, "pipeline": p, "answer": verdict, "facts": n,
                                 "key": f"{L}|{w}|{s}|{i}"})
    out = {"args": vars(a), "failed_calls": failed, "levels": {}, "criteria": {}}
    ok = lambda r: r["answer"] == r["gold"]
    asserted = lambda rs: sum(r["answer"] in ("yes", "no", "contradictory") and r["answer"] != r["gold"] for r in rs)
    for L in levels:
        print(f"\n=== level {L}{'' if L in CRITERION_LEVELS else ' (exploratory)'}")
        print(f"{'pipeline':16} {'right':>7} " + " ".join(f"{k:>10}" for k in KINDS_V2) + f" {'asserted err':>13} {'facts/q':>8}")
        by = {p: [r for r in rows if r["level"] == L and r["pipeline"] == p] for p in PIPELINES}
        out["levels"][L] = {}
        for p, rs in by.items():
            if not rs:
                continue
            per = {k: (sum(ok(r) for r in rs if r["kind"] == k), sum(r["kind"] == k for r in rs)) for k in KINDS_V2}
            st_ = {"n": len(rs), "pct": round(100 * sum(map(ok, rs)) / len(rs), 2), "asserted_errors": asserted(rs),
                   "facts_per_question": round(sum(r["facts"] for r in rs) / len(rs), 2), "per_kind": per}
            out["levels"][L][p] = st_
            print(f"{p:16} {st_['pct']:6.1f}% " + " ".join(f"{c:>4}/{k:<5}" for c, k in per.values()) + f" {st_['asserted_errors']:>13} {st_['facts_per_question']:>8.2f}")
        if L not in CRITERION_LEVELS:
            continue
        lexr, nolr = by["llm_lexicon"], by["llm_nolexicon"]
        w_ = sum(ok(x) and not ok(y) for x, y in zip(lexr, nolr))
        l_ = sum(ok(y) and not ok(x) for x, y in zip(lexr, nolr))
        c1 = out["levels"][L]["llm_lexicon"]["pct"] >= 95 and out["levels"][L]["llm_lexicon"]["asserted_errors"] == 0
        c2 = w_ > l_ and sign_test(w_, l_) < 0.05
        sub = {r["key"] for r in by.get("llm_concat_onto", [])}
        lex_sub = [r for r in lexr if r["key"] in sub]
        con = by.get("llm_concat_onto", [])
        if con:
            pl, pc = 100 * sum(map(ok, lex_sub)) / len(lex_sub), 100 * sum(map(ok, con)) / len(con)
            fl, fc = sum(r["facts"] for r in lex_sub) / len(lex_sub), sum(r["facts"] for r in con) / len(con)
            c3 = pl >= pc - 2 and fl <= 0.2 * fc and asserted(lex_sub) <= asserted(con)
            c3_detail = f"subset {len(con)} questions: llm_lexicon {pl:.1f}% / {fl:.2f} facts / {asserted(lex_sub)} asserted; llm_concat_onto {pc:.1f}% / {fc:.2f} facts / {asserted(con)} asserted"
        else:
            c3, c3_detail = False, "no concat subset"
        out["criteria"][L] = {"C1": c1, "C2": c2, "C2_paired": [w_, l_, sign_test(w_, l_)], "C3": c3, "C3_detail": c3_detail}
        print(f"paired llm_lexicon vs llm_nolexicon: only lexicon right {w_} | only no-lexicon right {l_} | sign test p = {sign_test(w_, l_):.2g}")
        print(f"C3 {c3_detail}")
        for c in ("C1", "C2", "C3"):
            print(f"level {L} {c}  {'PASS' if out['criteria'][L][c] else 'FAIL'}")
    print(f"\nfailed calls (counted as empty readings / unknown): {failed}")
    u = session.usage() if session is not None else None
    c = cost.cost_usd(u, a.model) if u else cost.from_receipts(tr.receipts, a.model)
    if c:
        out["cost"] = c
        print(f"cost: ${c['usd']:.3f} ({c['calls']} calls{', Batch API' if session is not None else ''}; without the prompt cache ${c['usd_without_cache']:.3f})")
    if session is not None:
        out["batches"] = session.batches_created
        session.finish()
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_lab_language_C_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"written: {path.relative_to(ROOT)}")
    return out


def main(argv=None, client=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--worlds", type=int, default=10)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--levels", default="1,2,3")
    ap.add_argument("--concat-worlds", type=int, default=4)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--state-dir", help="where the batch state is kept (on Colab: a Drive folder, so that a reset runtime resumes)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        levels = [int(x) for x in a.levels.split(",")]
        worlds = [WorldV2(a.seed * 1000 + w, a.sessions, 5, 3) for w in range(a.worlds)]
        n_read = sum(1 for w in worlds for f, _ in w.sessions if f)
        n_concat = sum(len(q) for w in worlds[: a.concat_worlds] for _, q in w.sessions)
        calls = len(levels) * (2 * n_read + n_concat)
        rate = 0.0034 * (0.5 if a.batch else 1.0)                     # phase B: $0.681 for 200 calls with the cache
        print(f"levels {levels}, {a.worlds} worlds: {n_read} sessions x 2 lexicon modes, {n_concat} concat questions per level "
              f"-> about {calls} calls (+ corrective rounds, about 15%); estimated ${calls * 1.15 * rate:.2f}"
              + (" with the Batch API; the lexicon chains need about 12-24 successive batches (1.5-2.5 h)" if a.batch else ""))
        return {"calls": calls}
    return run(a, client)


if __name__ == "__main__":
    main()
