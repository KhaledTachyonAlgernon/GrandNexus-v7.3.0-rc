"""Export du même programme vers clingo (ASP) : second avis indépendant pour tools/diff_engines.py.
Optionnel : `pip install clingo`. Limite documentée : le pas dirigé par le but (contraposées non sûres)
n'est pas exporté, clingo refusant les règles non sûres ; diff_engines le signale au lieu de compter un bug."""
from __future__ import annotations

from typing import List, Optional

from .core import Engine, Lit, Program


def _term(t) -> str:
    if isinstance(t, (bool, float)):
        raise ValueError("ASP export: integer and symbolic terms only")
    return str(t)


def _lit(l: Lit) -> str:
    return ("-" if l.neg else "") + f"{l.atom.pred}({','.join(_term(a) for a in l.atom.args)})"


def to_asp(eng: Engine) -> str:
    lines: List[str] = [_lit(f) + "." for f in eng.facts0]
    lines += [f"{_lit(r.head)} :- {', '.join(_lit(b) for b in r.body)}." for r in eng.rules]
    sigs = {(l.atom.pred, len(l.atom.args)) for l in eng.facts0}
    sigs |= {(l.atom.pred, len(l.atom.args)) for r in eng.rules for l in r.body + (r.head,)}
    for pred, ar in sorted(sigs):                      # p et -p ensemble => aucun modèle => contradictoire
        vs = ",".join(f"V{i}" for i in range(ar))
        lines.append(f":- {pred}({vs}), -{pred}({vs}).")
    return "\n".join(lines)


def clingo_verdict(prog: Program, use_knowledge: bool = True) -> Optional[str]:
    """oui / non / inconnu / contradictoire selon clingo ; None si clingo absent ou question non exportable."""
    try:
        import clingo
    except ImportError:
        return None
    if not prog.questions:
        return "inconnu"
    eng = Engine(prog, use_knowledge=use_knowledge)
    goal = [eng.canon(l) for l in prog.questions[0]]
    if any(l.vars() for l in goal):
        return None
    try:
        text = to_asp(eng)
    except ValueError:
        return None
    ctl = clingo.Control(["0"])
    ctl.add("base", [], text)
    ctl.ground([("base", [])])
    models: list = []
    res = ctl.solve(on_model=lambda m: models.append(set(m.symbols(atoms=True))))
    if not res.satisfiable:
        return "contradictoire"
    atoms = models[0]

    def sym(l: Lit):
        return clingo.Function(l.atom.pred, [clingo.Number(a) if isinstance(a, int) else clingo.Function(a)
                                             for a in l.atom.args], not l.neg)
    if all(sym(l) in atoms for l in goal):
        return "oui"
    if any(sym(l.flip()) in atoms for l in goal):
        return "non"
    return "inconnu"
