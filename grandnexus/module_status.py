"""
module_status.py - The status of every module of the package (v7.3.0, logbook 64-65).

    core          the demonstrated pathway and what it imports: boot(profile="minimal") loads exactly these
    supported     tested, used by the benches or kept for comparison, not on the core pathway
    experimental  the 2025 ground: imports and runs, not demonstrated; not extended without a measurement
    archive       superseded duplicates kept for history; not to be extended

The checks (tests_lab/test_boot_profile.py, tools/boot_profiles.py): every module of the package has exactly one tag;
the modules imported by the minimal profile at run time are core or supported; no core module except boot.py (whose
full profile assembles the experimental ground on purpose) imports an experimental or archive module, anywhere in
the file. A tag is a statement about evidence, not about quality: a module moves up only with a measurement.
"""
from __future__ import annotations

import ast
import pathlib
from typing import Dict, Iterable, List, Tuple

TAGS = ("core", "supported", "experimental", "archive")
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent

_CORE = {
    "grandnexus": "package root (subsystem import aliases)",
    "grandnexus.boot": "assembly; profile='minimal' is the core, profile='full' adds the experimental ground",
    "grandnexus.core": "package of NexusCore",
    "grandnexus.core.nexus_core": "NexusCore: the orchestrator (registers, starts, stops the modules)",
    "grandnexus.core.errorRecoveryManager": "imported and started by NexusCore",
    "grandnexus.core.event_bus": "installed by NexusCore",
    "grandnexus.cognition": "package of the cognitive modules",
    "grandnexus.cognition.contracts": "shared result types of the reasoning pathway",
    "grandnexus.cognition.perception": "package of the premise extractor",
    "grandnexus.cognition.perception.premise_extractor": "grammar pathway: text -> premises",
    "grandnexus.cognition.reasoning": "package of the text reasoner",
    "grandnexus.cognition.reasoning.text_reasoner": "pathways (grammar, JSON, nx) -> reference engine -> strict verdict",
    "grandnexus.llm_interface": "package of the translators (lazy exports since v7.3.0)",
    "grandnexus.llm_interface.translator_v5": "Claude as anchored translator into the nexus_logic language",
    "grandnexus.nexus_logic": "language spec and reference engine (package)",
    "grandnexus.nexus_logic.core": "parser and reference engine (ref-2.3)",
    "grandnexus.nexus_logic.bridge": "atoms of the grammar pathway -> nexus_logic program",
    "grandnexus.nexus_logic.asp": "clingo export (differential check, 1,218/1,218)",
}
_SUPPORTED = {
    "grandnexus.module_status": "this file: the tags and their checks",
    "grandnexus.cognition.experience": "experience memory of the learning loop; measured, no effect shown (logbook 62)",
    "grandnexus.cognition.deliberation": "deliberation experiment (several readings), rejected (logbook 44), bench kept",
    "grandnexus.cognition.reasoning.reasoning_core": "home engine, kept for the comparison with the reference engine",
    "grandnexus.llm_interface.llm_translator": "earlier JSON translator (prompts v1-v4), kept for comparison",
    "grandnexus.llm_interface.llm_engine": "LLM engine used by the JSON translator",
    "grandnexus.llm_interface.prompt_templates": "templates of the LLM engine",
    "grandnexus.llm_interface.response_parser": "parsers of the LLM engine",
}
_ARCHIVE = {
    "grandnexus.graph.graph_engine_v1": "duplicate of graph_engine (kept side by side, logbook: legacy notes)",
    "grandnexus.llm_interface.llm_engine_lite": "duplicate of llm_engine (fallback and embeddings to graft, never wired)",
    "grandnexus.computation.resource_manager_ml": "duplicate of resource_manager",
    "grandnexus.cognition.orchestration.cognitive_orchestrator_v1": "earlier version of cognitive_orchestrator",
}
_EXPERIMENTAL_NOTES = {
    "grandnexus.memory.semantic_v2": "variant of semantic, not loaded by any profile",
    "grandnexus.memory.working_v2": "variant of working, not loaded by any profile",
    "grandnexus.memory.memory_manager": "not loaded by any profile",
    "grandnexus.cognition.perception.filters.attention_filter": "not loaded by any profile",
    "grandnexus.cognition.perception.filters.attention_filter_v2": "variant of attention_filter, not loaded by any profile",
}
_ALIASES = {
    "grandnexus.perception": "grandnexus.cognition.perception",
    "grandnexus.reasoning": "grandnexus.cognition.reasoning",
    "grandnexus.learning": "grandnexus.cognition.learning",
    "grandnexus.metacognition": "grandnexus.cognition.metacognition",
    "grandnexus.dialogue": "grandnexus.io",
}


def package_modules(root: pathlib.Path = PACKAGE_ROOT) -> Dict[str, pathlib.Path]:
    """Every module of the package: dotted name -> file."""
    out = {}
    for p in sorted(root.rglob("*.py")):
        parts = ("grandnexus",) + p.relative_to(root).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        out[".".join(parts)] = p
    return out


def status() -> Dict[str, Tuple[str, str]]:
    """Every module -> (tag, reason). Modules not named above are experimental (the 2025 ground)."""
    out = {}
    for name in package_modules():
        if name in _CORE:
            out[name] = ("core", _CORE[name])
        elif name in _SUPPORTED:
            out[name] = ("supported", _SUPPORTED[name])
        elif name in _ARCHIVE:
            out[name] = ("archive", _ARCHIVE[name])
        else:
            out[name] = ("experimental", _EXPERIMENTAL_NOTES.get(name, "2025 ground: runs, not demonstrated"))
    return out


def tag_of(module: str) -> str:
    return status().get(_resolve(module), ("unknown", ""))[0]


def _resolve(name: str) -> str:
    for alias, real in _ALIASES.items():
        if name == alias or name.startswith(alias + "."):
            return real + name[len(alias):]
    return name


def _lazy_export_nodes(tree: ast.AST) -> set:
    """Import nodes inside a module-level __getattr__ (PEP 562 lazy export): they load nothing unless that name is
    requested from the package; reported apart from the imports that run (logbook 65)."""
    out = set()
    for fn in getattr(tree, "body", []):
        if isinstance(fn, ast.FunctionDef) and fn.name == "__getattr__":
            out |= {id(n) for n in ast.walk(fn) if isinstance(n, (ast.Import, ast.ImportFrom))}
    return out


def imports_of(path: pathlib.Path, module: str, known: Iterable[str], lazy: str = "exclude") -> List[str]:
    """Package modules imported anywhere in a file (absolute, relative and aliased imports, inside functions too).
    lazy: "exclude" (default) leaves out the imports of a PEP 562 __getattr__, "only" returns only those, "include" all."""
    known = set(known)
    pkg = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    found = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lazy_nodes = _lazy_export_nodes(tree)
    for node in ast.walk(tree):
        if (lazy == "exclude" and id(node) in lazy_nodes) or (lazy == "only" and id(node) not in lazy_nodes):
            continue
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = pkg.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                base = ".".join(anchor + ([base] if base else []))
            names = [base] + [f"{base}.{a.name}" for a in node.names]
        for n in names:
            n = _resolve(n)
            while n and n not in known and "." in n:
                n = n.rsplit(".", 1)[0]
            if n in known and n != module:
                found.add(n)
    return sorted(found)


def check() -> Dict[str, list]:
    """Static checks: untagged modules (none possible by construction, reported if a tag names a missing module) and
    core modules (boot.py excepted) importing experimental or archive modules."""
    st, mods = status(), package_modules()
    stale = sorted(n for n in list(_CORE) + list(_SUPPORTED) + list(_ARCHIVE) if n not in mods)
    leaks, lazy = [], []
    for name, (tag, _) in st.items():
        if tag != "core" or name == "grandnexus.boot":
            continue
        for dep in imports_of(mods[name], name, mods):
            if st[dep][0] in ("experimental", "archive"):
                leaks.append(f"{name} -> {dep} ({st[dep][0]})")
        for dep in imports_of(mods[name], name, mods, lazy="only"):
            if st[dep][0] in ("experimental", "archive"):
                lazy.append(f"{name} -> {dep} ({st[dep][0]}, lazy export)")
    return {"tags_naming_missing_modules": stale, "core_imports_outside_core": leaks, "core_lazy_exports_outside_core": lazy}


def table() -> str:
    """Markdown table of the tags (for MODULES.md)."""
    rows = ["| Module | Tag | Why |", "|---|---|---|"]
    for name, (tag, why) in sorted(status().items(), key=lambda kv: (TAGS.index(kv[1][0]), kv[0])):
        rows.append(f"| `{name}` | {tag} | {why} |")
    return "\n".join(rows) + "\n"
