#!/usr/bin/env python
"""
Living bench, phase A of "the real language" (logbook 81), sandbox, offline, 0 API call.

Same worlds (world v2), same questions and answers as the lab version (tools/living_lab.py), but the facts are written
at four levels of freedom by a seeded paraphraser; the questions stay in the canonical form ("Is Bob a chess player?",
"Does Alice live in Paris?"), so the system has to connect what it read to what is asked.
  level 0  the canonical sentence                         "Bob is a chess player."   "Alice lives in Lyon."
  level 1  synonyms and turns of phrase                    "Bob plays chess."   "Swimmers are never calm."   "Alice moved to Paris."
  level 2  freer sentences                                 "If someone plays chess, they are patient."   "Alice recently relocated to Paris."
  level 3  references to resolve: a pronoun for the person, after a sentence that only introduces them
                                                           "Bob called today. He plays chess."
For each level: how many facts the grammar pathway still extracts with the right structure, and the five pipelines of
the lab version (concat, overlap, bfs+script, graph+episodic, semantic+episodic). Sandbox: no criteria, no claim.

  python tools/living_language.py --seed 11 --worlds 20 --sessions 12
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from living_bench import KINDS_V2, WorldV2, article                                       # noqa: E402
import living_lab as LAB                                                                    # noqa: E402

FEMALE = set("Alice Carol Erin Grace Heidi Judy Laura Nina Paula Quinn Rita Tina Uma Wendy Yara".split())
ROLE_VERB = {"chess player": "plays chess", "painter": "paints", "swimmer": "swims", "teacher": "teaches",
             "gardener": "gardens", "pilot": "flies planes", "baker": "bakes bread", "musician": "plays music",
             "nurse": "works as a nurse", "farmer": "runs a farm"}


def plural(n: str) -> str:
    return n + "s"


def cap(s: str) -> str:
    return s[0].upper() + s[1:]


class Paraphraser:
    """Writes each fact at a given level; deterministic for a (seed, world)."""

    def __init__(self, level: int, seed: int) -> None:
        self.level, self.rng = level, random.Random(seed)
        self.has_city: set = set()

    def __call__(self, fact: str, meta: tuple, session: int) -> str:
        a, rel, b, pol = meta
        L, pick = self.level, self.rng.choice
        if rel == "instance_of":
            p, role = a, b
            he = "She" if p in FEMALE else "He"
            forms = {0: [f"{p} is {article(role)} {role}."],
                     1: [f"{p} works as {article(role)} {role}.", f"{p} {ROLE_VERB[role]}."],
                     2: [f"{p} has been {article(role)} {role} for years.", f"These days, {p} {ROLE_VERB[role]}."],
                     3: [f"{p} called today. {he} {ROLE_VERB[role]}.", f"{p} called today. {he} is {article(role)} {role}."]}
            return pick(forms[L])
        if rel == "is_a":
            role, c = a, b
            forms = {0: [f"Every {role} is {article(c)} {c}."],
                     1: [f"All {plural(role)} are {plural(c)}.", f"{cap(plural(role))} are {plural(c)}."],
                     2: [f"Anyone who is {article(role)} {role} is {article(c)} {c}.", f"Being {article(role)} {role} makes you {article(c)} {c}."]}
            return pick(forms[min(L, 2)])
        if rel == "has_property":
            x, adj = a, b
            if pol:
                forms = {0: [f"Every {x} is {adj}."], 1: [f"All {plural(x)} are {adj}.", f"{cap(plural(x))} are always {adj}."],
                         2: [f"Anyone who is {article(x)} {x} is {adj}.", f"If someone is {article(x)} {x}, they are {adj}."]}
            else:
                forms = {0: [f"No {x} is {adj}."], 1: [f"{cap(plural(x))} are never {adj}.", f"No {x} is ever {adj}."],
                         2: [f"Anyone who is {article(x)} {x} is not {adj}.", f"If someone is {article(x)} {x}, they are not {adj}."]}
            return pick(forms[min(L, 2)])
        p, city = a, b                                      # lives in
        moved = p in self.has_city
        self.has_city.add(p)
        he = "She" if p in FEMALE else "He"
        if moved:
            forms = {0: [f"{p} lives in {city}."], 1: [f"{p} moved to {city}.", f"{p} now lives in {city}."],
                     2: [f"{p} recently relocated to {city}.", f"{p} left for {city}."],
                     3: [f"{p} called today. {he} moved to {city}."]}
        else:
            forms = {0: [f"{p} lives in {city}."], 1: [f"{p} resides in {city}.", f"{p} has a flat in {city}."],
                     2: [f"{p} settled in {city} a while ago."], 3: [f"{p} called today. {he} lives in {city}."]}
        return pick(forms[L])


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=11, help="sandbox seed (7 is reserved for the lab measurement of logbook 80)")
    ap.add_argument("--worlds", type=int, default=20)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--levels", default="0,1,2,3")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)
    from grandnexus.cognition.perception.premise_extractor import PremiseExtractor
    from grandnexus.cognition.reasoning.text_reasoner import TextReasoner
    extractor, reasoner = PremiseExtractor(), TextReasoner()
    out = {"args": vars(a), "levels": {}}
    for L in [int(x) for x in a.levels.split(",")]:
        rows, fid = [], [0, 0]
        for w in range(a.worlds):
            seed = a.seed * 1000 + w
            r, f = LAB.run_world(WorldV2(seed, a.sessions, 5, 3), extractor, reasoner, Paraphraser(L, seed * 10 + L))
            rows += r
            fid[0] += f[0]
            fid[1] += f[1]
        n = len(rows) // len(LAB.PIPELINES)
        print(f"\n=== level {L}: {n} questions | facts extracted with the right structure: {fid[0]}/{fid[1]} ({100 * fid[0] / max(1, fid[1]):.1f}%)")
        print(f"{'pipeline':18} {'right':>7} " + " ".join(f"{k:>10}" for k in KINDS_V2) + f" {'asserted err':>13} {'facts/q':>8}")
        lv = {"fidelity": fid, "pipelines": {}}
        for p in LAB.PIPELINES:
            rs = [r for r in rows if r["pipeline"] == p]
            right = sum(r["answer"] == r["gold"] for r in rs)
            per = {k: (sum(r["answer"] == r["gold"] for r in rs if r["kind"] == k), sum(r["kind"] == k for r in rs)) for k in KINDS_V2}
            asserted = sum(r["answer"] in ("yes", "no", "contradictory") and r["answer"] != r["gold"] for r in rs)
            facts = sum(r["facts"] for r in rs) / max(1, len(rs))
            lv["pipelines"][p] = {"pct": round(100 * right / max(1, len(rs)), 1), "asserted_errors": asserted, "facts_per_question": round(facts, 2),
                                  "per_kind": per}
            print(f"{p:18} {100 * right / max(1, len(rs)):6.1f}% " + " ".join(f"{c:>4}/{k:<5}" for c, k in per.values()) + f" {asserted:>13} {facts:>8.2f}")
        out["levels"][L] = lv
    if not a.no_write:
        d = ROOT / "tests_lab" / "resultats" / "living"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"living_language_A_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwritten: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
