#!/usr/bin/env python
"""
The loop that learns - does experience improve the reading on NEW items, without any hand-written rule?

Phase 1, experience (a pool the test never sees): read each item; when the strict verdict is wrong, the reader
is told only "wrong, expected X" and re-reads its own program; the correction is kept ONLY if the engine then
reaches the expected verdict (a verified experience). This is the loop: read -> verdict -> feedback ->
reflection -> memory.

Phase 2, test (a disjoint set, never seen): every item is read under these conditions, from the same memory:
  none      no memory                      (= the current system)
  static    the k most central experiences, the same for every item (consolidated experience, no retrieval)
  random    k experiences drawn at random  (control: is it the RELEVANCE of experience that helps?)
  learned   the k most similar experiences (the learning loop)

Two criteria, fixed before measuring (logbook 52-53):
  C-experience: static > none  (verified experience helps, even consolidated into a fixed set)
  C-relevance : learned > random AND learned > static (retrieving the RELEVANT experience adds something)
  both with asserted errors (false yes / no / contradictory) not above none. Trivial controls are printed as usual.

Stories (logbook 56). FOLIO asks several conclusions on one premises text (a "story"). Runs 1-4 were disjoint by
item id, not by story, and the whole measured effect came from test items whose story was already in the memory
(the corrected reading of the same text is retrieved and reused). Hence --story-mode:
  disjoint   (default) test items whose story is in neither the memory nor the experience pool (ids of the excluded
             runs are still excluded): the TRANSFER question (does experience on other texts help?)
  in-memory  test items whose story IS in the memory (new conclusions on texts already corrected):
             the RECALL question (is a verified reading reused?)
  any        the old draw (disjoint by id only; kept to reproduce runs 1-4)
Every API row records the experiences shown (source ids) and whether one of them is the same story; the paired
sign tests are also split "same story retrieved / new story". --dry-run draws, freezes and prints the sets without
any API call (pre-registration). Progress is checkpointed after every item and resumed automatically after an
interrupted Colab session (--no-resume to start over).

Run 1 (2026-11-02, memory of 18): none 77, random 83, learned 83 -> experience helps, relevance not shown.
No item text is printed; the memory is saved as JSON (it quotes the experience texts), the results as JSON.

  python tools/bench_learning.py --exp-n 150 --exp-seed 3 --test-n 100 --test-seed 4
  python tools/bench_learning.py --memory tests_lab/resultats/learning/<memory>.json --test-n 100 --test-seed 4   # reuse a memory
  python tools/bench_learning.py --memory <memory>.json --exp-n 0 --story-mode in-memory --test-n 0 --conditions none,random,learned \\
         --exclude-from "tests_lab/resultats/learning/*.json" "tests_lab/resultats/folio/folio_train_*.json"   # run 5a
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import random
import sys
import time
from collections import Counter
from dataclasses import asdict
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bench_folio import freeze, load_items, metrics, story_key                        # noqa: E402
import cost                                                                             # noqa: E402
from grandnexus.cognition.experience import (Experience, ExperienceMemory,            # noqa: E402
                                             examples_block, statements_diff)
from grandnexus.nexus_logic import ENGINE_VERSION                                     # noqa: E402
from grandnexus.llm_interface.translator_v5 import PROMPT_VERSION, Translator          # noqa: E402

CONDITIONS = ("none", "static", "random", "learned")   # static = the k most central experiences, same for every item
API_CONDITIONS = set(CONDITIONS)
STORY_MODES = ("disjoint", "in-memory", "any")
TRIVIAL = ("always_unknown", "majority", "random_label")


def draw(split: str, seed: int, n: int, exclude: set, items: list | None = None, keep_stories: set | None = None,
         drop_stories: set | None = None) -> list:
    """Shuffle the split with `seed`, drop the excluded ids, keep only `keep_stories` (if given), drop `drop_stories`
    (if given), take the first n (0 = all). The story filters are applied BEFORE the cut, so the same seed gives the
    same order whatever the filter."""
    items = [it for it in (items if items is not None else load_items(split, None)) if it["id"] not in exclude]
    if keep_stories is not None:
        items = [it for it in items if it["story"] in keep_stories]
    if drop_stories:
        items = [it for it in items if it["story"] not in drop_stories]
    random.Random(seed).shuffle(items)
    return items[:n] if n else items


def memory_stories(memory: ExperienceMemory) -> set:
    return {story_key(e.text) for e in memory.entries}


DISCORDANT = 0.09   # share of items on which learned and none disagree, runs 1-4 and 5a pooled: 52/568 (logbook 61)


def mde_points(n: int, d: float = DISCORDANT, z: float = 1.96 + 0.84) -> float:
    """Minimum detectable net gain, in points of accuracy, for a paired sign test on n items (normal approximation)."""
    return 100 * z * (d / max(1, n)) ** 0.5


def n_for(points: float, d: float = DISCORDANT, z: float = 1.96 + 0.84) -> int:
    return int(round(d * (z / (points / 100)) ** 2))


def sign_test(w: int, l: int) -> float:
    n = w + l
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(w, l) + 1)) / 2 ** n)


def paired(rows: dict, x: str, y: str, ids: set | None = None) -> tuple:
    X = {r["id"] for r in rows[x] if r["pred"] == r["expected"] and (ids is None or r["id"] in ids)}
    Y = {r["id"] for r in rows[y] if r["pred"] == r["expected"] and (ids is None or r["id"] in ids)}
    w, l = len(X - Y), len(Y - X)
    return w, l, sign_test(w, l)


def experience_phase(tr: Translator, items: list, memory: ExperienceMemory, store_correct: bool,
                     ckpt: pathlib.Path | None = None, resume: bool = True) -> dict:
    st = Counter()
    done = set()
    if ckpt and resume and ckpt.exists():
        d = json.loads(ckpt.read_text(encoding="utf-8"))
        done = set(d["done_ids"]); st = Counter(d["stats"])
        for e in d["entries"]:
            if e["source_id"] not in memory.known_ids:
                memory.add(Experience(**e))
        print(f"  experience phase resumed: {len(done)} items already read, memory {len(memory.entries)}")
    for k, it in enumerate(items, 1):
        if it["id"] in done:
            continue
        try:
            r = tr.answer(it["text"], it["query"])
        except Exception as e:  # noqa: BLE001
            st["errors"] += 1
            print(f"  !! item {it['id']}: {type(e).__name__}: {str(e)[:120]}")
            continue
        st["read"] += 1
        if r["verdict_strict"] == it["expected"]:
            st["right_first"] += 1
            if store_correct:
                memory.add(Experience(it["text"], it["query"], r["program"], it["expected"], source_id=it["id"]))
        else:
            st["wrong_first"] += 1
            try:
                c = tr.reflect_correction(it["text"], it["query"], r["program"], r["verdict_strict"], it["expected"])
            except Exception as e:  # noqa: BLE001
                st["errors"] += 1
                print(f"  !! reflection {it['id']}: {type(e).__name__}: {str(e)[:120]}")
                continue
            if c["verdict_strict"] == it["expected"] and not c["rejections"]:
                st["verified"] += 1
                memory.add(Experience(it["text"], it["query"], c["program"], it["expected"], r["verdict_strict"],
                                      statements_diff(r["program"], c["program"]), it["id"]))
            else:
                st["unverified"] += 1
        done.add(it["id"])
        if ckpt:
            ckpt.write_text(json.dumps({"done_ids": sorted(done), "stats": dict(st), "entries": [asdict(e) for e in memory.entries]},
                                       ensure_ascii=False), encoding="utf-8")
        if k % 10 == 0:
            print(f"  experience {k}/{len(items)}: wrong {st['wrong_first']}, verified corrections {st['verified']}")
    return dict(st)


def main(argv=None, client=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="train")
    ap.add_argument("--jsonl")
    ap.add_argument("--exp-n", type=int, default=150)
    ap.add_argument("--exp-seed", type=int, default=3)
    ap.add_argument("--test-n", type=int, default=100, help="0 = every eligible item")
    ap.add_argument("--test-seed", type=int, default=4)
    ap.add_argument("--k", type=int, default=3, help="experiences shown per reading")
    ap.add_argument("--memory", help="reuse a saved memory; with --exp-n > 0 the experience phase EXTENDS it with new items")
    ap.add_argument("--store-correct", action="store_true", help="also store first-try correct readings (positive experiences)")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--exclude-from", nargs="*", default=[], help="JSONs (globs) of earlier runs: bench results (learning or FOLIO: "
                                                                  "their test items) and saved memories (their experience items) are excluded")
    ap.add_argument("--story-mode", choices=STORY_MODES, default="disjoint",
                    help="disjoint = transfer (stories absent from memory, pool and excluded runs); in-memory = recall "
                         "(stories present in the memory); any = disjoint by id only (runs 1-4)")
    ap.add_argument("--dry-run", action="store_true", help="draw, freeze and print the sets; no API call")
    ap.add_argument("--no-resume", action="store_true", help="ignore an existing checkpoint for this test set")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--out", default=str(ROOT / "tests_lab" / "resultats" / "learning"))
    a = ap.parse_args(argv)

    outdir = pathlib.Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    memory = ExperienceMemory.load(a.memory, seed=a.test_seed) if a.memory else ExperienceMemory(seed=a.test_seed)
    exp_stats = {"loaded": len(memory.entries)}

    used, used_stories = set(), set()
    if a.jsonl:
        pool = load_items(a.split, a.jsonl)
        random.Random(a.exp_seed).shuffle(pool)
        exp_items, test_items = pool[: a.exp_n], pool[a.exp_n: a.exp_n + a.test_n]
    else:
        all_items = load_items(a.split, None)
        story_of = {it["id"]: it["story"] for it in all_items}
        for f in a.exclude_from:
            for pattern in (glob.glob(f) or [f]):
                d = json.load(open(pattern, encoding="utf-8"))
                if isinstance(d, list):                      # a saved memory: its experience items
                    used |= {str(e["source_id"]) for e in d if e.get("source_id")}
                else:                                        # a bench result (learning or FOLIO): its test items, and every
                    used |= {str(r["id"]) for rows in d.get("rows", {}).values() for r in rows}   # item its experience
                    used |= {str(i) for i in d.get("summary", {}).get("experience_read_ids", [])}  # phase READ (logbook 61)
        used_stories = {story_of[i] for i in used if i in story_of}
        exp_items = (draw(a.split, a.exp_seed, a.exp_n, used | memory.known_ids, all_items)
                     if (a.exp_n > 0 or not a.memory) else [])   # --memory with --exp-n 0: no experience phase
        exclude_ids = used | {it["id"] for it in exp_items} | memory.known_ids
        mem_stories = memory_stories(memory) | {it["story"] for it in exp_items}
        if a.story_mode == "in-memory":
            test_items = draw(a.split, a.test_seed, a.test_n, exclude_ids, all_items, keep_stories=mem_stories)
        elif a.story_mode == "disjoint":
            test_items = draw(a.split, a.test_seed, a.test_n, exclude_ids, all_items, drop_stories=mem_stories)
        else:
            test_items = draw(a.split, a.test_seed, a.test_n, exclude_ids, all_items)
        if used:
            n_old = sum(it["story"] in used_stories for it in test_items)
            print(f"excluded {len(used)} items ({len(used_stories)} stories) already used by earlier runs; "
                  f"{n_old} test items share a story with one of them")
    assert not ({it["id"] for it in exp_items} & {it["id"] for it in test_items}), "experience and test sets overlap"
    exp_sha, test_sha = freeze(exp_items), freeze(test_items)
    n_same = sum(it["story"] in memory_stories(memory) for it in test_items)
    print(f"experience pool: {len(exp_items)} items (sha {exp_sha}) | test set: {len(test_items)} items (sha {test_sha}), "
          f"labels {dict(Counter(i['expected'] for i in test_items))}, stories {len({i['story'] for i in test_items})} "
          f"({n_same} items with their story in the memory) | story mode: {a.story_mode}")
    print(f"power: with ~{100 * DISCORDANT:.0f}% discordant items per comparison (runs 1-5a), {len(test_items)} items detect a net gain of "
          f"about {mde_points(len(test_items)):.1f} points (80% power, two-sided 5%); 3 points would need about {n_for(3)} items")
    if a.dry_run:
        print("dry run: nothing measured")
        return {"experience_sha": exp_sha, "test_sha": test_sha, "n_exp": len(exp_items), "n_test": len(test_items),
                "same_story_items": n_same, "story_mode": a.story_mode}

    tr = Translator(client=client, model=a.model) if client is not None else Translator(model=a.model)
    if a.memory:
        print(f"memory loaded: {len(memory.entries)} experiences")
        exp_items = [it for it in exp_items if it["id"] not in memory.known_ids]
    if exp_items and (not a.memory or a.exp_n > 0):
        exp_stats.update(experience_phase(tr, exp_items, memory, a.store_correct, outdir / f"checkpoint_memory_{exp_sha}.json",
                                          not a.no_resume))
        mem_path = outdir / f"memory_{a.split}_{len(memory.entries)}exp_{stamp}.json"
        memory.save(str(mem_path))
        print(f"experience: {exp_stats} | memory: {len(memory.entries)} experiences -> {mem_path}")
    static = memory.central(a.k)
    n_same = sum(it["story"] in memory_stories(memory) for it in test_items)

    conditions = [c for c in a.conditions.split(",") if c]
    rows = {c: [] for c in conditions}
    rows.update({c: [] for c in TRIVIAL})
    ckpt = outdir / f"checkpoint_test_{test_sha}.json"
    if ckpt.exists() and not a.no_resume:
        d = json.loads(ckpt.read_text(encoding="utf-8"))
        if d.get("conditions") == conditions and d.get("k") == a.k:
            rows = d["rows"]
            print(f"resumed: {len(rows[conditions[0]])} items already measured")
    done = {r["id"] for r in rows[conditions[0]]}
    majority = Counter(i["expected"] for i in test_items).most_common(1)[0][0]
    rng = random.Random(a.test_seed)
    for k, it in enumerate(test_items, 1):
        if it["id"] in done:
            continue
        base = {"id": it["id"], "expected": it["expected"], "run": 0}
        for c in conditions:
            try:
                ex = ([] if c == "none" else static if c == "static"
                      else memory.retrieve(it["text"], it["query"], a.k, "random" if c == "random" else "similar"))
                r = tr.answer(it["text"], it["query"], examples_block(ex))
                rows[c].append({**base, "pred": r["verdict_strict"], "pred_full": r["verdict"], "n_examples": len(ex),
                                "shown": [e.source_id for e in ex], "same_story": any(story_key(e.text) == it["story"] for e in ex),
                                "rejections": len(r["rejections"]), "calls": r["calls"],
                                "tokens": r["tokens_in"] + r["tokens_out"] + r.get("cache_read", 0) + r.get("cache_write", 0),
                                "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
                                "cache_read": r.get("cache_read", 0), "cache_write": r.get("cache_write", 0)})
            except Exception as e:  # noqa: BLE001
                rows[c].append({**base, "pred": "error", "error": f"{type(e).__name__}: {str(e)[:120]}"})
        rows["always_unknown"].append({**base, "pred": "unknown"})
        rows["majority"].append({**base, "pred": majority})
        rows["random_label"].append({**base, "pred": rng.choice(["yes", "no", "unknown"])})
        ckpt.write_text(json.dumps({"test_sha": test_sha, "conditions": conditions, "k": a.k, "rows": rows}, ensure_ascii=False),
                        encoding="utf-8")
        if k % 10 == 0:
            print(f"  test {k}/{len(test_items)}")

    summary = {"experience_sha": exp_sha, "test_sha": test_sha, "n_exp": len(exp_items), "n_test": len(test_items), "k": a.k,
               "experience_read_ids": [it["id"] for it in exp_items],
               "memory_size": len(memory.entries), "memory_file": a.memory or "", "experience": exp_stats, "model": a.model,
               "prompt_version": PROMPT_VERSION, "engine_version": ENGINE_VERSION,
               "story_mode": a.story_mode, "exp_seed": a.exp_seed, "test_seed": a.test_seed, "conditions": conditions,
               "excluded_ids": len(used), "excluded_stories": len(used_stories), "same_story_items": n_same,
               "args": [str(x) for x in (argv if argv is not None else sys.argv[1:])], "modes": {}}
    base_pct = max(metrics(rows[b])["pct"] for b in TRIVIAL)
    print(f"\nbest trivial control: {base_pct}%")
    for c in conditions:
        mt = metrics(rows[c])
        summary["modes"][c] = mt
        print(f"{c:8} {mt['acc']:>3}/{mt['n']} = {mt['pct']:5}% | false yes {mt['false_yes']} | false no {mt['false_no']} "
              f"| false contradictory {mt['false_contradictory']} | inventions {mt['inventions']} | unknown {mt['unknown']} "
              f"| examples shown {sum(r.get('n_examples', 0) for r in rows[c])} | same story {sum(bool(r.get('same_story')) for r in rows[c])} "
              f"| calls {sum(r.get('calls', 0) for r in rows[c])} | tokens {sum(r.get('tokens', 0) for r in rows[c])}")
    m = summary["modes"]
    asserted = lambda x: m[x]["false_yes"] + m[x]["false_no"] + m[x]["false_contradictory"]
    if all(c in m for c in ("none", "static")):
        c_exp = m["static"]["acc"] > m["none"]["acc"] and asserted("static") <= asserted("none")
        print(f"\nC-experience (static > none, asserted errors not above none): {'PASS' if c_exp else 'FAIL'} "
              f"(static {m['static']['acc']}, none {m['none']['acc']}; asserted {asserted('static')} vs {asserted('none')})")
        summary["criteria_experience"] = c_exp
    if all(c in m for c in ("none", "random", "learned")) and "static" in m:
        c_rel = (m["learned"]["acc"] > m["random"]["acc"] and m["learned"]["acc"] > m["static"]["acc"] and asserted("learned") <= asserted("none"))
        print(f"C-relevance (learned > random and learned > static, asserted errors not above none): {'PASS' if c_rel else 'FAIL'} "
              f"(learned {m['learned']['acc']}, random {m['random']['acc']}, static {m['static']['acc']})")
        summary["criteria_relevance"] = c_rel
    elif all(c in m for c in ("none", "random", "learned")):
        ok = (m["learned"]["acc"] > m["none"]["acc"] and m["learned"]["acc"] > m["random"]["acc"] and asserted("learned") <= asserted("none"))
        print(f"\nCRITERIA (run 1 form): learned > none and learned > random, asserted errors not above none -> {'PASS' if ok else 'FAIL'}")
        summary["criteria_pass"] = ok
    # paired comparison per item (sign test): the honest statistic for small differences
    summary["paired"] = {}
    for x, y in (("learned", "none"), ("learned", "random"), ("learned", "static"), ("static", "none"), ("random", "none")):
        if x in rows and y in rows:
            w, l, pv = paired(rows, x, y)
            summary["paired"][f"{x}_vs_{y}"] = {"only_first_right": w, "only_second_right": l, "sign_test_p": round(pv, 3)}
            print(f"paired {x:7} vs {y:7}: only {x} right {w:>2} | only {y} right {l:>2} | sign test p = {pv:.3f}")
    # the same, split by story: was the SAME story retrieved for this item (recall) or not (transfer)?
    if "learned" in rows and "none" in rows:
        same = {r["id"] for r in rows["learned"] if r.get("same_story")}
        other = {r["id"] for r in rows["learned"]} - same
        summary["paired_by_story"] = {}
        for label, ids in (("same story retrieved", same), ("new story", other)):
            for y in ("none", "random"):
                if y in rows and ids:
                    w, l, pv = paired(rows, "learned", y, ids)
                    summary["paired_by_story"][f"learned_vs_{y}|{label}"] = {"n": len(ids), "only_learned_right": w, f"only_{y}_right": l,
                                                                           "sign_test_p": round(pv, 3)}
                    print(f"paired learned vs {y:6} | {label:20} (n={len(ids):>3}): only learned right {w:>2} | only {y} right {l:>2} | p = {pv:.3f}")
        w, l, pv = paired(rows, "learned", "none")
        c_main = pv < 0.05 and w > l and asserted("learned") <= asserted("none")
        name = "C-recall" if a.story_mode == "in-memory" else "C-transfer" if a.story_mode == "disjoint" else "C-paired"
        print(f"\n{name} (learned vs none: sign test p < 0.05 in favour of learned, asserted errors not above none): "
              f"{'PASS' if c_main else 'FAIL'} ({w}/{l}, p = {pv:.3f}; asserted {asserted('learned')} vs {asserted('none')})")
        summary[name] = c_main
    print()
    summary["cost"] = cost.report({c: rows[c] for c in conditions}, a.model)
    run_cost = cost.from_receipts(tr.receipts, a.model)
    if run_cost:
        summary["cost"]["run_total_including_experience_phase"] = run_cost
        print(f"cost of the whole run (every call, experience phase included): ${run_cost['usd']:.3f}")
    out = outdir / f"learning_{a.split}_test{len(test_items)}_{test_sha}_{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    if ckpt.exists():
        ckpt.unlink()
    print(f"written: {out}")
    return summary


if __name__ == "__main__":
    main()
