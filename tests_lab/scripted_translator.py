"""Scripted stand-in for the LLM translator, shared by the offline tests of the living bench (logbook 82-84): with the
ontology or reading everything with the question it writes the ontology's names, otherwise names that follow the words
of the text. Also a fake Message Batches API that answers with it. Not a test by itself.
Logbook 91 (questions in free language): the same class also stands in for the question writer (it rewords canonical
questions with a few frames and synonyms, with planted defects on demand), for the fidelity judge (it refuses an
opposite word or a past state) and for the reader of a question asked alone (with the names in memory it gives back
the memory's name for a synonym; without them it keeps the word of the question)."""
import json
import re
import sys
import zlib
from collections import Counter
from types import SimpleNamespace
sys.path.insert(0, "tools")
from living_bench import CITIES                                                             # noqa: E402
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
    m = re.match(r"(\w+)'s home is in (\w+)$", s)
    if m:
        return [f"{'lives_in' if canonical else 'home_in'}({n(m.group(1))}, {n(m.group(2))}).{anchor}"]
    m = re.match(r"(\w+) (moved to|now lives in|resides in|has a flat in|recently relocated to|left for|settled in) (\w+)(?: a while ago)?$", s)
    if m:
        pred = "lives_in" if canonical else n(m.group(2).replace("recently ", ""))
        return [f"{pred}({n(m.group(1))}, {n(m.group(3))}).{anchor}"]
    return []

# ---- logbook 91: frames of the scripted question writer, and their inverse for the scripted question reader
BASE = {"chess player": "play chess", "painter": "paint", "swimmer": "swim", "teacher": "teach", "gardener": "garden",
        "pilot": "fly planes", "baker": "bake bread", "musician": "play music", "nurse": "work as a nurse", "farmer": "run a farm"}
ROLE_OF_BASE = {v: k for k, v in BASE.items()}
SYN = {"brave": "courageous", "calm": "serene", "honest": "truthful", "strong": "powerful"}
ADJ_OF_SYN = {v: k for k, v in SYN.items()}
NEIGHBOUR = {"patient": "calm", "careful": "calm", "curious": "brave"}     # logbook 93: the attraction the note 1 allowed
ANT = {"patient": "impatient", "curious": "indifferent", "brave": "cowardly", "calm": "nervous", "strong": "weak",
       "careful": "careless", "generous": "stingy", "honest": "dishonest"}

def _pick(q, options):
    return options[zlib.crc32(q.encode()) % len(options)]

def reword(q):
    """A faithful rewording of a canonical question."""
    m = re.match(r"Does (\w+) live in (\w+)\?$", q)
    if m:
        p, c = m.groups()
        return _pick(q, [f"Is {c} where {p} lives?", f"Is {p} based in {c} these days?", f"Is {p}'s home in {c}?"])
    m = re.match(r"Is (\w+) (?:an? )?(.+)\?$", q)
    p, x = m.groups()
    if x in BASE:
        return _pick(q, [f"Does {p} {BASE[x]}?", f"Would you call {p} {'an' if x[0] in 'aeiou' else 'a'} {x}?"])
    if x in SYN:
        return _pick(q, [f"Is {p} a {SYN[x]} person?", f"Would you describe {p} as {x}?"])
    return _pick(q, [f"Would you describe {p} as {x}?", f"Is {p} someone you would call {x}?"])

def unfaithful(q):
    """A rewording that passes the mechanical checks but does not ask the same thing (for the judge)."""
    m = re.match(r"Does (\w+) live in (\w+)\?$", q)
    if m:
        return f"Did {m.group(1)} once live in {m.group(2)}?"
    p, x = re.match(r"Is (\w+) (?:an? )?(.+)\?$", q).groups()
    return f"Would you describe {p} as {ANT[x]}?" if x in ANT else f"Was {p} once a {x}?"

def read_free(q, preds, attract=False):
    """Scripted reading of a free question: the lines of its program. preds: the predicate names in memory, or None
    when the names were not given (then a synonym keeps the word of the question)."""
    n_ = lambda x: x.lower().replace(" ", "_")
    m = re.match(r"Does (\w+) (.+)\?$", q)
    if m and m.group(2) in ROLE_OF_BASE:
        return [f"? {n_(ROLE_OF_BASE[m.group(2)])}({n_(m.group(1))})."]
    m = re.match(r"Would you call (\w+) an? (.+)\?$", q)
    if m:
        return [f"? {n_(m.group(2))}({n_(m.group(1))})."]
    m = re.match(r"Is (\w+) a (\w+) person\?$", q)
    if m:
        adj = ADJ_OF_SYN.get(m.group(2), m.group(2))
        return [f"? {adj if preds is not None and adj in preds else m.group(2)}({n_(m.group(1))})."]
    m = re.match(r"Would you describe (\w+) as (\w+)\?$", q) or re.match(r"Is (\w+) someone you would call (\w+)\?$", q)
    if m:
        adj = m.group(2)
        if attract and preds is not None and adj not in preds and NEIGHBOUR.get(adj) in preds:
            adj = NEIGHBOUR[adj]            # a quality absent from memory replaced by a neighbouring name present in it
        return [f"? {adj}({n_(m.group(1))})."]
    m = re.match(r"Is (\w+) where (\w+) lives\?$", q)
    if m:
        return [f"? lives_in({n_(m.group(2))}, {n_(m.group(1))})."]
    m = re.match(r"Is (\w+) based in (\w+) these days\?$", q)
    if m:       # a planted presupposition: the statement must never reach the memory
        return [f'based_in({n_(m.group(1))}, {n_(m.group(2))}). @ "{m.group(1)} based in {m.group(2)}"',
                f"? lives_in({n_(m.group(1))}, {n_(m.group(2))})."]
    m = re.match(r"Is (\w+)'s home in (\w+)\?$", q)
    if m:
        return [f"? lives_in({n_(m.group(1))}, {n_(m.group(2))})."]
    g = B.goal_of(q)
    return [f"? {g[0]}."] if g else ["# cannot express: the question"]


class Scripted:
    def __init__(self, defects=None, mute_once=(), attract=False):
        """defects (logbook 91): {canonical question: 'name' | 'negation' | 'other' | 'judge' | 'stubborn'} plants a
        defect in the first rewording of that question ('stubborn': in every rewording), or {'malformed': n} makes
        the n first list replies malformed. mute_once: free questions whose first reading has no question line."""
        self.messages, self.calls, self.by = self, 0, Counter()
        self.defects, self.mute, self.malformed = dict(defects or {}), set(mute_once), int((defects or {}).get("malformed", 0))
        self.attract = attract

    def _reply(self, model, text):
        return SimpleNamespace(id="s", model=model, content=[SimpleNamespace(text=text)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    def _writer(self, model, u):
        self.by["writer"] += 1
        qs = [l.split(". ", 1)[1] for l in u.split("\n") if re.match(r"\d+\. ", l)]
        again = "was refused" in u
        if not again and self.malformed > 0:
            self.malformed -= 1
            return self._reply(model, "Here are the questions: " + "; ".join(reword(q) for q in qs))
        out = []
        for q in qs:
            d = self.defects.get(q)
            p = q.split()[1]
            if d == "stubborn" or (d == "judge" and not again):
                out.append(unfaithful(q))
            elif d == "name" and not again:
                out.append(reword(q).replace(p, "this person"))
            elif d == "negation" and not again:
                out.append("Is it not the case that " + reword(q)[0].lower() + reword(q)[1:])
            elif d == "other" and not again:
                out.append(reword(q).replace(p, p + " (like " + ("Zack" if p != "Zack" else "Yara") + ")"))
            else:
                out.append(reword(q))
        return self._reply(model, json.dumps([{"n": i + 1, "q": t} for i, t in enumerate(out)]))

    def _judge(self, model, u):
        self.by["judge"] += 1
        first, second = u.split("Second: ", 1)[0], u.split("Second: ", 1)[1]
        bad = " once " in second or any(re.search(rf"\b{a}\b", second) for a in ANT.values())
        qual = lambda t: {ADJ_OF_SYN.get(w, w) for w in re.findall(r"[a-z]+", t.lower()) if w in ANT or w in ADJ_OF_SYN}
        bad = bad or (qual(first) and qual(second) and qual(first) != qual(second))     # two different qualities
        place = lambda t: set(re.findall(r"\b(" + "|".join(CITIES) + r")\b", t))
        bad = bad or (place(first) and place(second) and place(first) != place(second))  # two different places
        return self._reply(model, "DIFFERENT" if bad else "SAME")

    def _question(self, model, u):
        self.by["question"] += 1
        q = u.split("QUESTION (or statement to verify):\n", 1)[1].split("\n")[0].strip()
        if q in self.mute and "YOUR PROGRAM" not in u:
            self.mute.discard(q)
            return self._reply(model, "```nx\n# let me think about this question\n```")
        preds = None
        if "NAMES ALREADY IN MEMORY: predicates " in u:
            names = u.split("NAMES ALREADY IN MEMORY: predicates ", 1)[1].split(";")[0]
            preds = {x.split("/")[0].strip() for x in names.split(",")}
        attract = self.attract and "use that name" in u          # only the question note 1 invites it
        return self._reply(model, "```nx\n" + "\n".join(read_free(q, preds, attract)) + "\n```")

    def create(self, model, max_tokens, system, messages, **kw):
        self.calls += 1
        u = messages[0]["content"]
        role = system if isinstance(system, str) else ""       # the translator sends its system prompt as a cached block
        if role.startswith("You reword"):
            return self._writer(model, u)
        if role.startswith("You compare"):
            return self._judge(model, u)
        if B.QUESTION_TEXT in u:
            return self._question(model, u)
        self.by["reading"] += 1
        canonical = "ONTOLOGY OF THE MEMORY" in u or "(none:" not in u          # a concat reading is consistent by itself
        text = u.split("TEXT:\n")[-1].split("\n\nQUESTION")[0]
        q = u.split("QUESTION (or statement to verify):\n")[-1].strip()
        lines = [l for sent in re.split(r"(?<=\.)\s+", text) if sent for l in read(sent, canonical)]
        if not q.startswith("(none"):
            g = B.goal_of(q)
            if g:                                   # a question outside the bench's templates: no question line
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


class DualAPI:
    """Fake client with both interfaces (logbook 91): messages.create, synchronous (the question writer and judge),
    and messages.batches (the readings of a --batch run), both answered by the same scripted stand-in."""
    def __init__(self, server, scripted=None, interrupt_first_wait=False):
        self.scripted = scripted or Scripted()
        self.batches = BatchAPI(server, interrupt_first_wait)
        self.batches.reader = self.scripted
        self.messages = SimpleNamespace(create=self.scripted.create, batches=self.batches)
