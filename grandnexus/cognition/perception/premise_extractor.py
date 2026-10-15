"""
premise_extractor.py — De la phrase perçue aux prémisses et règles du raisonneur.

Grammaire à motifs (français + anglais), sans dépendance externe. Produit des
propositions canoniques que ReasoningCore._simple_deductive_reasoning sait
consommer (comparaison exacte de chaînes) :

    is(socrates,mortal)        appartenance / attribut      « X est (un) Y », « X is (a) Y »
    can(penguin,fly)           capacité                     « X peut Y », « X can Y »
    prop(rain)                 proposition simple           « il pleut », « it rains »
    not <prop>                 négation                     « n'est pas », « cannot », « aucun »

Règles :
    universelles  « Tous les X sont Y », « All X are Y », « Aucun X n'est Y »
                  -> instanciées sur chaque individu connu : is(i,X) ⇒ is(i,Y)
    conditionnelles « Si A, B », « If A then B », « B if A »  -> A ⇒ B

Questions -> buts : « X est-il Y ? », « Is X Y? », « Can X Y? », « Le gâteau cuit-il ? »

Limites connues (mesurées, pas cachées) : pas de pronoms anaphoriques, pas de
quantificateurs autres que tous/aucun, pas de modus tollens, lemmatisation naïve.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from grandnexus.cognition.contracts import (
    CognitiveModuleBase, CognitiveProcessType, CognitiveMode, cognitive_capability,
)

# ---------------------------------------------------------------------------
# Lexique
# ---------------------------------------------------------------------------
ARTICLES = {"a", "an", "the", "le", "la", "les", "un", "une", "des", "du", "l", "some"}
SUBJECT_PRONOUNS = {"it", "there", "il", "on", "ce", "cela", "ça"}
CLAUSE_STARTERS = ARTICLES | {"it", "he", "she", "they", "we", "i", "you", "il", "elle", "ils",
                              "elles", "on", "je", "tu", "nous", "vous", "mon", "ma", "mes",
                              "my", "his", "her", "their", "our", "ce", "cet", "cette", "ces"}
IRREGULAR = {"men": "man", "women": "woman", "people": "person", "children": "child",
             "mice": "mouse", "geese": "goose", "feet": "foot", "teeth": "tooth",
             "fish": "fish", "sheep": "sheep", "species": "species",
             "hommes": "homme", "animaux": "animal", "oiseaux": "oiseau", "chevaux": "cheval",
             "journaux": "journal", "yeux": "oeil", "gens": "personne"}
NO_STRIP = {"is", "was", "has", "does", "this", "his", "its", "us", "as", "yes", "always",
            "species", "physics", "mathematics", "socrates", "pas", "plus", "dans", "sous",
            "vers", "très", "trés", "mais", "fois", "souris", "bras", "corps", "temps", "gaz"}
COPULA_EN = {"is", "are", "am", "was", "were"}
COPULA_FR = {"est", "sont", "es", "suis", "sommes", "êtes"}
CAN_EN = {"can"}
CAN_FR = {"peut", "peuvent", "peux", "pouvons", "pouvez"}


def lemma(word: str) -> str:
    """Lemmatisation naïve : pluriels et féminins réguliers (FR/EN)."""
    w = word.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    if w in NO_STRIP or len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("aux") and len(w) > 4:
        return w[:-3] + "al"
    if w.endswith("ées"):
        return w[:-3] + "é"
    if w.endswith("ée"):
        return w[:-2] + "é"
    if w.endswith("eaux"):
        return w[:-1]
    if w.endswith("ss") or w.endswith("us") or w.endswith("is"):
        return w
    if w.endswith("s") or (w.endswith("x") and w[-2] in "eu"):
        return w[:-1]
    return w


def normalize(text: str) -> str:
    t = text.strip().lower().replace("’", "'").replace("`", "'")
    t = re.sub(r"\bcan't\b", "cannot", t)
    t = re.sub(r"\bisn't\b", "is not", t)
    t = re.sub(r"\baren't\b", "are not", t)
    t = re.sub(r"\bdoesn't\b", "does not", t)
    t = re.sub(r"\bdon't\b", "do not", t)
    t = re.sub(r"\bcan not\b", "cannot", t)
    t = re.sub(r"\bs'(il|ils)\b", r"si \1", t)
    t = re.sub(r"\b(n|l|d|qu|j|m|t|s|c)'", r"\1e ", t)        # élisions françaises
    t = t.replace("est-ce que ", "")
    t = re.sub(r"-t-", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> List[str]:
    return [w for w in re.split(r"[\s,;:]+", text.strip(" .!?")) if w]


def strip_articles(words: List[str]) -> List[str]:
    return [w for w in words if w not in ARTICLES]


def term(words: List[str]) -> str:
    ws = [lemma(w) for w in strip_articles(words) if w not in {"de", "of"} or len(words) > 2]
    return "_".join(ws) if ws else ""


@dataclass
class Clause:
    kind: str                     # is / can / prop
    subject: str = ""
    obj: str = ""
    negated: bool = False

    def proposition(self, subject: Optional[str] = None) -> str:
        s = subject if subject is not None else self.subject
        p = f"{self.kind}({s},{self.obj})" if self.kind in ("is", "can") else f"prop({self.obj})"
        return ("not " + p) if self.negated else p


@dataclass
class Extraction:
    facts: List[str] = field(default_factory=list)
    rules: List[Dict[str, Any]] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    universals: List[Dict[str, Any]] = field(default_factory=list)
    conditionals: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    unparsed: List[str] = field(default_factory=list)
    trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class PremiseExtractor(CognitiveModuleBase):
    """Module de perception : texte -> faits, règles, buts."""

    def __init__(self, nexus_core: Any = None, **kwargs):
        self.nexus_core = nexus_core
        self.default_confidence = 0.95

    # -- analyse d'une proposition ------------------------------------------
    def parse_clause(self, text: str) -> Optional[Clause]:
        words = tokens(text)
        if not words:
            return None
        neg = False
        # négations
        if "not" in words or "pas" in words or "cannot" in words or ("ne" in words and "pas" in words):
            neg = True
        words = [w for w in words if w not in {"not", "pas", "ne", "jamais", "does", "do", "did"}]
        if words and words[0] in SUBJECT_PRONOUNS:
            words = words[1:]
        if not words:
            return None
        for i, w in enumerate(words):
            if i == 0:
                continue
            if w in COPULA_EN | COPULA_FR:
                subj, obj = term(words[:i]), term(words[i + 1:])
                if subj and obj:
                    return Clause("is", subj, obj, neg)
            if w in CAN_EN | CAN_FR or w == "cannot":
                if w == "cannot":
                    neg = True
                subj, obj = term(words[:i]), term(words[i + 1:])
                if subj and obj:
                    return Clause("can", subj, obj, neg)
        content = strip_articles(words)
        if not content:
            return None
        return Clause("prop", obj="_".join(lemma(w) for w in content), negated=neg)

    # -- phrases --------------------------------------------------------------
    UNIVERSAL_RE = [
        (re.compile(r"^(?:all|every|each|any)\s+(.+?)\s+(are|is|can|cannot)\s+(not\s+)?(.+)$"), False),
        (re.compile(r"^(?:no)\s+(.+?)\s+(are|is|can)\s+(.+)$"), True),
        (re.compile(r"^(?:tous|toutes)\s+(?:les\s+)?(.+?)\s+(sont|peuvent)\s+(.+)$"), False),
        (re.compile(r"^(?:tout|toute|chaque)\s+(.+?)\s+(est|peut)\s+(.+)$"), False),
        (re.compile(r"^(?:aucun|aucune|nul|nulle)\s+(.+?)\s+(?:ne\s+)?(est|sont|peut|peuvent)\s+(.+)$"), True),
        (re.compile(r"^les\s+(.+?)\s+(?:ne\s+)?(sont|peuvent)\s+(.+)$"), False),
    ]
    CONDITIONAL_RE = [
        re.compile(r"^(?:if|when|whenever|si|quand|lorsque|lorsqu)\s+(.+?)\s*(?:,\s*then\s+|\s+then\s+|,\s*alors\s+|\s+alors\s+|,\s*)(.+)$"),
    ]
    TRAILING_IF_RE = re.compile(r"^(.+?)\s+(?:if|si|when|quand)\s+(.+)$")

    def _universal(self, s: str) -> Optional[Tuple[str, Clause, bool]]:
        for rx, is_negative in self.UNIVERSAL_RE:
            m = rx.match(s)
            if not m:
                continue
            g = m.groups()
            category = term(tokens(g[0]))
            verb = g[1]
            rest = g[-1]
            neg = is_negative or "not" in s.split() or "pas" in s.split() or verb == "cannot"
            rest_words = [w for w in tokens(rest) if w not in {"not", "pas", "ne"}]
            kind = "can" if verb in CAN_EN | CAN_FR | {"cannot"} else "is"
            obj = term(rest_words)
            if not category or not obj:
                continue
            # « Les X sont Y » sans article devant Y en anglais est déjà couvert ;
            # en français « les chats sont des mammifères » -> is(X, mammifère)
            return category, Clause(kind, "?", obj, neg), True
        # pluriel générique anglais : « Birds can fly », « Penguins cannot fly »
        w = tokens(s)
        if len(w) >= 3 and w[0] not in CLAUSE_STARTERS and w[0].endswith("s") and w[0] not in NO_STRIP \
                and w[1] in {"are", "can", "cannot"}:
            neg = w[1] == "cannot" or "not" in w
            kind = "can" if w[1] in {"can", "cannot"} else "is"
            obj = term([x for x in w[2:] if x != "not"])
            if obj:
                return lemma(w[0]), Clause(kind, "?", obj, neg), True
        return None

    def _split_conditional_body(self, body: str) -> Optional[Tuple[str, str]]:
        """« it rains the ground is wet » -> (« it rains », « the ground is wet »)."""
        w = tokens(body)
        for i in range(2, len(w) - 1):
            if w[i] in CLAUSE_STARTERS:
                return " ".join(w[:i]), " ".join(w[i:])
        return None

    def _conditional(self, s: str) -> Optional[Tuple[Clause, Clause]]:
        m = re.match(r"^(?:if|when|whenever|si|quand|lorsque|lorsqu|lorsqu'e)\s+(.+)$", s)
        if m:
            body = m.group(1)
            parts = re.split(r"\s*,\s*then\s+|\s+then\s+|\s*,\s*alors\s+|\s+alors\s+|\s*,\s*", body, maxsplit=1)
            if len(parts) != 2:
                sp = self._split_conditional_body(body)
                if not sp:
                    return None
                parts = list(sp)
            a, b = self.parse_clause(parts[0]), self.parse_clause(parts[1])
            return (a, b) if a and b else None
        m = self.TRAILING_IF_RE.match(s)
        if m and not s.startswith(("all ", "tous ", "toutes ")):
            b, a = self.parse_clause(m.group(1)), self.parse_clause(m.group(2))
            return (a, b) if a and b else None
        return None

    def _question(self, s: str) -> Optional[Clause]:
        w = tokens(s)
        if not w:
            return None
        if w[0] in {"is", "are", "can", "does", "do", "est", "sont", "peut", "peuvent"} and len(w) >= 3:
            v = w[0]
            rest = w[1:]
            if v in {"does", "do"}:
                return self.parse_clause(" ".join(rest))
            if v in {"is", "are", "est", "sont"}:
                if rest[0] in {"it", "ce"} and len(rest) > 2 and rest[1] in {"true", "vrai"}:
                    return self.parse_clause(" ".join(rest[3:] if rest[2] in {"that", "que"} else rest[2:]))
                # sujet = jusqu'au dernier mot (ou groupe nominal) ; objet = le reste
                for cut in range(len(rest) - 1, 0, -1):
                    subj, obj = rest[:cut], rest[cut:]
                    if strip_articles(subj) and strip_articles(obj):
                        if obj[0] in ARTICLES or cut == len(rest) - 1:
                            return Clause("is", term(subj), term(obj))
                return None
            if v in {"can", "peut", "peuvent"}:
                # « can a penguin fly » : sujet = jusqu'à l'avant-dernier mot
                return Clause("can", term(rest[:-1]), term(rest[-1:]))
        # français inversé : « socrate est-il mortel », « le gâteau cuit-il »
        joined = " ".join(w)
        m = re.match(r"^(.+?)\s+(\w+)-(?:il|elle|ils|elles|on)\s*(.*)$", joined)
        if m:
            subj, verb, rest = m.group(1), m.group(2), m.group(3)
            neg = False
            if verb in {"est", "sont"}:
                return Clause("is", term(tokens(subj)), term(tokens(rest)), neg) if rest else None
            if verb in CAN_FR:
                return Clause("can", term(tokens(subj)), term(tokens(rest)), neg) if rest else None
            return self.parse_clause(f"{subj} {verb} {rest}".strip())
        return self.parse_clause(joined)

    # -- point d'entrée -------------------------------------------------------
    def extract(self, text: str) -> Extraction:
        ex = Extraction()
        norm = normalize(text)
        sentences = [x for x in re.split(r"(?<=[.?!])\s+|\n+", norm) if x.strip()]
        individuals: List[str] = []
        for raw in sentences:
            is_q = raw.rstrip().endswith("?")
            s = raw.strip(" .!?")
            if not s:
                continue
            if is_q:
                c = self._question(s)
                if c:
                    ex.goals.append(c.proposition())
                    if c.subject:
                        individuals.append(c.subject)
                    ex.trace.append(f"but      | {raw} -> {c.proposition()}")
                else:
                    ex.unparsed.append(raw)
                continue
            u = self._universal(s)
            if u:
                category, clause, _ = u
                ex.universals.append({"category": category, "clause": clause})
                ex.trace.append(f"universel| {raw} -> ∀x is(x,{category}) ⇒ {clause.proposition('x')}")
                continue
            cond = self._conditional(s)
            if cond:
                a, b = cond
                ex.conditionals.append({"if": a, "then": b})
                ex.rules.append({"if": a.proposition(), "then": b.proposition(),
                                 "confidence": self.default_confidence, "source": raw})
                ex.trace.append(f"règle    | {raw} -> {a.proposition()} ⇒ {b.proposition()}")
                continue
            c = self.parse_clause(s)
            if c:
                ex.facts.append(c.proposition())
                if c.subject:
                    individuals.append(c.subject)
                ex.trace.append(f"fait     | {raw} -> {c.proposition()}")
            else:
                ex.unparsed.append(raw)
        # instanciation des règles universelles sur les individus connus,
        # jusqu'à stabilité (les conclusions peuvent créer de nouvelles appartenances)
        ex.entities = list(dict.fromkeys(individuals))
        seen = set()
        for ind in ex.entities:
            for u in ex.universals:
                r = {"if": f"is({ind},{u['category']})", "then": u["clause"].proposition(ind),
                     "confidence": self.default_confidence, "source": "universel"}
                key = (r["if"], r["then"])
                if key not in seen:
                    seen.add(key)
                    ex.rules.append(r)
        return ex

    @cognitive_capability(
        capability_type=CognitiveProcessType.PERCEPTION,
        description="Extraire faits, règles et buts d'un texte (FR/EN)",
        priority=55,
        compatible_modes={CognitiveMode.DELIBERATIVE, CognitiveMode.REACTIVE},
    )
    def extract_premises(self, request, context, query, **kwargs) -> Dict[str, Any]:
        ex = self.extract(str(query))
        n = len(ex.facts) + len(ex.rules) + len(ex.goals)
        out = ex.to_dict()
        out["universals"] = [{"category": u["category"], "then": u["clause"].proposition("x")}
                             for u in ex.universals]
        out["conditionals"] = [{"if": c["if"].proposition(), "then": c["then"].proposition()}
                               for c in ex.conditionals]
        out["confidence"] = 0.0 if n == 0 else round(1 - len(ex.unparsed) / max(1, n + len(ex.unparsed)), 2)
        return out
