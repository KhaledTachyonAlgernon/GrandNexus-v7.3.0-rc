#!/usr/bin/env python
"""
Living bench, phase B of "the real language" (logbook 82), sandbox: the anchored LLM translator reads the paraphrased
facts of tools/living_language.py, session by session, and the structured memory is fed with its program.

The crux (logbook 81): facts are read in different sessions, apart from the questions, so the names the reader gives
must stay the same from one reading to the next. Shared lexicon: before each reading, the memory gives the translator
the conventions of its ontology and the names already in memory, to reuse when the text says the same thing in other
words. The only knowledge given, as in the lab version: lives_in(person, city) holds one city at a time.
Questions stay canonical and are mapped to the ontology's names without a call:
  "Is Bob a chess player?" -> chess_player(bob)    "Is Bob calm?" -> calm(bob)    "Does Alice live in Paris?" -> lives_in(alice, paris)
Pipelines (all end in the reference engine, strict):
  grammar          the grammar pathway feeds graph+episodic (phase A, no call)
  llm_lexicon      the translator with the shared lexicon feeds graph+episodic (2025 graph engine + repaired episodic memory)
  llm_lexicon_bfs  the same readings, trivial control: breadth-first search + succession script
  llm_nolexicon    the translator without lexicon feeds graph+episodic
  llm_concat       the translator reads every fact so far and the question in one go (FOLIO-like), on --concat-worlds worlds
Calls: one reading per session and per lexicon mode (+ corrective rounds), one per question for llm_concat.
--dry-run prints the calls and an estimated cost without any call. Sandbox: no criteria, no claim.

  python tools/living_llm.py --seed 11 --worlds 3 --sessions 12 --levels 1,2 --concat-worlds 1 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import re
import sys
import time
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from living_bench import KINDS_V2, WorldV2                                                 # noqa: E402
from living_language import Paraphraser                                                    # noqa: E402

PIPELINES = ("grammar", "llm_lexicon", "llm_lexicon_bfs", "llm_nolexicon", "llm_concat")
READ_QUERY = "(none: write the statements of the text only, no question line)"
ONTOLOGY = """ONTOLOGY OF THE MEMORY YOU WRITE INTO (follow it; it is shared by every reading):
- People, places and things are lowercase constants (bob, alice, lyon).
- A role, a class or a property is a unary predicate named by its singular noun or its adjective, lowercase with
  underscores: chess_player(bob). thinker(bob). calm(bob). A general statement about a role or class is a rule:
  chess_player(V) => thinker(V).   chess_player(V) => not calm(V).
- Residence is lives_in(person, city), and a person lives in one city at a time: whatever words the text uses for
  living somewhere or moving there, write lives_in(person, city).
- Prefer a name already in memory when the text says the same thing in other words (an activity and the role of the
  people who do it, a plural, a synonym); create a new name only for something new."""
ONTOLOGY_V1 = ONTOLOGY
ONTOLOGY_V2 = ONTOLOGY_V1 + """
- A person described by what they do belongs to the role named by the noun for the people who do it: someone who sings
  is a singer(..), someone who runs marathons is a marathon_runner(..). A broader category is not that role: a singer
  is not written performer(..) unless the text says performer."""
ONTOLOGIES = {1: ONTOLOGY_V1, 2: ONTOLOGY_V2}


def node(x: str) -> str:
    return x.lower().replace(" ", "_")


def goal_of(question: str) -> tuple | None:
    """Canonical question -> (goal literal, start constant, end name)."""
    m = re.match(r"Does (\w+) live in (\w+)\?$", question)
    if m:
        p, c = node(m.group(1)), node(m.group(2))
        return f"lives_in({p}, {c})", p, "lives_in"
    m = re.match(r"Is (\w+) (?:an? )?(.+)\?$", question)
    if m:
        p, x = node(m.group(1)), node(m.group(2))
        return f"{x}({p})", p, x
    return None


def lexicon_block(mem: "Memory", with_lexicon: bool, ontology: int = 1) -> str:
    """ontology 1: logbook 82-87 (default, reproduces them); 2: logbook 88 (practitioner-noun convention)."""
    if not with_lexicon:
        return ""
    preds = sorted(f"{p}/{n}" for p, n in mem.preds)
    consts = sorted(mem.consts)
    return (ONTOLOGIES[ontology] + "\nNAMES ALREADY IN MEMORY: predicates " + (", ".join(preds) or "(none yet)")
            + "; constants " + (", ".join(consts) or "(none yet)") + ".\n\n")


class Memory:
    """Structured memory fed by nx programs: graph engine for categories and rules, repaired episodic memory for
    residence (succession), and the plain structures of the trivial control."""

    def __init__(self) -> None:
        from grandnexus.graph.graph_engine import InMemoryGraphEngine
        from grandnexus.memory.episodic import EpisodicMemory, EpisodicMemoryConfig
        self.graph = InMemoryGraphEngine()
        self.epi = EpisodicMemory(EpisodicMemoryConfig(single_valued_relations={"lives_in": "not lives_in({subject}, {value})"}))
        self.episode = None
        self.items: list = []
        self.adj: dict = defaultdict(list)
        self.live_log: list = []
        self.global_rules: list = []
        self.preds: set = set()
        self.consts: set = set()

    def new_session(self) -> None:
        if self.episode is not None:
            self.epi.close_episode(self.episode)
        self.episode = self.epi.create_episode("session").episode_id

    def _edge(self, a: str, b: str, line: str) -> None:
        i = len(self.items)
        self.items.append(line)
        self.adj[a].append((b, i))
        for x in (a, b):
            try:
                self.graph.get_node(x)
            except Exception:  # noqa: BLE001  (NodeNotFoundError)
                self.graph.add_node(node_id=x, label="Concept")
        self.graph.add_edge(a, b, "rel", properties={"idx": i})

    def add_program(self, prog) -> None:
        for lit, _sid, knowledge in prog.facts:
            if knowledge:
                continue
            a = lit.atom
            self.preds.add((a.pred, len(a.args)))
            self.consts.update(x for x in a.args if not x[:1].isupper())
            if a.pred == "lives_in" and len(a.args) == 2 and not lit.neg:
                self.live_log.append((a.args[0], a.args[1]))
                self.epi.add_event(self.episode, str(lit), metadata={"subject": a.args[0], "relation": "lives_in", "value": a.args[1]})
            elif len(a.args) == 1:
                self._edge(a.args[0], a.pred, str(lit))
            elif len(a.args) == 2:
                self._edge(a.args[0], a.args[1], str(lit))
        for r in prog.rules:
            if r.knowledge:
                continue
            for x in list(r.body) + [r.head]:
                self.preds.add((x.atom.pred, len(x.atom.args)))
            if len(r.body) == 1 and len(r.body[0].atom.args) == 1 and len(r.head.atom.args) == 1 and not r.body[0].neg:
                self._edge(r.body[0].atom.pred, r.head.atom.pred, str(r))
            else:
                self.global_rules.append(str(r))

    def path(self, a: str, b: str, trivial: bool) -> list:
        if trivial:
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

    def residence(self, goal: str, subject: str, trivial: bool) -> list:
        if trivial:
            vals = [v for s, v in self.live_log if s == subject]
            if not vals:
                return []
            return [f"lives_in({subject}, {vals[-1]})"] + [f"not lives_in({subject}, {v})" for v in dict.fromkeys(vals) if v != vals[-1]]
        return [e.content for e in self.epi.retrieve_events(text=goal, max_results=4)]

    def decide(self, question: str, trivial: bool = False, detail: bool = False) -> tuple:
        """(strict verdict, number of statements used); with detail=True also the goal and the statements (logbook 86)."""
        from grandnexus.nexus_logic import decide, parse
        g = goal_of(question)
        if g is None:
            return ("unknown", 0, "", []) if detail else ("unknown", 0)
        goal, start, end = g
        items = self.residence(goal, start, trivial) if end == "lives_in" else self.path(start, end, trivial)
        lines = [x if x.rstrip().endswith(".") else x + "." for x in items + self.global_rules]
        prog = parse("\n".join(lines + [f"? {goal}."]), require_anchor=False)
        ans = decide(prog, use_knowledge=False).answer
        return (ans, len(items), goal, lines) if detail else (ans, len(items))


def run_world(world: WorldV2, level: int, seed: int, tr, extractor, concat: bool) -> list:
    import living_lab as LAB
    para = Paraphraser(level, seed * 10 + level)
    mems = {"lex": Memory(), "nolex": Memory()}
    st = LAB.Structured()
    texts: list = []
    rows = []
    for s, (facts, questions) in enumerate(world.sessions):
        st.new_session()
        session_text = []
        for f in facts:
            t = para(f, world.meta[f], s)
            session_text.append(t)
            ex = extractor.extract(t)
            for it in [("fact", x) for x in ex.facts] + [("univ", u["category"], u["clause"].obj, u["clause"]) for u in ex.universals]:
                st.add(it)
        texts += session_text
        for key, mem in mems.items():
            mem.new_session()
            if session_text:
                prog = tr.translate(" ".join(session_text), READ_QUERY, lexicon_block(mem, key == "lex"))["parsed"]
                mem.add_program(prog)
        for kind, q, gold in questions:
            ans = {}
            goals = extractor.extract(q).goals
            g0 = goals[0] if goals else ""
            m = LAB.ATOM.match(g0)
            if m:
                _n, rel, a, b = m.groups()
                items = st.live_episodic(g0) if rel == "live" else st.path_graph(a, b)
                ans["grammar"] = (LAB.verdict(items, g0), len(items))
            else:
                ans["grammar"] = ("unknown", 0)
            ans["llm_lexicon"] = mems["lex"].decide(q)
            ans["llm_lexicon_bfs"] = mems["lex"].decide(q, trivial=True)
            ans["llm_nolexicon"] = mems["nolex"].decide(q)
            if concat:
                r = tr.answer(" ".join(texts), q)
                ans["llm_concat"] = (r["verdict_strict"], len(texts))
            for p, (a_, n) in ans.items():
                rows.append({"kind": kind, "gold": gold, "pipeline": p, "answer": a_, "facts": n, "level": level})
    return rows


def main(argv=None, client=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--worlds", type=int, default=3)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--levels", default="1,2")
    ap.add_argument("--concat-worlds", type=int, default=1, help="worlds on which llm_concat runs (one call per question)")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    levels = [int(x) for x in a.levels.split(",")]
    worlds = [WorldV2(a.seed * 1000 + w, a.sessions, 5, 3) for w in range(a.worlds)]
    n_sessions = sum(1 for w in worlds for f, _ in w.sessions if f)
    n_q = sum(len(q) for w in worlds for _, q in w.sessions)
    n_q_concat = sum(len(q) for w in worlds[: a.concat_worlds] for _, q in w.sessions)
    calls = len(levels) * (2 * n_sessions + n_q_concat)
    print(f"{a.worlds} worlds, levels {levels}: {n_sessions} session readings x 2 lexicon modes, {n_q} questions per level, "
          f"llm_concat on {n_q_concat} questions per level -> about {calls} calls (+ corrective rounds); "
          f"estimated ${calls * 0.006:.2f} at the standard rate with the prompt cache (logbook 66: output is most of it)")
    if a.dry_run:
        return {"calls": calls}
    from grandnexus.cognition.perception.premise_extractor import PremiseExtractor
    from grandnexus.llm_interface.translator_v5 import Translator
    import cost
    tr = Translator(client=client, model=a.model) if client is not None else Translator(model=a.model)
    extractor = PremiseExtractor()
    rows = []
    for L in levels:
        for w, world in enumerate(worlds):
            rows += run_world(world, L, a.seed * 1000 + w, tr, extractor, concat=w < a.concat_worlds)
            print(f"  level {L}, world {w + 1}/{len(worlds)} done ({len(tr.receipts)} calls so far)")
    out = {"args": vars(a), "levels": {}}
    for L in levels:
        print(f"\n=== level {L}")
        print(f"{'pipeline':16} {'right':>7} " + " ".join(f"{k:>10}" for k in KINDS_V2) + f" {'asserted err':>13} {'facts/q':>8}")
        out["levels"][L] = {}
        for p in PIPELINES:
            rs = [r for r in rows if r["pipeline"] == p and r["level"] == L]
            if not rs:
                continue
            right = sum(r["answer"] == r["gold"] for r in rs)
            per = {k: (sum(r["answer"] == r["gold"] for r in rs if r["kind"] == k), sum(r["kind"] == k for r in rs)) for k in KINDS_V2}
            asserted = sum(r["answer"] in ("yes", "no", "contradictory") and r["answer"] != r["gold"] for r in rs)
            facts = sum(r["facts"] for r in rs) / len(rs)
            out["levels"][L][p] = {"n": len(rs), "pct": round(100 * right / len(rs), 1), "asserted_errors": asserted,
                                   "facts_per_question": round(facts, 2), "per_kind": per}
            print(f"{p:16} {100 * right / len(rs):6.1f}% " + " ".join(f"{c:>4}/{k:<5}" for c, k in per.values()) + f" {asserted:>13} {facts:>8.2f}")
    c = cost.from_receipts(tr.receipts, a.model)
    if c:
        out["cost"] = c
        print(f"\ncost: ${c['usd']:.3f} ({c['calls']} calls; without the prompt cache ${c['usd_without_cache']:.3f})")
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_llm_B_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"written: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
