#!/usr/bin/env python
"""
The two boot profiles side by side, against the criteria fixed in logbook 64 (offline, 0 API call, no item text printed).

Each profile x mode (laboratory, live) runs in a fresh Python process: boot time, grandnexus modules imported, threads
after boot, the answers on the offline frozen sets (grammar pathway) and on scripted nx readings (an injected
translator_v5 whose client returns fixed programs), shutdown time, threads left. Then:
  C-equivalence  same answer, item by item, in both profiles
  C-footprint    minimal: <= 20 modules, boot < 1 s, <= 2 threads after boot, shutdown < 0.5 s, no thread left
  C-tags         every module tagged once; the minimal profile imports only core / supported modules at run time;
                 no core module (boot.py excepted) imports an experimental or archive module (PEP 562 lazy exports
                 are reported apart, logbook 65)
  no regression  the full profile still boots with every step OK
Writes tests_lab/resultats/boot/boot_profiles_<date>.json.

  python tools/boot_profiles.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FROZEN_SETS = ("tests_lab/temoin_khaled_2026-10-16.json", "tests_lab/temoin_khaled_2026-10-16_labels_v2.json",
               "tests_lab/holdout_extracteur.json")
# scripted nx readings: synthetic texts, not test items; the anchors are in the texts
SCRIPTED = [
    ("All dogs bark. Rex is a dog. Does Rex bark?",
     'dog(X) => bark(X). @ "All dogs bark"\ndog(rex). @ "Rex is a dog"\n? bark(rex).'),
    ("No cat can fly. Tom is a cat. Can Tom fly?",
     'cat(X) => not fly(X). @ "No cat can fly"\ncat(tom). @ "Tom is a cat"\n? fly(tom).'),
    ("Mia is a pianist or a violinist. Mia is not a pianist. Is Mia a violinist?",
     'pianist(mia) | violinist(mia). @ "Mia is a pianist or a violinist"\nnot pianist(mia). @ "Mia is not a pianist"\n? violinist(mia).'),
    ("Some birds sing. Tweety is a bird. Does Tweety sing?",
     'bird(tweety). @ "Tweety is a bird"\n? sing(tweety).'),
]
LIMITS = {"modules": 20, "boot_s": 1.0, "threads_after_boot": 2, "shutdown_s": 0.5, "threads_left": 0}

WORKER = r'''
import json, logging, sys, threading, time
from types import SimpleNamespace
sys.path.insert(0, ROOT)
profile, live = PROFILE, LIVE
t0 = time.time()
from grandnexus.boot import boot
from grandnexus.llm_interface.translator_v5 import Translator
programs = {text: prog for text, prog in SCRIPTED}

class Scripted:
    def __init__(self): self.messages = self
    def create(self, model, max_tokens, system, messages):
        tail = messages[0]["content"].split("TEXT:")[-1]
        prog = next(p for t, p in programs.items() if t.split(".")[0] in tail)
        return SimpleNamespace(id="scripted", model="scripted", content=[SimpleNamespace(text="```nx\n" + prog + "\n```")],
                               usage=SimpleNamespace(input_tokens=0, output_tokens=0))

gn = boot(log_level=logging.CRITICAL, llm="off", profile=profile, start_core=live, nx_translator=Translator(client=Scripted()))
t1 = time.time()
mods_boot = sorted(m for m in sys.modules if m.startswith("grandnexus"))
threads_boot = threading.active_count() - 1
tr = gn.modules()["text_reasoner"]
answers = {}
for f in FROZEN:
    items = json.load(open(ROOT + "/" + f, encoding="utf-8"))["items"]
    for i, it in enumerate(items):
        r = tr.answer(it[0], mode="grammar")
        answers[f"{f.rsplit('/', 1)[-1]}#{i}"] = r.get("answer") if isinstance(r, dict) else str(r)
for i, (text, _) in enumerate(SCRIPTED):
    r = tr.answer(text, mode="nx")
    answers[f"scripted_nx#{i}"] = r.get("answer") if isinstance(r, dict) else str(r)
mods_run = sorted(m for m in sys.modules if m.startswith("grandnexus"))
steps_ok, steps = sum(s.ok for s in gn.report), len(gn.report)
t2 = time.time(); gn.shutdown(); t3 = time.time()
time.sleep(0.5)
left = [t.name for t in threading.enumerate() if t is not threading.main_thread() and t.is_alive()]
print("@@" + json.dumps({"boot_s": round(t1 - t0, 3), "modules": len(mods_run), "modules_at_boot": len(mods_boot),
      "module_list": mods_run, "threads_after_boot": threads_boot, "shutdown_s": round(t3 - t2, 3), "threads_left": len(left),
      "threads_left_names": left, "steps_ok": steps_ok, "steps": steps, "answers": answers}))
'''


def run_worker(profile: str, live: bool) -> dict:
    code = (WORKER.replace("ROOT)", repr(str(ROOT)) + ")").replace("ROOT +", repr(str(ROOT)) + " +")
            .replace("PROFILE, LIVE", f"{profile!r}, {live!r}").replace("FROZEN", repr(list(FROZEN_SETS)))
            .replace("SCRIPTED", repr(SCRIPTED)))
    p = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=600)
    line = next((l for l in p.stdout.splitlines() if l.startswith("@@")), None)
    if line is None:
        raise RuntimeError(f"worker {profile}/{'live' if live else 'lab'} failed:\n{p.stderr[-1500:]}")
    return json.loads(line[2:])


def main(argv=None) -> dict:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-write", action="store_true", help="do not write the result file (offline test)")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from grandnexus import module_status as M
    res = {}
    for profile in ("full", "minimal"):
        for live in (False, True):
            key = f"{profile}/{'live' if live else 'lab'}"
            res[key] = run_worker(profile, live)
            r = res[key]
            print(f"{key:13} boot {r['boot_s']:5.2f}s | modules {r['modules']:3} | threads after boot {r['threads_after_boot']:2} | "
                  f"shutdown {r['shutdown_s']:5.2f}s | threads left {r['threads_left']} | steps {r['steps_ok']}/{r['steps']}")
    out = {"results": res, "criteria": {}}
    # C-equivalence
    diffs = []
    for mode in ("lab", "live"):
        a, b = res[f"full/{mode}"]["answers"], res[f"minimal/{mode}"]["answers"]
        diffs += [f"{mode}:{k}" for k in a if a[k] != b.get(k)]
    n_items = len(res["full/lab"]["answers"])
    out["criteria"]["C-equivalence"] = {"pass": not diffs, "items": n_items, "differences": diffs}
    # C-footprint
    bad = []
    for mode in ("lab", "live"):
        r = res[f"minimal/{mode}"]
        for k, lim in LIMITS.items():
            ok = r[k] < lim if k.endswith("_s") else r[k] <= lim
            if not ok:
                bad.append(f"{mode}: {k} = {r[k]} (limit {lim})")
    out["criteria"]["C-footprint"] = {"pass": not bad, "failures": bad}
    # C-tags
    st = M.status()
    outside = sorted(m for m in res["minimal/lab"]["module_list"] + res["minimal/live"]["module_list"]
                     if st.get(m, ("unknown",))[0] not in ("core", "supported"))
    chk = M.check()
    out["criteria"]["C-tags"] = {"pass": not outside and not chk["core_imports_outside_core"] and not chk["tags_naming_missing_modules"],
                                 "modules": len(st), "runtime_outside_core_or_supported": sorted(set(outside)), **chk}
    # no regression of the full profile
    out["criteria"]["full profile unchanged"] = {"pass": all(res[f"full/{m}"]["steps_ok"] == res[f"full/{m}"]["steps"] for m in ("lab", "live")),
                                                 "steps": {m: f"{res[f'full/{m}']['steps_ok']}/{res[f'full/{m}']['steps']}" for m in ("lab", "live")}}
    print()
    for name, c in out["criteria"].items():
        detail = {k: v for k, v in c.items() if k != "pass" and v not in ([], {}, "")}
        print(f"{name:24} {'PASS' if c['pass'] else 'FAIL'}  {json.dumps(detail)[:300]}")
    if args.no_write:
        return out
    d = ROOT / "tests_lab" / "resultats" / "boot"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"boot_profiles_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwritten: {path.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    main()
