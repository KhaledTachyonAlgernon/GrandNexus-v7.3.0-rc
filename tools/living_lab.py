#!/usr/bin/env python
"""
Living bench, lab version (logbook 79), offline, 0 API call. Pre-registered criteria C0-C2 are printed at the end.

The bench gives no structure: each fact sentence of a world v2 (tools/living_bench.py) is read by GrandNexus's own
premise extractor, and the memories are fed with what it extracts (atoms such as is(bob,chess_player),
live(alice,in_lyon), universal rules). Only knowledge given: "live" is single-valued. Every pipeline ends in the same
reference engine (strict).
  concat            every sentence so far + the question, read by the grammar pathway
  overlap           the 6 sentences sharing most words with the question (recency on ties), same pathway
  bfs+script        trivial structured control: breadth-first search over the extracted triples ("is" questions),
                    a ten-line succession script ("live" questions: latest value, negation of the older ones)
  graph+episodic    2025 InMemoryGraphEngine (find_paths) for "is" questions, repaired EpisodicMemory for "live" ones
  semantic+episodic 2025 SemanticMemory (relations walked from the person), same split

  python tools/living_lab.py --seed 7 --worlds 40 --sessions 12
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import re
import sys
import time
import uuid
from collections import defaultdict
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from living_bench import KINDS_V2, WorldV2, words                                         # noqa: E402

PIPELINES = ("concat", "overlap", "bfs+script", "graph+episodic", "semantic+episodic")
ATOM = re.compile(r"^(not )?(\w+)\((\w+),(\w+)\)$")


def node(x: str) -> str:
    return x.lower().replace(" ", "_")


def sign_test(w: int, l: int) -> float:
    n = w + l
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(w, l) + 1)) / 2 ** n)


def expected_structure(meta) -> tuple:
    """The generator's structure of a fact, its names written as the extractor writes constants (lower case, articles
    dropped, words lemmatised the same way in statements and questions: "Tours" -> tour). Found on the debug seed 5,
    before the measurement of logbook 79: comparing with the raw names flagged 8/160 facts that only differ by this
    normalisation, which questions share (logbook 80)."""
    from grandnexus.cognition.perception.premise_extractor import term
    t = lambda x: term(x.lower().split())
    a, rel, b, pol = meta
    if rel == "instance_of":
        return ("fact", f"is({t(a)},{t(b)})")
    if rel == "lives in":
        return ("fact", f"live({t(a)},in_{t(b)})")
    return ("univ", t(a), t(b), not pol)                 # is_a / has_property: category, object, negated


def verdict(items: list, goal: str) -> str:
    """Atoms and universal rules -> the reference engine's strict verdict, grounding the rules on the individuals as
    the premise extractor does."""
    from grandnexus.nexus_logic.bridge import verdict_from_atoms
    facts = [it[1] for it in items if it[0] == "fact"]
    univs = [it for it in items if it[0] == "univ"]
    inds = []
    for a in facts + [goal]:
        m = ATOM.match(a)
        if m and m.group(3) not in inds:
            inds.append(m.group(3))
    rules = [{"if": f"is({i},{u[1]})", "then": u[3].proposition(i)} for i in inds for u in univs]
    return verdict_from_atoms(facts, rules, [goal], use_knowledge=False).answer


class Structured:
    """The three structured pipelines, fed with the same extracted items."""

    def __init__(self) -> None:
        from grandnexus.graph.graph_engine import InMemoryGraphEngine
        from grandnexus.memory import semantic as S
        from grandnexus.memory.episodic import EpisodicMemory, EpisodicMemoryConfig
        self.S = S
        self.items: list = []                                   # every extracted item, by index
        self.adj: dict = defaultdict(list)                      # trivial: node -> [(next node, item index)]
        self.live_log: list = []                                # trivial: (subject, value) in order
        self.graph = InMemoryGraphEngine()
        self.sem = S.SemanticMemory(S.SemanticMemoryConfig())
        self.epi = EpisodicMemory(EpisodicMemoryConfig(single_valued_relations={"live": "not live({subject},{value})"}))
        self.episode = None

    def new_session(self) -> None:
        if self.episode is not None:
            self.epi.close_episode(self.episode)
        self.episode = self.epi.create_episode("session").episode_id

    def _node(self, x: str) -> None:
        try:
            self.graph.get_node(x)
        except Exception:  # noqa: BLE001  (NodeNotFoundError)
            self.graph.add_node(node_id=x, label="Concept")
        if self.sem.get_concept(x) is None:
            self.sem.add_concept(self.S.Concept(concept_id=x, name=x))

    def add(self, item: tuple) -> None:
        i = len(self.items)
        self.items.append(item)
        if item[0] == "fact":
            m = ATOM.match(item[1])
            if not m:
                return
            neg, rel, a, b = m.groups()
            if rel == "live" and not neg:
                self.live_log.append((a, b))
                self.epi.add_event(self.episode, item[1], metadata={"subject": a, "relation": "live", "value": b})
                return
            src, dst = a, b
        else:
            src, dst = item[1], item[2]
        self.adj[src].append((dst, i))
        self._node(src)
        self._node(dst)
        self.graph.add_edge(src, dst, "rel", properties={"idx": i})
        self.sem.add_relation(self.S.Relation(relation_id=str(uuid.uuid4()), source_concept_id=src,
                                              relation_type=self.S.RelationType.RELATED_TO, target_concept_id=dst, properties={"idx": i}))

    # ---- "is" questions: items on a path from the person to the asked concept
    def path_trivial(self, a: str, b: str) -> list:
        parent, frontier = {a: None}, [a]
        for _ in range(3):
            nxt = []
            for x in frontier:
                for y, i in self.adj.get(x, []):
                    if y not in parent:
                        parent[y] = (x, i)
                        nxt.append(y)
            frontier = nxt
        out, cur = [], b if b in parent else None
        while cur is not None and parent[cur] is not None:
            cur, i = parent[cur]
            out.insert(0, self.items[i])
        return out

    def path_graph(self, a: str, b: str) -> list:
        try:
            paths = self.graph.find_paths(a, b, max_depth=3)
        except Exception:  # noqa: BLE001
            return []
        idx = []
        for p in paths:
            for x, y in zip(p, p[1:]):
                for nb, eid, _t in self.graph.get_node_neighbors(x):
                    if nb == y:
                        i = (getattr(self.graph.get_edge(eid), "properties", None) or {}).get("idx")
                        if i is not None and i not in idx:
                            idx.append(i)
        return [self.items[i] for i in idx]

    def path_semantic(self, a: str, b: str) -> list:
        parent, frontier = {a: None}, [a]
        for _ in range(3):
            nxt = []
            for x in frontier:
                for rel in self.sem.get_relations_by_source(x):
                    if rel.target_concept_id not in parent:
                        parent[rel.target_concept_id] = (x, rel.properties.get("idx"))
                        nxt.append(rel.target_concept_id)
            frontier = nxt
        out, cur = [], b if b in parent else None
        while cur is not None and parent[cur] is not None:
            cur, i = parent[cur]
            out.insert(0, self.items[i])
        return out

    # ---- "live" questions
    def live_trivial(self, a: str) -> list:
        vals = [v for s, v in self.live_log if s == a]
        if not vals:
            return []
        cur = vals[-1]
        return [("fact", f"live({a},{cur})")] + [("fact", f"not live({a},{v})") for v in dict.fromkeys(vals) if v != cur]

    def live_episodic(self, goal: str) -> list:
        return [("fact", e.content) for e in self.epi.retrieve_events(text=goal, max_results=4)]


def run_world(world: WorldV2, extractor, reasoner) -> tuple:
    st = Structured()
    history: list = []
    rows, fidelity = [], [0, 0]
    for s, (facts, questions) in enumerate(world.sessions):
        st.new_session()
        for f in facts:
            history.append((s, f))
            ex = extractor.extract(f)
            items = [("fact", a) for a in ex.facts] + [("univ", u["category"], u["clause"].obj, u["clause"]) for u in ex.universals]
            exp = expected_structure(world.meta[f])
            got = [("fact", it[1]) if it[0] == "fact" else ("univ", it[1], it[2], it[3].negated) for it in items]
            fidelity[0] += got == [exp]
            fidelity[1] += 1
            for it in items:
                st.add(it)
        for kind, q, gold in questions:
            goals = extractor.extract(q).goals
            goal = goals[0] if goals else ""
            m = ATOM.match(goal)
            ctx_text = {"concat": [f for _, f in history],
                        "overlap": [f for _, _, f in sorted((-len(words(f) & words(q)), -t, f) for t, f in history)[:6]]}
            for name, c in ctx_text.items():
                r = reasoner.answer(" ".join(c + [q]), mode="grammar")
                rows.append({"kind": kind, "gold": gold, "pipeline": name, "answer": r.get("answer"), "facts": len(c)})
            for name in ("bfs+script", "graph+episodic", "semantic+episodic"):
                if not m:
                    items, ans = [], "unknown"
                else:
                    _neg, rel, a, b = m.groups()
                    if rel == "live":
                        items = st.live_trivial(a) if name == "bfs+script" else st.live_episodic(goal)
                    else:
                        items = {"bfs+script": st.path_trivial, "graph+episodic": st.path_graph,
                                 "semantic+episodic": st.path_semantic}[name](a, b)
                    ans = verdict(items, goal)
                rows.append({"kind": kind, "gold": gold, "pipeline": name, "answer": ans, "facts": len(items)})
    return rows, fidelity


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--worlds", type=int, default=40)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    from grandnexus.cognition.perception.premise_extractor import PremiseExtractor
    from grandnexus.cognition.reasoning.text_reasoner import TextReasoner
    extractor, reasoner = PremiseExtractor(), TextReasoner()
    rows, fid = [], [0, 0]
    for w in range(a.worlds):
        r, f = run_world(WorldV2(a.seed * 1000 + w, a.sessions, 5, 3), extractor, reasoner)
        rows += r
        fid[0] += f[0]
        fid[1] += f[1]
    n = len(rows) // len(PIPELINES)
    print(f"world v2, seed {a.seed}: {a.worlds} worlds x {a.sessions} sessions, {n} questions")
    c0 = fid[0] / max(1, fid[1])
    print(f"C0 extraction: {fid[0]}/{fid[1]} facts extracted with the generator's structure ({100 * c0:.2f}%) -> {'PASS' if c0 >= 0.99 else 'FAIL'}")
    summ = {}
    print(f"\n{'pipeline':18} {'right':>7} " + " ".join(f"{k:>10}" for k in KINDS_V2) + f" {'asserted err':>13} {'facts/q':>8}")
    for p in PIPELINES:
        rs = [r for r in rows if r["pipeline"] == p]
        right = sum(r["answer"] == r["gold"] for r in rs)
        per = {k: (sum(r["answer"] == r["gold"] for r in rs if r["kind"] == k), sum(r["kind"] == k for r in rs)) for k in KINDS_V2}
        asserted = sum(r["answer"] in ("yes", "no", "contradictory") and r["answer"] != r["gold"] for r in rs)
        facts = sum(r["facts"] for r in rs) / max(1, len(rs))
        summ[p] = {"right": right, "n": len(rs), "pct": round(100 * right / max(1, len(rs)), 2), "asserted_errors": asserted,
                   "facts_per_question": round(facts, 2), "per_kind": per}
        print(f"{p:18} {summ[p]['pct']:6.1f}% " + " ".join(f"{c:>4}/{k:<5}" for c, k in per.values()) + f" {asserted:>13} {facts:>8.2f}")
    by = {p: [r for r in rows if r["pipeline"] == p] for p in PIPELINES}
    ok = lambda r: r["answer"] == r["gold"]
    print()
    crit = {"C0": c0 >= 0.99}
    for p in ("graph+episodic", "semantic+episodic"):
        tests = {}
        for c in ("concat", "overlap"):
            w = sum(ok(x) and not ok(y) for x, y in zip(by[p], by[c]))
            l = sum(ok(y) and not ok(x) for x, y in zip(by[p], by[c]))
            tests[c] = (w, l, sign_test(w, l))
            print(f"paired {p:18} vs {c:8}: only {p} right {w:>3} | only {c} right {l:>3} | sign test p = {sign_test(w, l):.2g}")
        c1 = (summ[p]["pct"] >= 95 and summ[p]["asserted_errors"] == 0 and summ[p]["facts_per_question"] <= 0.2 * summ["concat"]["facts_per_question"]
              and all(t[0] > t[1] and t[2] < 0.05 for t in tests.values()))
        c2 = summ[p]["pct"] >= summ["bfs+script"]["pct"] - 1 and summ[p]["asserted_errors"] <= summ["bfs+script"]["asserted_errors"]
        crit[f"C1 {p}"], crit[f"C2 {p}"] = c1, c2
        summ[p]["paired"] = {c: {"only_this_right": t[0], "only_control_right": t[1], "p": t[2]} for c, t in tests.items()}
    print()
    for k, v in crit.items():
        print(f"{k:24} {'PASS' if v else 'FAIL'}")
    out = {"args": vars(a), "fidelity": {"exact": fid[0], "facts": fid[1]}, "summary": summ, "criteria": crit}
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_lab_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"\nwritten: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
