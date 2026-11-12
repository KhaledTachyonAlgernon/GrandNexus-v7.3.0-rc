"""Offline test (no API) of phase C (logbook 84) on the debug seed 5: the scripted translator stands in for the LLM;
the batch path gives exactly the synchronous results; an interruption while a batch is in flight resumes without a
second submission of what was already submitted."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, "."); sys.path.insert(0, "tools"); sys.path.insert(0, "tests_lab")
import living_lab_language as C
from scripted_translator import Scripted, BatchAPI

ARGS = ["--seed", "5", "--worlds", "2", "--sessions", "8", "--levels", "1,2", "--concat-worlds", "1", "--no-write"]
sync = C.main(ARGS, client=Scripted())
for L in (1, 2):
    lv = sync["levels"][L]
    assert lv["llm_lexicon"]["pct"] == 100 and lv["llm_lexicon"]["asserted_errors"] == 0, lv["llm_lexicon"]
    assert lv["llm_nolexicon"]["pct"] < lv["llm_lexicon"]["pct"] and lv["grammar"]["pct"] < 40
    assert sync["criteria"][L]["C1"] and sync["criteria"][L]["C3"], sync["criteria"][L]
server = {}
batch = C.main(ARGS + ["--batch"], client=BatchAPI(server))
assert batch["levels"] == sync["levels"] and batch["criteria"] == sync["criteria"], "batch results differ from synchronous ones"
assert batch["batches"] == len(server) >= 8, batch["batches"]                     # the lexicon chains are sequential
server2 = {}
try:
    C.main(ARGS + ["--batch"], client=BatchAPI(server2, interrupt_first_wait=True))
    raise AssertionError("the interruption did not propagate")
except KeyboardInterrupt:
    pass
assert len(server2) == 1
resumed = C.main(ARGS + ["--batch"], client=BatchAPI(server2))
assert len(server2) == len(server) and resumed["levels"] == sync["levels"], (len(server2), len(server))
print("ALL OK")
