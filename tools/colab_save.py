#!/usr/bin/env python
"""
Save a Colab session without saving the wrong folder (logbook 61).

The repository saved is the one this file belongs to (its root is derived from this file, never from a hard-coded
path): commit everything, zip the repository with its .git into the Drive folder, check that the zip really contains
the expected result files, and copy those files to the Drive as well (small, a second copy). The zip name says what
it holds: GrandNexus_<git describe>_<tag>[_NO_RESULT]_<date>.zip. Exit code 1 when an expected result is missing.

  !python /content/GrandNexus/tools/colab_save.py --tag run6 --expect "tests_lab/resultats/learning/learning_*_<sha>_*.json"
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True, help="what this session was, e.g. run6 or costcheck")
    ap.add_argument("--expect", nargs="*", default=[], help="globs, relative to the repository, of the files this session must have produced")
    ap.add_argument("--drive", default="/content/drive/MyDrive/GrandNexus")
    ap.add_argument("--message", help="commit message (default: 'session <tag>')")
    a = ap.parse_args(argv)

    found = sorted({p.relative_to(ROOT).as_posix() for g in a.expect for p in ROOT.glob(g) if p.is_file()})
    no_result = bool(a.expect) and not found
    for p in list(ROOT.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)
    git("add", "-A")
    git("-c", "user.name=Khaled", "-c", "user.email=khaled@grandnexus.local", "commit", "-qm",
        a.message or f"session {a.tag}" + (" (no result)" if no_result else ""))
    describe = git("describe", "--tags") or "untagged"
    drive = pathlib.Path(a.drive)
    drive.mkdir(parents=True, exist_ok=True)
    name = drive / f"GrandNexus_{describe}_{a.tag}{'_NO_RESULT' if no_result else ''}_{time.strftime('%Y%m%d_%H%M')}"
    zpath = pathlib.Path(shutil.make_archive(str(name), "zip", ROOT.parent, ROOT.name))
    inside = set(zipfile.ZipFile(zpath).namelist())
    missing = [f for f in found if f"{ROOT.name}/{f}" not in inside]
    for f in found:
        shutil.copy2(ROOT / f, drive / pathlib.Path(f).name)
    print(f"repository : {ROOT}  ({describe}, {git('log', '--oneline', '-1')})")
    print(f"zip        : {zpath}  ({zpath.stat().st_size} bytes, sha256 {hashlib.sha256(zpath.read_bytes()).hexdigest()[:16]})")
    print(f"results    : {found or 'NONE'}" + (f"  MISSING FROM THE ZIP: {missing}" if missing else ("  (in the zip, and copied to the Drive)" if found else "")))
    return 1 if (missing or no_result) else 0


if __name__ == "__main__":
    sys.exit(main())
