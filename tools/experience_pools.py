#!/usr/bin/env python
"""
The items read by the experience phases of learning runs 1-3 (logbook 61), reconstructed offline from the archived
pool shas: a phase reads every item of its pool, stores only the verified corrections, and the result files before
v7.2.5-rc did not record the others. Those items are not "seen" (no text was read by anyone), but a test drawn among
them is biased: they were read right at the first attempt, or resisted the corrective reflection.

The seeds were found by search against the shas (run 3's pool was drawn by the Colab assistant): pool = shuffle of the
train split with the seed, first n items, no exclusion; the phase then skipped the items already in the memory.
Writes tests_lab/resultats/learning/experience_pools_runs1-3.json, picked up by --exclude-from with the usual glob.

  python tools/experience_pools.py            # rebuild and check the shas
"""
from __future__ import annotations

import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bench_folio import freeze, load_items                                                # noqa: E402

POOLS = [   # run, seed, n drawn, sha of the drawn pool (summary.experience_sha of the run), memory it built
    {"run": 1, "seed": 3, "n": 150, "sha": "69df473b4385cbb0", "memory": "memory_train_exp150_69df473b4385cbb0_2026-11-02_191057.json"},
    {"run": 2, "seed": 5, "n": 250, "sha": "a110fee6dc04d6a8", "memory": "memory_train_60exp_2026-11-04_173037.json"},
    {"run": 3, "seed": 7, "n": 400, "sha": "1533062121ae0743", "memory": "memory_train_61exp_2026-11-04_191343.json"},
]
OUT = ROOT / "tests_lab" / "resultats" / "learning" / "experience_pools_runs1-3.json"


def rebuild(split: str = "train") -> dict:
    items = load_items(split, None)
    read, pools = [], []
    for p in POOLS:
        pool = list(items)
        random.Random(p["seed"]).shuffle(pool)
        pool = pool[: p["n"]]
        sha = freeze(pool)
        if sha != p["sha"]:
            raise SystemExit(f"run {p['run']}: sha {sha} != {p['sha']} (data or code changed?)")
        ids = [it["id"] for it in pool]
        pools.append({**p, "ids": ids})
        read += [i for i in ids if i not in read]
    return {"summary": {"what": "items read by the experience phases of learning runs 1-3 (stored or not)",
                        "experience_read_ids": read, "pools": pools}, "rows": {}}


if __name__ == "__main__":
    d = rebuild()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(d['summary']['experience_read_ids'])} distinct items read by 3 pools "
          f"({', '.join(str(p['n']) for p in d['summary']['pools'])}); shas checked")
