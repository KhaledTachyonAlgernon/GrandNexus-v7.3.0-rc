#!/usr/bin/env python
"""
Module audition n°1, family metacognition (logbook 68): does the confidence that the 2025 ConfidenceEvaluator gives
to a reading predict whether the strict verdict is right? Offline, 0 API call, no item text printed.

Data: the archived programs of the FOLIO validation runs (tests_lab/resultats/folio/programs/<run>/<id>_r<k>.nx) and
the expected labels of the same runs. Each program is replayed through the reference engine (strict).
  F0  the module as wired today: the result carries the reasoner's own `confidence` (0.95 decided, 0.0 unknown) and
      ConfidenceEvaluator.evaluate_reasoning_confidence relays it
  F1  the module's own default model, fed with what the engine can give: inference_steps = the proof,
      assumptions = the statements marked as background knowledge, contradictions = a contradictory verdict
Trivial controls: constant, random, decided-or-not, no rejection, no corrective round, short program, short proof.
Measure: AUROC of each signal for "the strict verdict is right", on all programs, on the decided ones, on the unknown ones.
Criterion: F1 >= 0.60 and >= best trivial control + 0.05, on all programs and on the decided ones.

  python tools/audition_confidence.py
"""
from __future__ import annotations

import glob
import json
import logging
import pathlib
import random
import sys
import time
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grandnexus.nexus_logic import decide, parse                                         # noqa: E402

DECIDED = ("yes", "no", "contradictory")
TRIVIAL = ("constant", "random", "decided", "no_rejection", "no_corrective", "short_program", "short_proof")


def auroc(scores, labels) -> float | None:
    """P(score of a right verdict > score of a wrong one), ties counted 1/2. None when one class is empty."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    order = sorted(set(scores))
    rank = {}
    below = 0
    counts = {v: 0 for v in order}
    for s in scores:
        counts[s] += 1
    for v in order:                                   # mid-rank of each distinct value
        rank[v] = below + (counts[v] + 1) / 2
        below += counts[v]
    r_pos = sum(rank[s] for s in pos)
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def collect() -> list[dict]:
    logging.disable(logging.CRITICAL)
    from grandnexus.cognition.metacognition.confidence import ConfidenceEvaluator
    ev = ConfidenceEvaluator()
    rng = random.Random(0)
    out = []
    for f in sorted(glob.glob(str(ROOT / "tests_lab" / "resultats" / "folio" / "folio_validation_203_*.json"))):
        res = pathlib.Path(f)
        progdir = res.parent / "programs" / res.stem
        if not progdir.is_dir():
            continue
        for row in json.load(open(res, encoding="utf-8"))["rows"].get("translator", []):
            p = progdir / f"{row['id']}_r{row['run']}.nx"
            if not p.exists():
                continue
            prog = parse(p.read_text(encoding="utf-8"))
            v = decide(prog, use_knowledge=False)
            n_assume = sum(1 for _, _, k in prog.facts if k) + sum(1 for r in getattr(prog, "rules", []) if getattr(r, "knowledge", False))
            n_stmt = len(prog.facts) + len(getattr(prog, "rules", []))
            decided = v.answer in DECIDED
            f0 = ev.evaluate_reasoning_confidence({"confidence": 0.95 if decided else 0.0})
            f1 = ev.evaluate_reasoning_confidence(SimpleNamespace(inference_steps=list(v.proof)),
                                                  {"contradictions": ["contradictory"] if v.answer == "contradictory" else [],
                                                   "assumptions": ["k"] * n_assume})
            out.append({"run": res.stem, "id": row["id"], "k": row["run"], "right": v.answer == row["expected"], "decided": decided,
                        "F0": f0, "F1": f1, "constant": 0.0, "random": rng.random(), "decided_sig": 1.0 if decided else 0.0,
                        "no_rejection": 0.0 if row.get("rejections") else 1.0, "no_corrective": 0.0 if row.get("corrective") else 1.0,
                        "short_program": -float(n_stmt), "short_proof": -float(len(v.proof)), "proof_len": len(v.proof), "assumptions": n_assume})
    try:
        ev.stop()
    except Exception:  # noqa: BLE001
        pass
    return out


def main(argv=None) -> dict:
    rows = collect()
    signals = {"F0 (module as wired: relays the reasoner's confidence)": "F0", "F1 (module's own default model)": "F1",
               "constant": "constant", "random": "random", "decided-or-not": "decided_sig", "no rejection": "no_rejection",
               "no corrective round": "no_corrective", "short program": "short_program", "short proof": "short_proof"}
    subsets = {"all": rows, "decided": [r for r in rows if r["decided"]], "unknown": [r for r in rows if not r["decided"]]}
    out = {"n": {k: len(v) for k, v in subsets.items()}, "right": {k: sum(r["right"] for r in v) for k, v in subsets.items()}, "auroc": {}}
    print(f"programs replayed: {len(rows)} | strict verdict right: {out['right']['all']} | decided {out['n']['decided']} "
          f"(right {out['right']['decided']}) | unknown {out['n']['unknown']} (right {out['right']['unknown']})")
    print(f"F1 values: {sorted({round(r['F1'], 3) for r in rows})[:8]} ... | proof length 0..{max(r['proof_len'] for r in rows)} | "
          f"programs with background-knowledge statements: {sum(r['assumptions'] > 0 for r in rows)}")
    print(f"\n{'signal':58} {'all':>7} {'decided':>8} {'unknown':>8}")
    for label, key in signals.items():
        a = {name: auroc([r[key] for r in sub], [r["right"] for r in sub]) for name, sub in subsets.items()}
        out["auroc"][key] = a
        fmt = lambda x: "   n/a" if x is None else f"{x:6.3f}"
        print(f"{label:58} {fmt(a['all']):>7} {fmt(a['decided']):>8} {fmt(a['unknown']):>8}")
    best = {name: max((out["auroc"][k][name] or 0.0) for k in ("constant", "random", "decided_sig", "no_rejection", "no_corrective",
                                                                "short_program", "short_proof")) for name in ("all", "decided")}
    f1 = out["auroc"]["F1"]
    ok = all((f1[name] or 0.0) >= 0.60 and (f1[name] or 0.0) >= best[name] + 0.05 for name in ("all", "decided"))
    out["best_trivial"], out["pass"] = best, ok
    print(f"\ncriterion (F1 >= 0.60 and >= best trivial control + 0.05, on all and on decided): {'PASS' if ok else 'FAIL'} "
          f"(F1 all {f1['all']:.3f} vs best trivial {best['all']:.3f}; decided {f1['decided']:.3f} vs {best['decided']:.3f})")
    d = ROOT / "tests_lab" / "resultats" / "auditions"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"audition_confidence_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"written: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
