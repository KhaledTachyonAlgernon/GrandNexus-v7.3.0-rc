"""Offline test (no API) of phase B of the living bench (logbook 82): a scripted translator stands in for the LLM. With
the shared lexicon it writes the ontology's names; without it, names that follow the words of the text. Checks the
plumbing: programs into the memories, canonical questions to goals, the trivial control, the concat path."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, "."); sys.path.insert(0, "tools"); sys.path.insert(0, "tests_lab")
import living_llm as B
from scripted_translator import Scripted

fake = Scripted()
out = B.main(["--seed", "11", "--worlds", "2", "--sessions", "8", "--levels", "1,2", "--concat-worlds", "1", "--no-write"], client=fake)
for L in (1, 2):
    r = out["levels"][L]
    assert r["llm_lexicon"]["pct"] == 100 and r["llm_lexicon"]["asserted_errors"] == 0, (L, r["llm_lexicon"])
    assert r["llm_lexicon_bfs"]["pct"] == 100, (L, r["llm_lexicon_bfs"])
    assert r["llm_nolexicon"]["pct"] < r["llm_lexicon"]["pct"], (L, r["llm_nolexicon"])
    assert r["grammar"]["pct"] < 40, (L, r["grammar"])
    assert r["llm_concat"]["n"] > 0
assert fake.calls > 0
print("ALL OK")
