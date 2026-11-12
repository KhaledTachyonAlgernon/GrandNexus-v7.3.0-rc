"""Scripted stand-in for the LLM translator, shared by the offline tests of the living bench (logbook 82-84): with the
ontology or reading everything with the question it writes the ontology's names, otherwise names that follow the words
of the text. Also a fake Message Batches API that answers with it. Not a test by itself."""
import re
from types import SimpleNamespace
import living_llm as B
from living_bench import ROLES, CLASSES, ADJS
from living_language import ROLE_VERB
VERB_ROLE = {v: r for r, v in ROLE_VERB.items()}
NOUNS = sorted(ROLES + CLASSES, key=len, reverse=True)

def sing(x):
    x = x.lower()
    return x[:-1] if x.endswith("s") and x[:-1] in NOUNS else x

def n(x):
    return x.lower().replace(" ", "_")

def read(sentence, canonical):
    s = sentence.rstrip(".")
    anchor = f' @ "{s}"'
    m = re.match(r"(\w+) (?:works as|has been) an? ([a-z ]+?)(?: for years)?$", s)
    if m:
        return [f"{n(m.group(2))}({n(m.group(1))}).{anchor}" if canonical else f"works_as({n(m.group(1))}, {n(m.group(2))}).{anchor}"]
    m = re.match(r"(?:These days, )?(\w+) (" + "|".join(VERB_ROLE) + r")$", s)
    if m:
        return [f"{n(VERB_ROLE[m.group(2)])}({n(m.group(1))}).{anchor}" if canonical else f"{n(m.group(2).split()[0])}({n(m.group(1))}).{anchor}"]
    m = re.match(r"(?:All )?([A-Za-z ]+?)s are ([a-z]+?)s$", s) or re.match(r"(?:Anyone who is|Being) an? ([a-z ]+?) (?:is|makes you) an? ([a-z]+)$", s)
    if m and sing(m.group(2)) in CLASSES:
        return [f"{n(sing(m.group(1)))}(V) => {n(sing(m.group(2)))}(V).{anchor}"]
    m = (re.match(r"(?:All )?([A-Za-z ]+?)s are (?:always )?(" + "|".join(ADJS) + ")$", s)
         or re.match(r"(?:Anyone who is an?|If someone is an?) ([a-z ]+?),? (?:is|they are) (" + "|".join(ADJS) + ")$", s))
    if m:
        return [f"{n(sing(m.group(1)))}(V) => {m.group(2)}(V).{anchor}"]
    m = (re.match(r"([A-Za-z ]+?)s are never (" + "|".join(ADJS) + ")$", s) or re.match(r"No ([a-z ]+?) is ever (" + "|".join(ADJS) + ")$", s)
         or re.match(r"(?:Anyone who is an?|If someone is an?) ([a-z ]+?),? (?:is|they are) not (" + "|".join(ADJS) + ")$", s))
    if m:
        return [f"{n(sing(m.group(1)))}(V) => not {m.group(2)}(V).{anchor}"]
    m = re.match(r"(\w+) (moved to|now lives in|resides in|has a flat in|recently relocated to|left for|settled in) (\w+)(?: a while ago)?$", s)
    if m:
        pred = "lives_in" if canonical else n(m.group(2).replace("recently ", ""))
        return [f"{pred}({n(m.group(1))}, {n(m.group(3))}).{anchor}"]
    return []

class Scripted:
    def __init__(self): self.messages, self.calls = self, 0
    def create(self, model, max_tokens, system, messages):
        self.calls += 1
        u = messages[0]["content"]
        canonical = "ONTOLOGY OF THE MEMORY" in u or "(none:" not in u          # a concat reading is consistent by itself
        text = u.split("TEXT:\n")[-1].split("\n\nQUESTION")[0]
        q = u.split("QUESTION (or statement to verify):\n")[-1].strip()
        lines = [l for sent in re.split(r"(?<=\.)\s+", text) if sent for l in read(sent, canonical)]
        if not q.startswith("(none"):
            g = B.goal_of(q)
            lines.append(f"? {g[0]}.")
        return SimpleNamespace(id="s", model=model, content=[SimpleNamespace(text="```nx\n" + "\n".join(lines) + "\n```")],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))



class BatchAPI:
    """Fake Message Batches API answering with the scripted translator; `server` survives the client (resume tests)."""
    def __init__(self, server, interrupt_first_wait=False):
        self.messages, self.batches, self.server, self.interrupt, self.reader = self, self, server, interrupt_first_wait, Scripted()
    def create(self, requests):
        bid = f"msgbatch_{len(self.server) + 1}"
        self.server[bid] = list(requests)
        return SimpleNamespace(id=bid, processing_status="in_progress")
    def retrieve(self, bid):
        if self.interrupt:
            self.interrupt = False
            raise KeyboardInterrupt
        return SimpleNamespace(id=bid, processing_status="ended", request_counts=SimpleNamespace(processing=0, succeeded=len(self.server[bid])))
    def results(self, bid):
        for req in self.server[bid]:
            yield SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(type="succeeded", message=self.reader.create(**req["params"])))
