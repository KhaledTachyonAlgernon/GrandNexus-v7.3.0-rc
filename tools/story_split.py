#!/usr/bin/env python
"""
Story split of archived learning runs (logbook 56), offline, no API call, no item text printed.

FOLIO asks several conclusions on one premises text (a "story"). For each archived run, the k experiences shown
in the `learned` condition are recomputed (TF-IDF retrieval is deterministic) and every test item is classed
"same story retrieved" (one of the shown experiences is a corrected reading of the SAME text: recall) or
"new story" (transfer). The paired sign test learned vs none is then given per class, per run and pooled.

A result is paired with the memory it was measured with: `memory_file` in its summary when present (runs >= 4),
else the memory saved with the same time stamp (runs 1-3), else --memory.

  python tools/story_split.py                       # every learning_*.json under tests_lab/resultats/learning
  python tools/story_split.py --memory tests_lab/resultats/learning/memory_train_61exp_2026-11-04_191343.json
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bench_folio import load_items, story_key                                          # noqa: E402
from bench_learning import sign_test                                                    # noqa: E402
from grandnexus.cognition.experience import ExperienceMemory                            # noqa: E402

CLASSES = ("same story retrieved", "new story")


def memory_for(result: pathlib.Path, summary: dict, fallback: str | None) -> pathlib.Path | None:
    if summary.get("memory_file") and pathlib.Path(summary["memory_file"]).exists():
        return pathlib.Path(summary["memory_file"])
    m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{6})\.json$", result.name)
    if m:
        same = sorted(result.parent.glob(f"memory_*_{m.group(1)}.json"))
        if same:
            return same[0]
    return pathlib.Path(fallback) if fallback else None


def split_run(result: pathlib.Path, memory: ExperienceMemory, items: dict, k: int) -> dict:
    d = json.load(open(result, encoding="utf-8"))
    rows = d["rows"]
    if "learned" not in rows or "none" not in rows:
        return {}
    none = {r["id"]: r for r in rows["none"]}
    learned = {r["id"]: r for r in rows["learned"]}
    out = {c: Counter() for c in CLASSES}
    for i, r in none.items():
        it = items.get(i)
        if it is None or i not in learned:
            continue
        shown = memory.retrieve(it["text"], it["query"], k, "similar")
        cls = CLASSES[0] if any(story_key(e.text) == it["story"] for e in shown) else CLASSES[1]
        n_ok, l_ok = r["pred"] == r["expected"], learned[i]["pred"] == learned[i]["expected"]
        out[cls]["n"] += 1
        out[cls]["learned_only"] += (l_ok and not n_ok)
        out[cls]["none_only"] += (n_ok and not l_ok)
        for cond, row in (("none", r), ("learned", learned[i])):
            out[cls][f"asserted_{cond}"] += (row["pred"] not in ("unknown", "error") and row["pred"] != row["expected"])
    return out


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", nargs="*", default=[str(ROOT / "tests_lab" / "resultats" / "learning" / "learning_*.json")])
    ap.add_argument("--memory", help="memory for results that record none and have no time-stamped memory")
    ap.add_argument("--split", default="train")
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args(argv)

    items = {it["id"]: it for it in load_items(a.split, None)}
    pooled = {c: Counter() for c in CLASSES}
    report = {}
    for pattern in a.results:
        for f in sorted(glob.glob(pattern) or [pattern]):
            result = pathlib.Path(f)
            summary = json.load(open(result, encoding="utf-8"))["summary"]
            mem_path = memory_for(result, summary, a.memory)
            if mem_path is None:
                print(f"{result.name}: no memory found, skipped")
                continue
            memory = ExperienceMemory.load(str(mem_path))
            out = split_run(result, memory, items, summary.get("k", a.k))
            if not out:
                continue
            report[result.name] = {c: dict(v) for c, v in out.items()}
            print(f"{result.name}  (memory {mem_path.name}, {len(memory.entries)} experiences)")
            for c in CLASSES:
                v = out[c]
                pooled[c].update(v)
                print(f"   {c:22} n={v['n']:>4}  only learned right {v['learned_only']:>3}  only none right {v['none_only']:>3}  "
                      f"p = {sign_test(v['learned_only'], v['none_only']):.3f}  asserted none/learned {v['asserted_none']}/{v['asserted_learned']}")
    print("POOLED (items of runs 1-3 partly overlap; memories differ between runs)")
    for c in CLASSES:
        v = pooled[c]
        print(f"   {c:22} n={v['n']:>4}  only learned right {v['learned_only']:>3}  only none right {v['none_only']:>3}  "
              f"p = {sign_test(v['learned_only'], v['none_only']):.3f}  asserted none/learned {v['asserted_none']}/{v['asserted_learned']}")
    report["pooled"] = {c: dict(v) for c, v in pooled.items()}
    return report


if __name__ == "__main__":
    main()
