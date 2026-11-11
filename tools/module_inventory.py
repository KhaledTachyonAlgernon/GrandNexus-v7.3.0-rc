#!/usr/bin/env python
"""
Inventory of the experimental modules (module review, logbook 72), offline, 0 API call, no item text read.

For every module tagged experimental in grandnexus/module_status.py: family, lines, classes and public methods,
first line of the docstring, who imports it (package, tools, tests), whether the full boot loads it, whether it
imports, and a lifecycle probe in a fresh process: instantiate each class whose constructor needs no argument, call
start() when it exists, then stop() / shutdown(), and count the threads left. Each module gets a path to the verdict:
  direct      it can change a step of the core pathway (text -> premises -> program -> engine -> verdict):
              auditionable on FOLIO, often for free on the archived programs
  over time   it only makes sense across several sessions (memories, learning, graph): the future "living" bench
  agent       agent infrastructure (sensors, actuators, clock, security, ops, orchestration): no verdict to change;
              only the lifecycle is checked
Writes tests_lab/resultats/auditions/module_inventory_<date>.json and AUDITIONS.md (inventory part).

  python tools/module_inventory.py
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grandnexus import module_status as M                                                  # noqa: E402

DIRECT_FAMILIES = ("grandnexus.cognition.perception", "grandnexus.cognition.reasoning", "grandnexus.cognition.metacognition")
OVER_TIME_FAMILIES = ("grandnexus.memory", "grandnexus.cognition.learning", "grandnexus.graph", "grandnexus.evolution",
                      "grandnexus.distributed")
OVERRIDES = {   # module -> (path, why), where the family is not the right guide
    "grandnexus.cognition.perception.code_analyzer": ("agent", "analyses source code, not the text of a problem"),
    "grandnexus.cognition.reasoning.planning": ("agent", "plans actions; no step of a deduction"),
    "grandnexus.cognition.metacognition.self_model": ("over time", "model of the agent itself across sessions"),
    "grandnexus.cognition.metacognition.affect_regulator": ("over time", "affective state regulated over time"),
    "grandnexus.cognition.metacognition.adaptation": ("over time", "adapts parameters from accumulated performance"),
}

PROBE = r'''
import importlib, inspect, json, logging, sys, threading, time
logging.disable(logging.CRITICAL)
sys.path.insert(0, ROOT)
name = NAME
out = {"imports": False, "classes": {}}
before = set(threading.enumerate())
try:
    mod = importlib.import_module(name)
    out["imports"] = True
except BaseException as e:
    out["import_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    print("@@" + json.dumps(out)); sys.exit(0)
for cname, cls in inspect.getmembers(mod, inspect.isclass):
    if cls.__module__ != name or cname.startswith("_"):
        continue
    rec = {}
    try:
        sig = inspect.signature(cls)
        if any(p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
               for p in sig.parameters.values()):
            rec["instantiable"] = "needs arguments"
            out["classes"][cname] = rec
            continue
        if issubclass(cls, BaseException) or getattr(cls, "__abstractmethods__", None):
            continue
        obj = cls()
        rec["instantiable"] = "yes"
        for meth in ("start", "initialize"):
            f = getattr(obj, meth, None)
            if callable(f):
                try:
                    if not [p for p in inspect.signature(f).parameters.values() if p.default is inspect._empty]:
                        f(); rec[meth] = "ok"
                except BaseException as e:
                    rec[meth] = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(0.2)
        for meth in ("stop", "shutdown"):
            f = getattr(obj, meth, None)
            if callable(f):
                try:
                    if not [p for p in inspect.signature(f).parameters.values() if p.default is inspect._empty]:
                        f(); rec[meth] = "ok"; break
                except BaseException as e:
                    rec[meth] = f"{type(e).__name__}: {str(e)[:80]}"
    except BaseException as e:
        rec["instantiable"] = f"{type(e).__name__}: {str(e)[:80]}"
    out["classes"][cname] = rec
time.sleep(0.5)
left = [t.name for t in threading.enumerate() if t not in before and t.is_alive()]
out["threads_left"] = len(left)
out["threads_left_names"] = left[:5]
print("@@" + json.dumps(out))
'''


def path_of(name: str) -> tuple[str, str]:
    if name in OVERRIDES:
        return OVERRIDES[name]
    if name.startswith(DIRECT_FAMILIES):
        return "direct", "perception, reasoning or metacognition: can act on a step of the pathway"
    if name.startswith(OVER_TIME_FAMILIES):
        return "over time", "memory, learning, graph: makes sense across sessions"
    return "agent", "agent infrastructure"


def static_info(path: pathlib.Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc = (ast.get_docstring(tree) or "").strip().splitlines()
    classes = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            classes[node.name] = sum(1 for b in node.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and not b.name.startswith("_"))
    return {"doc": next((l for l in doc if l.strip()), "")[:140], "classes": classes}


def importers(target: str, mods: dict) -> list[str]:
    out = []
    for name, p in mods.items():
        if name != target and target in M.imports_of(p, name, mods, lazy="include"):
            out.append(name)
    short = target.rsplit(".", 1)[-1]
    for p in list((ROOT / "tools").glob("*.py")) + list((ROOT / "tests_lab").glob("*.py")):
        if p.name == "module_inventory.py":
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if target in txt or f"import {short}" in txt or f".{short} import" in txt:
            out.append(f"{p.parent.name}/{p.name}")
    return sorted(out)


def main(argv=None) -> dict:
    st, mods = M.status(), M.package_modules()
    boot = sorted((ROOT / "tests_lab" / "resultats" / "boot").glob("boot_profiles_*.json"))
    full = set(json.loads(boot[-1].read_text())["results"]["full/lab"]["module_list"]) if boot else set()
    rows = {}
    exp = sorted(n for n, (t, _) in st.items() if t == "experimental")
    for i, name in enumerate(exp, 1):
        info = static_info(mods[name])
        lines = sum(1 for _ in open(mods[name], encoding="utf-8"))
        rec = {"family": ".".join(name.split(".")[1:3]) if name.count(".") >= 3 else name.split(".")[1], "lines": lines, **info,
               "path": path_of(name)[0], "path_why": path_of(name)[1], "loaded_by_full_boot": name in full,
               "importers": importers(name, mods)}
        if lines:
            code = PROBE.replace("ROOT)", repr(str(ROOT)) + ")").replace("NAME", repr(name))
            try:
                with tempfile.TemporaryDirectory() as tmp:   # modules may write files in the working directory
                    p = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True, timeout=60, cwd=tmp)
                line = next((l for l in p.stdout.splitlines() if l.startswith("@@")), None)
                rec["probe"] = json.loads(line[2:]) if line else {"error": (p.stderr or "no output")[-160:]}
            except subprocess.TimeoutExpired:
                rec["probe"] = {"error": "timeout (60 s)"}
        rows[name] = rec
        print(f"  {i:2}/{len(exp)} {name}", file=sys.stderr)
    out = {"date": time.strftime("%Y-%m-%d %H:%M"), "modules": rows}
    d = ROOT / "tests_lab" / "resultats" / "auditions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"module_inventory_{time.strftime('%Y-%m-%d_%H%M%S')}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = main()["modules"]
    real = {n: r for n, r in res.items() if r["lines"]}
    from collections import Counter
    print(f"experimental modules: {len(res)} ({len(res) - len(real)} empty package files)")
    print("path to the verdict:", dict(Counter(r["path"] for r in real.values())))
    print("import OK:", sum(r.get("probe", {}).get("imports", False) for r in real.values()), "/", len(real),
          "| loaded by the full boot:", sum(r["loaded_by_full_boot"] for r in real.values()),
          "| imported by nobody:", sum(not r["importers"] for r in real.values()),
          "| threads left after the probe:", sum(1 for r in real.values() if r.get("probe", {}).get("threads_left", 0)))
