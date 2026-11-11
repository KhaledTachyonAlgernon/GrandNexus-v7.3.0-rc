"""Offline smoke test of the living bench lab version (logbook 79-80) on the debug seed 5 (never the measured seed 7):
the extraction keeps the structure, and the structured pipelines answer without asserted error with few facts."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, "."); sys.path.insert(0, "tools")
import living_lab as L
out = L.main(["--seed", "5", "--worlds", "2", "--sessions", "8", "--no-write"])
assert out["criteria"]["C0"], out["fidelity"]
s = out["summary"]
for p in ("bfs+script", "graph+episodic", "semantic+episodic"):
    assert s[p]["asserted_errors"] == 0 and s[p]["pct"] >= 95 and s[p]["facts_per_question"] < 4, (p, s[p])
assert s["concat"]["facts_per_question"] > 5 * s["graph+episodic"]["facts_per_question"]
print("ALL OK")
