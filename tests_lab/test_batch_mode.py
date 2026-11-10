"""Offline test (no API) of the batch mode (logbook 69): with a scripted API, --batch gives exactly the same rows as the
synchronous mode on the learning bench (experience phase + four conditions) and on the FOLIO bench (translator + direct,
2 runs), in at most 4 batches; an interruption while a batch is in flight resumes without a second submission; batch
rows are priced at half."""
import json, pathlib, sys, tempfile
from types import SimpleNamespace
sys.path.insert(0, "."); sys.path.insert(0, "tools")
import bench_folio, bench_learning, cost
from grandnexus.llm_interface.translator_v5 import SYSTEM_DIRECT

CARELESS = '```nx\nbird(X) => fly(X). @ "Every bird in the zoo can fly"\npenguin({n}). @ "{N} is a penguin"\n? fly({n}).\n```'
CAREFUL = ('```nx\nbird(X) => fly(X). @ "Every bird in the zoo can fly"\npenguin({n}). @ "{N} is a penguin"\n'
           'penguin(X) => bird(X). @ "Penguins are birds in the zoo"\npenguin(X) => not fly(X). @ "Penguins cannot fly"\n? fly({n}).\n```')
DOG = '```nx\ndog(X) => bark(X). @ "All dogs bark"\ndog({n}). @ "{N} is a dog"\n? bark({n}).\n```'
NAMES = ["Tweety", "Pingu", "Skipper", "Kowalski", "Rico", "Private", "Rex", "Fido", "Max"]

def item(i):
    n = NAMES[i]
    if i < 6:
        return {"id": str(i), "text": f"Every bird in the zoo can fly. {n} is a penguin. Penguins are birds in the zoo. Penguins cannot fly.",
                "query": f"Can {n} fly?", "expected": "contradictory"}
    return {"id": str(i), "text": f"All dogs bark. {n} is a dog.", "query": f"Does {n} bark?", "expected": "yes"}

def respond(model, max_tokens, system, messages):
    """Deterministic scripted model: the usage depends on the request, so equal rows mean equal requests."""
    sys_text = system[0]["text"] if isinstance(system, list) else system
    u = messages[0]["content"]
    usage = SimpleNamespace(input_tokens=len(u) // 4, output_tokens=7, cache_creation_input_tokens=0, cache_read_input_tokens=len(sys_text) // 4)
    if sys_text == SYSTEM_DIRECT:
        return SimpleNamespace(id="d", model=model, content=[SimpleNamespace(text="yes")], usage=usage)
    n = next(x for x in NAMES if x in u.split("TEXT:")[-1])
    if "is a dog" in u.split("TEXT:")[-1]:
        body = DOG
    else:
        careful = "The engine answered" in u or ("EXAMPLES OF VERIFIED PAST READINGS" in u and "penguin(X) => not fly(X)" in u)
        body = CAREFUL if careful else CARELESS
    return SimpleNamespace(id="t", model=model, content=[SimpleNamespace(text=body.format(n=n.lower(), N=n))], usage=usage)

class Sync:
    def __init__(self): self.messages = self
    def create(self, **kw): return respond(**kw)

class BatchAPI:
    """Fake Message Batches API. `server` is shared between instances: a batch survives the client that submitted it."""
    def __init__(self, server, interrupt_first_wait=False):
        self.messages, self.batches, self.server, self.interrupt = self, self, server, interrupt_first_wait
    def create(self, requests):
        bid = f"msgbatch_{len(self.server) + 1}"
        self.server[bid] = list(requests)
        return SimpleNamespace(id=bid, processing_status="in_progress")
    def retrieve(self, bid):
        if self.interrupt:
            self.interrupt = False
            raise KeyboardInterrupt            # the Colab session dies while the batch is in flight
        return SimpleNamespace(id=bid, processing_status="ended", request_counts=SimpleNamespace(processing=0, succeeded=len(self.server[bid])))
    def results(self, bid):
        for req in self.server[bid]:
            yield SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(type="succeeded", message=respond(**req["params"])))

d = pathlib.Path(tempfile.mkdtemp())
jl = d / "pool.jsonl"
jl.write_text("\n".join(json.dumps(item(i)) for i in range(9)), encoding="utf-8")
KEEP = ("id", "expected", "pred", "pred_full", "n_examples", "shown", "same_story", "rejections", "calls", "tokens_in", "tokens_out", "cache_read", "cache_write")

def learning(out, client, batch):
    args = ["--jsonl", str(jl), "--exp-n", "5", "--test-n", "4", "--k", "1", "--exp-seed", "1", "--out", str(d / out)] + (["--batch"] if batch else [])
    s = bench_learning.main(args, client=client)
    rows = json.load(open(next((d / out).glob("learning_*.json"))))["rows"]
    return s, rows

s_sync, r_sync = learning("sync", Sync(), False)
server = {}
s_batch, r_batch = learning("batch", BatchAPI(server), True)
for c in ("none", "static", "random", "learned"):
    a = [{k: r.get(k) for k in KEEP} for r in r_sync[c]]; b = [{k: r.get(k) for k in KEEP} for r in r_batch[c]]
    assert a == b, f"learning bench, condition {c}: batch rows differ from the synchronous rows"
    assert all(r["batch"] for r in r_batch[c]) and not any(r.get("batch") for r in r_sync[c])
assert s_batch["memory_size"] == s_sync["memory_size"] and s_batch["experience"] == s_sync["experience"], (s_batch["experience"], s_sync["experience"])
assert 1 <= len(server) <= 4 and s_batch["batches"] == len(server), f"{len(server)} batches"
assert not list((d / "batch").glob("batch_state_*.json")), "the batch state is removed once the results are written"
t_sync, t_batch = s_sync["cost"]["total"], s_batch["cost"]["total"]
assert t_batch["batch"] and abs(t_batch["usd"] - 0.5 * t_sync["usd"]) < 1e-4, (t_batch, t_sync)

# interruption while the first batch is in flight, then the same command again: nothing is submitted twice
server2 = {}
try:
    learning("resume", BatchAPI(server2, interrupt_first_wait=True), True)
    raise AssertionError("the interruption did not propagate")
except KeyboardInterrupt:
    pass
assert len(server2) == 1 and list((d / "resume").glob("batch_state_*.json")), "one batch in flight, state on disk"
s_res, r_res = learning("resume", BatchAPI(server2), True)
assert len(server2) == len(server), f"resume submitted {len(server2)} batches instead of {len(server)}"
assert [r["pred"] for r in r_res["learned"]] == [r["pred"] for r in r_sync["learned"]]

# FOLIO bench: translator + direct, 2 runs
def folio(out, client, batch):
    args = ["--jsonl", str(jl), "--modes", "translator,direct", "--runs", "2", "--strict", "--out", str(d / out), "--model", "claude-sonnet-5-5"] + (["--batch"] if batch else [])
    s = bench_folio.main(args, client=client)
    return s, json.load(open(next((d / out).glob("local_*.json"))))["rows"]
KEEP_F = ("id", "expected", "run", "pred", "calls", "tokens_in", "tokens_out", "cache_read", "cache_write")
fs, fr = folio("fsync", Sync(), False)
server3 = {}
fb, frb = folio("fbatch", BatchAPI(server3), True)
for m in ("translator", "direct", "always_unknown", "majority", "random"):
    assert [{k: r.get(k) for k in KEEP_F} for r in fr[m]] == [{k: r.get(k) for k in KEEP_F} for r in frb[m]], f"FOLIO bench, mode {m}"
assert 1 <= len(server3) <= 4 and fb["batches"] == len(server3)
assert abs(fb["cost"]["total"]["usd"] - 0.5 * fs["cost"]["total"]["usd"]) < 1e-4
assert cost.cost_usd({"tokens_in": 1_000_000, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "calls": 1, "batch": True}, "claude-sonnet-5-5")["usd"] == 1.0
print("ALL OK")
