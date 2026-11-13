"""Offline test (no API) of the level-1 diagnosis tool (logbook 86) with the scripted translator on the debug seed 5:
every fact, reading and question is logged, and seed 13 (the measured worlds) is refused."""
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
try:
    D.main(["--seed", "13", "--dry-run"])
    raise AssertionError("seed 13 accepted")
except SystemExit:
    pass
print("ALL OK")
