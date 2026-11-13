#!/usr/bin/env python
"""
Living bench, sandbox prototype (logbook 76): facts that arrive over sessions, questions that need old facts.
Offline, 0 API call: the grammar pathway (premise extractor -> nexus_logic) reads simple English. No claim is made
from this bench in sandbox mode; it shows where (and whether) a memory can matter.

A seeded generator builds small "lives": people, roles, rules on roles, cities. Each session brings a few facts:
  "Bob is a chess player."   "Every chess player is patient." / "No swimmer is calm."   "Alice lives in Lyon."
A person who already lives somewhere and gets a new city has MOVED: the old fact is superseded.
Questions asked at a session, answers known by construction:
  recall      a fact at least two sessions old                         "Is Bob a chess player?" -> yes
  chain       a rule and a role, at least one of them from an older session  "Is Bob patient?" -> yes / no
  update_new  the latest city of someone who moved                     "Does Alice live in Paris?" -> yes
  update_old  the former city of someone who moved                      "Does Alice live in Lyon?" -> no
  unknown     nothing supports the answer                               "Is Tom brave?" -> unknown
(update_old needs to know that moving ends the former residence: a pipeline that keeps both facts answers "yes",
an asserted error; one that keeps only the latest answers "unknown", a refusal.)

Pipelines, each giving a context (facts) + the question to the same reasoner:
  none        only the facts of the current session
  concat      every fact so far, in order ("put everything back in the text")
  latest      concat, but only the latest city of each person (a trivial supersession rule)
  overlap     the K past facts sharing most words with the question, most recent first on ties
  working     the 2025 WorkingMemory: every fact stored as it arrives, retrieve(question, K)
  episodic_2025  the EpisodicMemory as written in 2025: one episode per session, retrieve_events(question, K)
  episodic    the same module repaired (logbook 77): retrieval by the question's words, and succession for "lives in"
              (a new city closes the old one and the memory records "X does not live in <old city>.")
World v2 (--world v2, logbook 78) adds classes ("Every chess player is a thinker.", "Every thinker is calm.") and the
question kind chain2 (role -> class -> property): the middle fact shares no word with the question. Two more pipelines:
  graph       the 2025 InMemoryGraphEngine: one edge per fact (person -> role -> class -> property), find_paths from
              the person to the asked concept, the facts on the paths; "lives in" questions go to the repaired episodic memory
  semantic    the 2025 SemanticMemory: the same facts as concepts and relations, walked from the person
              (get_relations_by_source, depth 3); "lives in" questions go to the repaired episodic memory

  python tools/living_bench.py --worlds 20 --sessions 12 --seed 1
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import random
import re
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NAMES = ("Alice Bob Carol Dave Erin Frank Grace Heidi Ivan Judy Karl Laura Mike Nina Oscar Paula Quinn Rita Sam Tina "
         "Uma Victor Wendy Xavier Yara Zack").split()
ROLES = ["chess player", "painter", "swimmer", "teacher", "gardener", "pilot", "baker", "musician", "nurse", "farmer"]
ADJS = ["patient", "curious", "brave", "calm", "strong", "careful", "generous", "honest"]
CITIES = ["Lyon", "Paris", "Lille", "Nantes", "Nice", "Rennes", "Dijon", "Brest", "Metz", "Tours", "Caen", "Rouen"]
CLASSES = ["thinker", "athlete", "artist", "worker", "traveler"]
KINDS = ("recall", "chain", "update_new", "update_old", "unknown")
KINDS_V2 = ("recall", "chain", "chain2", "update_new", "update_old", "unknown")
PIPELINES = ("none", "concat", "latest", "overlap", "working", "episodic_2025", "episodic")
PIPELINES_V2 = PIPELINES + ("graph", "semantic")
STOP = set("the a an is are does do every no not in of to live lives".split())
# Seeds of the living bench (STATUS, handover): worlds of a measured seed are never read for a diagnosis nor printed,
# and never measured again; debugging and offline tests use the debug seeds only.
MEASURED_SEEDS = (7, 13, 17, 19, 23)       # logbook 80, 85, 89, 93, 94
DEBUG_SEEDS = (5, 11)
USED_SEEDS = (1, 3, 5, 7, 11, 13, 17, 19, 23)  # never the seed of a new measurement


def article(role: str) -> str:
    return "an" if role[0] in "aeiou" else "a"


class World:
    """One life: facts arriving over sessions, the state that answers the questions."""

    def __init__(self, seed: int, sessions: int, facts_per_session: int, questions_per_session: int) -> None:
        self.rng = random.Random(seed)
        self.people = self.rng.sample(NAMES, 10)
        self.polarity = {a: self.rng.choice((True, False)) for a in ADJS}     # one polarity per adjective: no contradiction
        self.roles: dict = defaultdict(dict)       # person -> {role: session}
        self.rules: dict = {}                      # (role, adj) -> session
        self.city: dict = {}                       # person -> (city, session)
        self.moves: dict = {}                      # person -> (old city, new city, session of the move)
        self.sessions = []                         # [(facts, questions)]
        for s in range(sessions):
            facts = [self._fact(s) for _ in range(facts_per_session)]
            qs = [q for q in (self._question(s) for _ in range(questions_per_session * 4)) if q][:questions_per_session] if s >= 2 else []
            self.sessions.append(([f for f in facts if f], qs))

    def _fact(self, s: int) -> str | None:
        r = self.rng.random()
        p = self.rng.choice(self.people)
        if r < 0.40:
            role = self.rng.choice(ROLES)
            if role in self.roles[p]:
                return None
            self.roles[p][role] = s
            return f"{p} is {article(role)} {role}."
        if r < 0.70:
            role, adj = self.rng.choice(ROLES), self.rng.choice(ADJS)
            if (role, adj) in self.rules:
                return None
            self.rules[(role, adj)] = s
            return f"Every {role} is {adj}." if self.polarity[adj] else f"No {role} is {adj}."
        city = self.rng.choice(CITIES)
        if p in self.city:
            old = self.city[p][0]
            if old == city:
                return None
            self.moves[p] = (old, city, s)
        self.city[p] = (city, s)
        return f"{p} lives in {city}."

    def _question(self, s: int, kind: str | None = None):
        kind = kind or self.rng.choice(KINDS)
        p = self.rng.choice(self.people)
        if kind == "recall":
            old = [r for r, t in self.roles[p].items() if t <= s - 2]
            return ("recall", f"Is {p} {article(old[0])} {old[0]}?", "yes") if old else None
        if kind == "chain":
            for role, t_role in self.roles[p].items():
                for adj in ADJS:
                    t_rule = self.rules.get((role, adj))
                    if t_rule is not None and min(t_role, t_rule) < s:
                        return ("chain", f"Is {p} {adj}?", "yes" if self.polarity[adj] else "no")
            return None
        if kind in ("update_new", "update_old"):
            mv = self.moves.get(p)
            if not mv or mv[2] > s:
                return None
            old, new, _ = mv
            if self.city[p][0] != new:                       # moved again since: keep it simple
                return None
            return (kind, f"Does {p} live in {new if kind == 'update_new' else old}?", "yes" if kind == "update_new" else "no")
        adj = self.rng.choice(ADJS)
        if any((role, adj) in self.rules for role in self.roles[p]) or self.roles[p] == {}:
            return None
        return ("unknown", f"Is {p} {adj}?", "unknown")


class WorldV2(World):
    """World v2 (logbook 78): roles belong to classes ("Every chess player is a thinker."), rules may sit on a class
    ("Every thinker is calm."), and chain2 asks a property reached through the class only. Each fact carries its
    structure (subject, relation, value) for the memories that need it."""

    def __init__(self, seed: int, sessions: int, facts_per_session: int, questions_per_session: int) -> None:
        self.cls: dict = {}            # role -> (class, session)
        self.meta: dict = {}           # fact -> structure
        super().__init__(seed, sessions, facts_per_session, questions_per_session)

    def _fact(self, s: int) -> str | None:
        r = self.rng.random()
        p = self.rng.choice(self.people)
        if r < 0.30:
            role = self.rng.choice(ROLES)
            if role in self.roles[p]:
                return None
            self.roles[p][role] = s
            f = f"{p} is {article(role)} {role}."
            self.meta[f] = (p, "instance_of", role, True)
            return f
        if r < 0.45:
            role, c = self.rng.choice(ROLES), self.rng.choice(CLASSES)
            if role in self.cls:
                return None
            self.cls[role] = (c, s)
            f = f"Every {role} is {article(c)} {c}."
            self.meta[f] = (role, "is_a", c, True)
            return f
        if r < 0.70:
            subject = self.rng.choice(ROLES if r < 0.58 else CLASSES)
            adj = self.rng.choice(ADJS)
            if (subject, adj) in self.rules:
                return None
            self.rules[(subject, adj)] = s
            f = f"Every {subject} is {adj}." if self.polarity[adj] else f"No {subject} is {adj}."
            self.meta[f] = (subject, "has_property", adj, self.polarity[adj])
            return f
        city = self.rng.choice(CITIES)
        if p in self.city:
            old = self.city[p][0]
            if old == city:
                return None
            self.moves[p] = (old, city, s)
        self.city[p] = (city, s)
        f = f"{p} lives in {city}."
        self.meta[f] = (p, "lives in", city, True)
        return f

    def _question(self, s: int):
        kind = self.rng.choice(KINDS_V2)
        p = self.rng.choice(self.people)
        if kind == "chain2":
            for role in self.roles[p]:
                c = self.cls.get(role, (None,))[0]
                for adj in ADJS:
                    if c and (c, adj) in self.rules and not any((r, adj) in self.rules for r in self.roles[p]):
                        return ("chain2", f"Is {p} {adj}?", "yes" if self.polarity[adj] else "no")
            return None
        if kind == "unknown":
            adj = self.rng.choice(ADJS)
            subjects = set(self.roles[p]) | {self.cls[r][0] for r in self.roles[p] if r in self.cls}
            if not self.roles[p] or any((x, adj) in self.rules for x in subjects):
                return None
            return ("unknown", f"Is {p} {adj}?", "unknown")
        if kind == "chain":
            for role, t_role in self.roles[p].items():
                for adj in ADJS:
                    t_rule = self.rules.get((role, adj))
                    if t_rule is not None and min(t_role, t_rule) < s:
                        return ("chain", f"Is {p} {adj}?", "yes" if self.polarity[adj] else "no")
            return None
        return World._question(self, s, kind) if kind in ("recall", "update_new", "update_old") else None


def node(name: str) -> str:
    return name.lower().replace(" ", "_")


def path_facts(question: str, graph=None, sem=None) -> list | None:
    """Facts on the paths from the asked person to the asked concept ("Is Bob calm?", "Is Bob a thinker?"), through the
    2025 graph engine (find_paths) or semantic memory (relations walked from the person). None: not an "is" question."""
    m = re.match(r"Is (\w+) (?:an? )?(.+)\?$", question)
    if not m:
        return None
    start, end = node(m.group(1)), node(m.group(2))
    texts: list = []
    if graph is not None:
        try:
            paths = graph.find_paths(start, end, max_depth=3)
        except Exception:  # noqa: BLE001
            paths = []
        for path in paths:
            for a, b in zip(path, path[1:]):
                for nb, eid, _etype in graph.get_node_neighbors(a):
                    if nb == b:
                        t = (getattr(graph.get_edge(eid), "properties", None) or {}).get("text")
                        if t and t not in texts:
                            texts.append(t)
        return texts
    frontier, parent = [start], {start: None}
    for _ in range(3):
        nxt = []
        for cid in frontier:
            for rel in sem.get_relations_by_source(cid):
                if rel.target_concept_id not in parent:
                    parent[rel.target_concept_id] = (cid, rel.properties.get("text"))
                    nxt.append(rel.target_concept_id)
        frontier = nxt
    cur = end if end in parent else None
    while cur is not None and parent[cur] is not None:
        cur, t = parent[cur]
        if t and t not in texts:
            texts.insert(0, t)
    return texts


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2}


def run_world(world: World, reasoner, k: int) -> list:
    from grandnexus.memory.episodic import EpisodicMemory, EpisodicMemoryConfig
    from grandnexus.memory.working import WorkingMemory, WorkingMemoryConfig
    v2 = isinstance(world, WorldV2)
    graph = sem = None
    if v2:
        import uuid
        from grandnexus.graph.graph_engine import InMemoryGraphEngine
        from grandnexus.memory import semantic as S
        graph, sem = InMemoryGraphEngine(), S.SemanticMemory(S.SemanticMemoryConfig())
        rtype = {"instance_of": S.RelationType.INSTANCE_OF, "is_a": S.RelationType.IS_A, "has_property": S.RelationType.HAS_PROPERTY}
    wm = WorkingMemory(WorkingMemoryConfig())
    em_old = EpisodicMemory(EpisodicMemoryConfig(lexical_retrieval=False))          # the 2025 behaviour
    em = EpisodicMemory(EpisodicMemoryConfig(single_valued_relations={"lives in": "{subject} does not live in {value}."}))
    history: list = []                              # (session, fact)
    rows = []
    for s, (facts, questions) in enumerate(world.sessions):
        ep, ep_old = em.create_episode("session", context={"session": s}), em_old.create_episode("session", context={"session": s})
        for f in facts:
            history.append((s, f))
            wm.store_item(f, source=f"session{s}")
            em_old.add_event(ep_old.episode_id, f, metadata={"session": s})
            m = re.match(r"(\w+) lives in (\w+)\.", f)
            md = {"session": s, "subject": m.group(1), "relation": "lives in", "value": m.group(2)} if m else {"session": s}
            em.add_event(ep.episode_id, f, metadata=md)
            if v2 and f in world.meta and world.meta[f][1] != "lives in":
                a, rel, b, _pol = world.meta[f]
                for x in (a, b):
                    try:
                        graph.get_node(node(x))
                    except Exception:  # noqa: BLE001  (NodeNotFoundError)
                        graph.add_node(node_id=node(x), label="Concept", properties={"name": x})
                    if sem.get_concept(node(x)) is None:
                        sem.add_concept(S.Concept(concept_id=node(x), name=x))
                graph.add_edge(node(a), node(b), rel, properties={"text": f})
                sem.add_relation(S.Relation(relation_id=str(uuid.uuid4()), source_concept_id=node(a), relation_type=rtype[rel],
                                            target_concept_id=node(b), properties={"text": f}))
        em.close_episode(ep.episode_id)
        em_old.close_episode(ep_old.episode_id)
        for kind, q, gold in questions:
            latest_city = {}
            for t, f in history:
                m = re.match(r"(\w+) lives in (\w+)\.", f)
                if m:
                    latest_city[m.group(1)] = f
            ctx = {
                "none": list(facts),
                "concat": [f for _, f in history],
                "latest": [f for _, f in history if not re.match(r"\w+ lives in", f) or latest_city.get(f.split()[0]) == f],
                "overlap": [f for _, _, f in sorted(((-len(words(f) & words(q)), -t, f) for t, f in history))[:k]],
                "working": [getattr(x[0] if isinstance(x, tuple) else x, "content", "") for x in wm.retrieve(q, max_results=k)],
                "episodic_2025": [getattr(x[0] if isinstance(x, tuple) else x, "content", "") for x in em_old.retrieve_events(text=q, max_results=k)],
                "episodic": [getattr(x[0] if isinstance(x, tuple) else x, "content", "") for x in em.retrieve_events(text=q, max_results=k)],
            }
            if v2:
                for name, kw in (("graph", {"graph": graph}), ("semantic", {"sem": sem})):
                    pf = path_facts(q, **kw)
                    ctx[name] = pf if pf is not None else [x.content for x in em.retrieve_events(text=q, max_results=4)]
            for name, c in ctx.items():
                t0 = time.perf_counter()
                r = reasoner.answer(" ".join(c + [q]), mode="grammar")
                ans = r.get("answer") if isinstance(r, dict) else str(r)
                rows.append({"session": s, "kind": kind, "gold": gold, "pipeline": name, "answer": ans,
                             "facts": len(c), "seconds": time.perf_counter() - t0})
    return rows


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worlds", type=int, default=20)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--facts", type=int, default=5, help="facts per session")
    ap.add_argument("--questions", type=int, default=3, help="questions per session (from session 3)")
    ap.add_argument("--k", type=int, default=6, help="facts retrieved by the memories")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--world", choices=("v1", "v2"), default="v1", help="v2: classes and two-step chains (logbook 78)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    from grandnexus.cognition.reasoning.text_reasoner import TextReasoner
    reasoner = TextReasoner()
    rows = []
    W, kinds, pipelines = (WorldV2, KINDS_V2, PIPELINES_V2) if a.world == "v2" else (World, KINDS, PIPELINES)
    for w in range(a.worlds):
        rows += run_world(W(a.seed * 1000 + w, a.sessions, a.facts, a.questions), reasoner, a.k)
    n_q = len(rows) // len(pipelines)
    print(f"{a.worlds} worlds x {a.sessions} sessions: {n_q} questions {dict(Counter(r['kind'] for r in rows if r['pipeline'] == 'none'))}")
    summary = {}
    print(f"\n{'pipeline':10} {'right':>7} " + " ".join(f"{k:>10}" for k in kinds) + f" {'asserted err':>13} {'facts/q':>8} {'ms/q':>6}")
    for p in pipelines:
        rs = [r for r in rows if r["pipeline"] == p]
        right = sum(r["answer"] == r["gold"] for r in rs)
        per = {k: (sum(r["answer"] == r["gold"] for r in rs if r["kind"] == k), sum(r["kind"] == k for r in rs)) for k in kinds}
        asserted = sum(r["answer"] in ("yes", "no", "contradictory") and r["answer"] != r["gold"] for r in rs)
        facts = sum(r["facts"] for r in rs) / max(1, len(rs))
        ms = 1000 * sum(r["seconds"] for r in rs) / max(1, len(rs))
        summary[p] = {"right": right, "n": len(rs), "per_kind": per, "asserted_errors": asserted, "facts_per_question": round(facts, 1), "ms_per_question": round(ms, 1)}
        print(f"{p:10} {100 * right / max(1, len(rs)):6.1f}% " + " ".join(f"{c:>4}/{n:<5}" for c, n in per.values())
              + f" {asserted:>13} {facts:>8.1f} {ms:>6.1f}")
    out = {"args": vars(a), "summary": summary}
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_sandbox_{a.world + '_' if a.world != 'v1' else ''}{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwritten: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
