"""Offline test (no API) of the story-aware bench (logbook 56): content shas ignore derived fields, the story modes draw
what they claim, and an interrupted test phase resumes from its checkpoint without re-reading what was measured."""
import json, os, pathlib, sys, tempfile
from types import SimpleNamespace
sys.path.insert(0, "."); sys.path.insert(0, "tools")
from bench_folio import freeze, story_key, load_items
import bench_learning as B
from grandnexus.cognition.experience import Experience, ExperienceMemory

NAMES = ["Rex", "Fido", "Max", "Bella", "Luna", "Milo", "Oscar", "Daisy"]
PROG = '```nx\ndog(X) => bark(X). @ "All dogs bark"\ndog({n}). @ "{N} is a dog"\n? bark({n}).\n```'
PROG2 = '```nx\ndog(X) => bark(X). @ "All dogs bark"\ndog({n}). @ "{N} is a dog"\n? dog({n}).\n```'
d = pathlib.Path(tempfile.mkdtemp())
# a synthetic FOLIO split: one story (premises text) per name, two conclusions per story
rows = []
for i, n in enumerate(NAMES):
    prem = f"All dogs bark. {n} is a dog."
    rows.append({"story_id": i, "premises": prem, "conclusion": f"{n} barks.", "label": "True", "example_id": 2 * i})
    rows.append({"story_id": i, "premises": prem, "conclusion": f"{n} is a dog.", "label": "True", "example_id": 2 * i + 1})
(d / "folio_v2_train.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
os.environ["FOLIO_DIR"] = str(d)
items = load_items("train", None)
assert len(items) == 16 and len({it["story"] for it in items}) == 8, "story keys"
assert story_key("All dogs  bark.\n Rex is a dog.") == story_key("All dogs bark. Rex is a dog."), "story key normalises whitespace"
assert freeze(items) == freeze([{k: it[k] for k in ("id", "text", "query", "expected")} for it in items]), "freeze ignores derived fields"

# a memory holding corrected readings for the first 3 stories (one conclusion each)
mem = ExperienceMemory([Experience(items[2 * i]["text"], items[2 * i]["query"], PROG.format(n=NAMES[i].lower(), N=NAMES[i]), "yes",
                                   "unknown", ["dog(X) => bark(X)."], items[2 * i]["id"]) for i in range(3)])
mem_path = d / "memory.json"; mem.save(str(mem_path))
out = d / "out"
common = ["--split", "train", "--memory", str(mem_path), "--exp-n", "0", "--test-n", "0", "--k", "1", "--out", str(out)]
r_in = B.main(common + ["--story-mode", "in-memory", "--dry-run"])
r_dis = B.main(common + ["--story-mode", "disjoint", "--dry-run"])
r_any = B.main(common + ["--story-mode", "any", "--dry-run"])
assert (r_in["n_test"], r_in["same_story_items"]) == (3, 3), f"in-memory: {r_in}"       # the other conclusion of each memorised story
assert (r_dis["n_test"], r_dis["same_story_items"]) == (10, 0), f"disjoint: {r_dis}"    # the 5 untouched stories, 2 conclusions each
assert (r_any["n_test"], r_any["same_story_items"]) == (13, 3), f"any: {r_any}"
# exclusion by an earlier result and by a memory file
first = B.main(common + ["--story-mode", "any", "--test-n", "4", "--dry-run"])
assert first["n_test"] == 4

class Reader:
    """Scripted reader: always the right program; raises KeyboardInterrupt (a Colab interruption) after `stop` calls."""
    def __init__(self, stop=None): self.messages, self.calls, self.stop = self, 0, stop
    def create(self, model, max_tokens, system, messages):
        self.calls += 1
        if self.stop is not None and self.calls > self.stop:
            raise KeyboardInterrupt
        u = messages[0]["content"]; tail = u.split("TEXT:")[-1]
        n = next(x for x in NAMES if x in tail)
        body = (PROG2 if "QUESTION:" in tail and "is a dog" in tail.split("QUESTION:")[-1] else PROG).format(n=n.lower(), N=n)
        return SimpleNamespace(id="fake", model=model, content=[SimpleNamespace(text=body)], usage=SimpleNamespace(input_tokens=1, output_tokens=1))

args = common + ["--story-mode", "any", "--conditions", "none,learned"]
try:
    B.main(args, client=Reader(stop=7))            # 2 conditions per item: interrupted inside the 4th item
    raise AssertionError("the interruption did not propagate")
except KeyboardInterrupt:
    pass
ck = list(out.glob("checkpoint_test_*.json"))
assert len(ck) == 1 and len(json.loads(ck[0].read_text())["rows"]["none"]) == 3, "checkpoint after 3 complete items"
second = Reader()
s = B.main(args, client=second)
assert second.calls == 2 * (13 - 3), f"resume re-read {second.calls // 2} items instead of 10"
assert s["modes"]["none"]["n"] == 13 and s["modes"]["learned"]["n"] == 13 and not list(out.glob("checkpoint_test_*.json"))
res = json.load(open(sorted(out.glob("learning_train_test13_*.json"))[-1]))
assert sum(bool(r["same_story"]) for r in res["rows"]["learned"]) == 3, "same-story flag on the 3 recalled items"
assert "paired_by_story" in res["summary"] and res["summary"]["story_mode"] == "any"
print("ALL OK")
