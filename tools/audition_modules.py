#!/usr/bin/env python
"""
Module auditions n°2-4 (logbook 73), offline, 0 API call; item texts are processed by program, never printed.

Data: the archived programs of the FOLIO validation runs (tests_lab/resultats/folio/programs/<run>/<id>_r<k>.nx), the
rows of the same runs (expected label, rejections, corrective rounds), the texts of the same items. Each program is
replayed through the reference engine (strict); Verdict.used gives the statements the proof used, Program.anchors the
span of the text each statement quotes.

  n°2 attention filter (perception.filters.attention_filter): does its salience, focused on the question's words, pick
      the premise sentences the proof cites? unit = (reading, sentence), readings decided and right.
  n°3 linguistic patterns (perception.pattern_recognizer): does the number of patterns its linguistic detector finds
      (premise sentences as history, the question as current text: the detector needs at least two texts) announce a
      wrong reading? unit = reading.
  n°4 reflection (metacognition.reflection, ErrorAnalysisStrategy): fed with the trace of a reading, does the number of
      issues it reports announce a wrong reading? unit = reading.
Criterion for each: AUROC >= 0.60 and >= best trivial control + 0.05.

  python tools/audition_modules.py
"""
from __future__ import annotations

import glob
import json
import logging
import pathlib
import random
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from audition_confidence import auroc                                                     # noqa: E402
from bench_folio import load_items                                                         # noqa: E402
from grandnexus.nexus_logic import decide, parse                                           # noqa: E402

DECIDED = ("yes", "no", "contradictory")
STOP = set("the a an is are was were be been of to in on at by for with and or not no does do did can could will would "
           "should it its this that these those there their they he she his her if then than as from".split())


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z'-]+", s.lower()) if len(w) >= 3 and w not in STOP}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def readings() -> list[dict]:
    items = {it["id"]: it for it in load_items("validation", None)}
    out = []
    for f in sorted(glob.glob(str(ROOT / "tests_lab" / "resultats" / "folio" / "folio_validation_203_*.json"))):
        res = pathlib.Path(f)
        progdir = res.parent / "programs" / res.stem
        if not progdir.is_dir():
            continue
        for row in json.load(open(res, encoding="utf-8"))["rows"].get("translator", []):
            p = progdir / f"{row['id']}_r{row['run']}.nx"
            it = items.get(str(row["id"]))
            if not p.exists() or it is None:
                continue
            prog = parse(p.read_text(encoding="utf-8"))
            v = decide(prog, use_knowledge=False)
            n_know = sum(1 for _, _, k in prog.facts if k) + sum(1 for r in prog.rules if r.knowledge)
            out.append({"run": res.stem, "id": str(row["id"]), "expected": row["expected"], "verdict": v.answer, "right": v.answer == row["expected"],
                        "decided": v.answer in DECIDED, "used": list(v.used), "anchors": dict(prog.anchors), "proof_len": len(v.proof),
                        "statements": prog.n_statements, "knowledge": n_know, "rejections": row.get("rejections", 0) or 0,
                        "corrective": row.get("corrective", 0) or 0, "text": it["text"], "query": it["query"]})
    return out


def table(title: str, signals: dict, labels: list, module_key: str) -> dict:
    res = {k: auroc(v, labels) for k, v in signals.items()}
    controls = {k: a for k, a in res.items() if k != module_key}
    best_key = max(controls, key=lambda k: controls[k] or 0.0)
    m = res[module_key] or 0.0
    ok = m >= 0.60 and m >= (controls[best_key] or 0.0) + 0.05
    print(f"\n{title}  (units {len(labels)}, positives {sum(labels)})")
    for k, a in res.items():
        print(f"   {k:44} {'n/a' if a is None else f'{a:.3f}'}")
    print(f"   criterion (module >= 0.60 and >= best control + 0.05): {'PASS' if ok else 'FAIL'} "
          f"(module {m:.3f}, best control {best_key} {controls[best_key] or 0.0:.3f})")
    return {"auroc": res, "best_control": best_key, "pass": ok, "units": len(labels), "positives": sum(labels)}


def audition_attention(rs: list[dict], rng: random.Random) -> dict:
    from grandnexus.cognition.perception.filters.attention_filter import AttentionFilter, AttentionMode
    af = AttentionFilter()
    sig = {"attention filter salience": [], "word overlap with the question": [], "position (first sentences first)": [],
           "position (last sentences first)": [], "random": []}
    labels = []
    for r in rs:
        if not (r["decided"] and r["right"]):
            continue
        used_spans = [norm(r["anchors"][s]) for s in r["used"] if s in r["anchors"]]
        if not used_spans:
            continue
        sents = sentences(r["text"])
        q = words(r["query"])
        fid = af.create_focus(AttentionMode.TOP_DOWN, target_concepts=sorted(q))
        for i, s in enumerate(sents):
            ns = norm(s)
            labels.append(any(a in ns or ns in a for a in used_spans))
            sig["attention filter salience"].append(float(af.filter(s).attention_score))
            sig["word overlap with the question"].append(len(words(s) & q) / max(1, len(q)))
            sig["position (first sentences first)"].append(-float(i))
            sig["position (last sentences first)"].append(float(i))
            sig["random"].append(rng.random())
        af.remove_focus(fid)
    return table("n°2 attention filter: is the sentence cited by the proof?", sig, labels, "attention filter salience")


def audition_patterns(rs: list[dict], rng: random.Random) -> dict:
    from grandnexus.cognition.perception.pattern_recognizer import LinguisticPatternDetector
    det = LinguisticPatternDetector()
    cache: dict = {}
    sig = {"linguistic patterns found": [], "text length": [], "number of sentences": [], "presence of 'or'": [],
           "presence of 'not'": [], "random": []}
    labels = []
    for r in rs:
        key = r["id"]
        if key not in cache:
            sents = sentences(r["text"])
            cache[key] = len(det.detect(r["query"], [(s, "text", 0.0, {}) for s in sents], {}))
        full = (r["text"] + " " + r["query"]).lower()
        labels.append(not r["right"])
        sig["linguistic patterns found"].append(float(cache[key]))
        sig["text length"].append(float(len(r["text"])))
        sig["number of sentences"].append(float(len(sentences(r["text"]))))
        sig["presence of 'or'"].append(1.0 if re.search(r"\bor\b|\beither\b", full) else 0.0)
        sig["presence of 'not'"].append(1.0 if re.search(r"\bnot\b|n't\b", full) else 0.0)
        sig["random"].append(rng.random())
    out = table("n°3 linguistic patterns: is the reading wrong?", sig, labels, "linguistic patterns found")
    out["patterns_per_item"] = {"min": min(cache.values()), "max": max(cache.values()), "distinct": len(set(cache.values()))}
    return out


def audition_reflection(rs: list[dict], rng: random.Random) -> dict:
    from grandnexus.cognition.metacognition.reflection import ErrorAnalysisStrategy, ReflectionTask, ReflectionType
    strat = ErrorAnalysisStrategy()
    sig = {"issues reported by the reflection": [], "undecided verdict": [], "a rejection": [], "a corrective round": [],
           "long program": [], "short proof": [], "random": []}
    labels, conf = [], []
    for r in rs:
        trace = {"type": "reading", "module": "translator_v5",
                 "message": (f"strict verdict {r['verdict']}; {r['rejections']} rejections; {r['corrective']} corrective rounds; "
                             f"{r['statements']} statements; proof of {r['proof_len']} lines; {r['knowledge']} background-knowledge statements"),
                 "context": {k: r[k] for k in ("verdict", "rejections", "corrective", "statements", "proof_len", "knowledge")},
                 "stack_trace": ""}
        res = strat.reflect(ReflectionTask(reflection_type=ReflectionType.ERROR_ANALYSIS, target_data=trace))
        labels.append(not r["right"])
        sig["issues reported by the reflection"].append(float(len(res.insights) + len(res.recommendations)))
        conf.append(res.confidence)
        sig["undecided verdict"].append(0.0 if r["decided"] else 1.0)
        sig["a rejection"].append(1.0 if r["rejections"] else 0.0)
        sig["a corrective round"].append(1.0 if r["corrective"] else 0.0)
        sig["long program"].append(float(r["statements"]))
        sig["short proof"].append(-float(r["proof_len"]))
        sig["random"].append(rng.random())
    out = table("n°4 reflection (error analysis): is the reading wrong?", sig, labels, "issues reported by the reflection")
    vals = sig["issues reported by the reflection"]
    out["issues"] = {"min": min(vals), "max": max(vals), "distinct": len(set(vals)), "confidence_values": sorted(set(conf))[:5]}
    return out


def main(argv=None) -> dict:
    logging.disable(logging.CRITICAL)
    rs = readings()
    print(f"readings replayed: {len(rs)} | right {sum(r['right'] for r in rs)} | decided {sum(r['decided'] for r in rs)} "
          f"| decided and right {sum(r['decided'] and r['right'] for r in rs)}")
    out = {"n_readings": len(rs),
           "n2_attention_filter": audition_attention(rs, random.Random(2)),
           "n3_linguistic_patterns": audition_patterns(rs, random.Random(3)),
           "n4_reflection_error_analysis": audition_reflection(rs, random.Random(4))}
    d = ROOT / "tests_lab" / "resultats" / "auditions"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"audition_modules_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwritten: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
