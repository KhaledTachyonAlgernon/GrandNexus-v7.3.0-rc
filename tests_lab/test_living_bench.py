"""Offline smoke test of the living bench (logbook 76-78), sandbox: small seeded worlds, 0 API call. Guards the
generators and the pipelines against silent breakage; the numbers of record are in the logbook."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, "."); sys.path.insert(0, "tools")
import living_bench as L

v1 = L.main(["--worlds", "2", "--sessions", "8", "--seed", "3", "--no-write"])["summary"]
assert v1["episodic"]["asserted_errors"] == 0 and v1["episodic"]["right"] > v1["episodic_2025"]["right"], v1["episodic"]
assert v1["concat"]["facts_per_question"] > v1["episodic"]["facts_per_question"]
v2 = L.main(["--world", "v2", "--worlds", "2", "--sessions", "8", "--seed", "3", "--no-write"])["summary"]
for p in ("graph", "semantic"):
    assert v2[p]["right"] == v2[p]["n"] and v2[p]["asserted_errors"] == 0, (p, v2[p])
    assert v2[p]["facts_per_question"] < 4
print("ALL OK")
