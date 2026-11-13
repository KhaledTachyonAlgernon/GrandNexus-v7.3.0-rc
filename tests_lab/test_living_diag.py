"""Offline test (no API) of the level-1 diagnosis tool (logbook 86) with the scripted translator on the debug seed 5:
every fact, reading and question is logged, and seed 13 (the measured worlds) is refused.
Logbook 90: a reading that fails after the retries counts its facts as not read (the gate's denominator is every fact
of the bench), moves come from the world, and the gate of an archived run can be recomputed with 0 API call."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, "."); sys.path.insert(0, "tools"); sys.path.insert(0, "tests_lab")
import living_diag as D
from scripted_translator import Scripted
out = D.main(["--seed", "5", "--worlds", "2", "--sessions", "8", "--level", "1", "--no-write"], client=Scripted())
w = out["worlds"][0]
assert w["facts"] and w["questions"] and w["sessions"]
assert all(f["read_as_expected"] for f in w["facts"]), [f for f in w["facts"] if not f["read_as_expected"]][:2]
assert out["right"] == out["n"] and out["asserted_errors"] == 0
assert all("form" in f and f["form"] is not None for f in w["facts"])
v2 = D.main(["--seed", "5", "--worlds", "2", "--sessions", "8", "--level", "1", "--paraphraser", "2", "--ontology", "2", "--gate", "--no-write"],
           client=Scripted())
assert v2["gate"]["pass"] and v2["right"] == v2["n"], v2.get("gate")
assert any("'s home is in" in f["surface"] for w in v2["worlds"] for f in w["facts"]), "paraphraser v2 not used"
assert not any("has a flat in" in f["surface"] for w in v2["worlds"] for f in w["facts"])
assert any("has a flat in" in f["surface"] for w in out["worlds"] for f in w["facts"]), "v1 by default"
# logbook 90: readings that fail after the retries (API unavailable)
import grandnexus.llm_interface.translator_v5 as T
from types import SimpleNamespace
T.SLEEP = lambda s: None
class Down(Scripted):
    """The scripted reader behind an API that is unavailable for the sessions whose text contains a marker."""
    def __init__(self, markers):
        super().__init__(); self.markers, self.refused = markers, 0
    def create(self, model, max_tokens, system, messages):
        if any(m in messages[0]["content"] for m in self.markers):
            self.refused += 1
            e = type("ServiceUnavailableError", (Exception,), {})("down"); e.status_code = 503
            raise e
        return super().create(model, max_tokens, system, messages)
args = ["--seed", "5", "--worlds", "2", "--sessions", "8", "--level", "1", "--paraphraser", "2", "--ontology", "2", "--gate", "--no-write"]
w0 = v2["worlds"][0]
first = [f for f in w0["facts"] if f["rel"] == "lives in" and not f["move"]]
movers = [f["surface"].split("'")[0].split()[0] for f in first
          if any(g["rel"] == "lives in" and g["move"] and g["surface"].startswith(f["surface"].split("'")[0].split()[0])
                 and g["session"] > f["session"] for g in w0["facts"])]
assert movers, "debug world 0 must hold a person who moves in a later session"
target = next(f for f in first if f["surface"].startswith(movers[0]))
down = Down([target["surface"]])
v3 = D.main(args, client=down)
assert down.refused == len(T.DEFAULT_RETRY_WAITS) + 1, down.refused        # retried, then given up
assert v3["failed"]["readings"] == 1 and v3["failed"]["facts_in_failed_readings"] >= 1
lost = [f for w in v3["worlds"] for f in w["facts"] if f["reading_failed"]]
assert lost and not any(f["read_as_expected"] for f in lost)
n_facts = lambda o: sum(len(w["facts"]) for w in o["worlds"])
assert n_facts(v3) == n_facts(v2), "every fact of the bench stays in the log"
assert v3["gate"]["n_first_residences"] == v2["gate"]["n_first_residences"], "moves come from the world, not the readings"
assert v3["gate"]["first_residences"] < 1.0 and v3["gate"]["failed_readings"] == 1
moved_later = [f for f in v3["worlds"][0]["facts"] if f["rel"] == "lives in" and f["surface"].startswith(movers[0])
               and f["session"] > target["session"]]
assert moved_later and all(f["move"] for f in moved_later), "a move after a failed first reading is still a move"
# the whole API down: the gate fails, it is never computed on nothing
v4 = D.main(args, client=Down(["TEXT:"]))
assert v4["failed"]["readings"] == v4["failed"]["readings_total"] and not v4["gate"]["pass"]

# the replay of the archived runs (0 API call) reproduces logbook 87 and recomputes the gate of logbook 89
import glob
a87 = sorted(glob.glob("tests_lab/resultats/living/living_diag_L1_2026-11-12_*.json"))
a89 = sorted(glob.glob("tests_lab/resultats/living/living_diag_L1_2026-11-13_*.json"))
if a87 and a89:
    r87 = D.main(["--regate", a87[0], "--no-write"])["repaired"]
    assert (round(r87["first_residences"] * r87["n_first_residences"]), r87["n_first_residences"]) == (56, 90), r87
    assert (round(r87["role_facts"] * r87["n_role_facts"]), r87["n_role_facts"]) == (157, 163), r87
    r89 = D.main(["--regate", a89[0], "--no-write"])
    assert r89["archived"]["pass"] and not r89["repaired"]["pass"] and r89["repaired"]["failed_readings"] == 50
    ok = r89["successful_readings_only"]
    assert (ok["n_first_residences"], ok["first_residence_misses"], ok["of_which_superseded_in_session"]) == (55, 3, 3), ok
else:
    print("archived diagnosis runs absent: replay not checked")

try:
    D.main(["--seed", "13", "--dry-run"])
    raise AssertionError("seed 13 accepted")
except SystemExit:
    pass
print("ALL OK")
