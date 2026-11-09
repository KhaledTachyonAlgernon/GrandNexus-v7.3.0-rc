"""Offline test (no API) of the prompt cache and the cost accounting (logbook 63): the system prompt is sent as one
cached block (or as plain text with cache_system=False), the usage fields of the API (cache reads and writes) reach the
answer and the bench rows, and tools/cost.py prices them."""
import sys
from types import SimpleNamespace
sys.path.insert(0, "."); sys.path.insert(0, "tools")
from grandnexus.llm_interface.translator_v5 import Translator, SYSTEM_TRANSLATE
import cost

PROG = '```nx\ndog(X) => bark(X). @ "All dogs bark"\ndog(rex). @ "Rex is a dog"\n? bark(rex).\n```'

class Cached:
    """Fake API: records what it was sent; the first call writes the cache, the next ones read it."""
    def __init__(self): self.messages, self.sent = self, []
    def create(self, model, max_tokens, system, messages):
        self.sent.append(system)
        first = len(self.sent) == 1
        u = SimpleNamespace(input_tokens=40, output_tokens=60, cache_creation_input_tokens=1400 if first else 0,
                            cache_read_input_tokens=0 if first else 1400)
        return SimpleNamespace(id=f"m{len(self.sent)}", model=model, content=[SimpleNamespace(text=PROG)], usage=u)

c = Cached()
tr = Translator(client=c, model="claude-sonnet-5-5")
r1 = tr.answer("All dogs bark. Rex is a dog.", "Does Rex bark?")
r2 = tr.answer("All dogs bark. Rex is a dog.", "Does Rex bark?")
assert r1["verdict_strict"] == "yes" == r2["verdict_strict"]
blk = c.sent[0]
assert isinstance(blk, list) and blk[0]["text"] == SYSTEM_TRANSLATE and blk[0]["cache_control"] == {"type": "ephemeral"}, blk
assert (r1["cache_write"], r1["cache_read"], r2["cache_write"], r2["cache_read"]) == (1400, 0, 0, 1400)
assert r1["tokens_in"] == 40 and r1["tokens_out"] == 60

plain = Cached()
Translator(client=plain, cache_system=False).answer("All dogs bark. Rex is a dog.", "Does Rex bark?")
assert plain.sent[0] == SYSTEM_TRANSLATE, "cache_system=False sends the plain system string"

# an old-style fake without cache fields still works (fields default to 0)
class Old:
    def __init__(self): self.messages = self
    def create(self, **kw):
        return SimpleNamespace(id="o", model="fake", content=[SimpleNamespace(text=PROG)], usage=SimpleNamespace(input_tokens=5, output_tokens=7))
r = Translator(client=Old()).answer("All dogs bark. Rex is a dog.", "Does Rex bark?")
assert (r["cache_read"], r["cache_write"], r["tokens_in"]) == (0, 0, 5)

# pricing: Sonnet 5.5, $2 input, $10 output, $2.50 cache write, $0.10 cache read per million tokens
u = {"tokens_in": 1_000_000, "tokens_out": 100_000, "cache_read": 2_000_000, "cache_write": 0, "calls": 10}
p = cost.cost_usd(u, "claude-sonnet-5-5")
assert abs(p["usd"] - (2.0 + 1.0 + 0.2)) < 1e-9 and abs(p["usd_without_cache"] - (6.0 + 1.0)) < 1e-9, p
rows = [{"calls": 1, "tokens_in": 40, "tokens_out": 60, "cache_read": 1400, "cache_write": 0}]
assert cost.usage(rows)["cache_read"] == 1400 and cost.usage([{"calls": 1, "tokens": 9}]) is None
rc = cost.from_receipts(tr.receipts, "claude-sonnet-5-5")
assert rc["calls"] == 2 and rc["usd"] < rc["usd_without_cache"]
print("ALL OK")
