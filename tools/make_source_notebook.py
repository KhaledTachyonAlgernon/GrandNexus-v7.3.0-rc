#!/usr/bin/env python
"""
Source notebook for the project folder: STATUS.md, the git history, then every text file of the repository as a
`%%writefile` cell (Runtime > Run all rewrites the package under /content/GrandNexus). Excluded: the archive/ and
services_1505/ originals, result JSONs and saved memories (they quote item texts), caches, empty files, notebooks.
The complete zip (with .git) stays the reference; this notebook exists because the project folder takes no zip.

  python tools/make_source_notebook.py --version v7.2.4-rc --out GrandNexus_v7_2_4-rc_source.ipynb \\
         --branch-files lessons:grandnexus/cognition/lessons.py lessons:tests_lab/test_lessons.py lessons:tools/bench_learning.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".sh", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".nx", ".json"}
EXCLUDE_DIRS = ("archive/", "services_1505/", "tests_lab/resultats/", "tests_lab/data/", "notebooks/", ".git/")
EXCLUDE_FILES = {"LOGBOOK.md"}           # delivered apart as LOGBOOK_<version>.md


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    keep = []
    for f in sorted(out):
        p = ROOT / f
        if any(f.startswith(d) for d in EXCLUDE_DIRS) or f in EXCLUDE_FILES or p.suffix not in TEXT_SUFFIXES and p.name != ".gitignore":
            continue
        if not p.exists() or p.stat().st_size == 0:
            continue
        keep.append(f)
    return keep


def cell(kind: str, text: str) -> dict:
    c = {"cell_type": kind, "metadata": {}, "source": text.splitlines(keepends=True)}
    if kind == "code":
        c.update({"execution_count": None, "outputs": []})
    return c


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="/content/GrandNexus")
    ap.add_argument("--branch-files", nargs="*", default=[], metavar="BRANCH:PATH",
                    help="files of another branch to append (written under <base>_branch_<branch>/, never over the main tree)")
    a = ap.parse_args(argv)

    files = tracked_files()
    dirs = sorted({str(pathlib.Path(f).parent) for f in files})
    history = subprocess.run(["git", "log", "--oneline", "--decorate", "-40"], cwd=ROOT, capture_output=True, text=True).stdout
    branches = subprocess.run(["git", "branch", "--list"], cwd=ROOT, capture_output=True, text=True).stdout
    for spec in a.branch_files:
        branch, path = spec.split(":", 1)
        dirs.append(f"../{pathlib.Path(a.base).name}_branch_{branch}/{pathlib.Path(path).parent}")
    cells = [cell("markdown", f"# GrandNexus {a.version} — full source (notebook for the project folder)\n"
                              f"**Runtime > Run all** writes the package to `{a.base}`. The complete zip (with `.git`) is the reference.\n"),
             cell("markdown", (ROOT / "STATUS.md").read_text(encoding="utf-8")),
             cell("code", f"import os\nBASE = {a.base!r}\nDIRS = {json.dumps(dirs)}\nfor d in DIRS:\n    os.makedirs(os.path.join(BASE, d), exist_ok=True)\nprint('directories ready under', BASE)\n"),
             cell("markdown", f"## Git history (newest first)\n\n```\n{history}```\nBranches:\n```\n{branches}```\n")]
    current = None
    for f in files:
        d = str(pathlib.Path(f).parent)
        if d != current:
            current = d
            cells.append(cell("markdown", f"## `{d}/`\n" if d != "." else "## repository root\n"))
        body = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        cells.append(cell("code", f"%%writefile {a.base}/{f}\n{body}" + ("" if body.endswith("\n") else "\n")))
    for spec in a.branch_files:
        branch, path = spec.split(":", 1)
        body = subprocess.run(["git", "show", f"{branch}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        cells.append(cell("markdown", f"## branch `{branch}`: `{path}`\n(written under `{a.base}_branch_{branch}/`; "
                                      f"`git checkout {branch}` in the zip gives the real thing)\n"))
        cells.append(cell("code", f"%%writefile {a.base}_branch_{branch}/{path}\n{body}" + ("" if body.endswith("\n") else "\n")))
    nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                                       "language_info": {"name": "python"}, "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 4}
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out}: {len(files)} files, {len(cells)} cells, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
