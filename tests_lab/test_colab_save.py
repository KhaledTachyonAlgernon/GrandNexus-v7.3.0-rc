"""Offline test of tools/colab_save.py: it saves the repository it belongs to (not a stale folder elsewhere), checks the
expected results are inside the zip, copies them to the Drive folder, and names the zip _NO_RESULT when they are absent."""
import pathlib, shutil, subprocess, sys, tempfile, zipfile
src = pathlib.Path("tools/colab_save.py").resolve()
tmp = pathlib.Path(tempfile.mkdtemp())
repo, stale, drive = tmp / "env" / "GrandNexus", tmp / "GrandNexus", tmp / "drive"
for r in (repo, stale):
    (r / "tools").mkdir(parents=True)
    shutil.copy(src, r / "tools" / "colab_save.py")
    (r / "README.md").write_text("x\n")
    subprocess.run("git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm init && git tag v0", shell=True, cwd=r, check=True)
res = repo / "tests_lab" / "resultats" / "learning" / "learning_train_test68_abc_2026.json"
res.parent.mkdir(parents=True); res.write_text("{}")
def run(r, *args):
    return subprocess.run([sys.executable, str(r / "tools" / "colab_save.py"), "--drive", str(drive), *args], capture_output=True, text=True)
p = run(repo, "--tag", "run5a", "--expect", "tests_lab/resultats/learning/learning_*_abc_*.json")
assert p.returncode == 0, p.stdout + p.stderr
z = sorted(drive.glob("GrandNexus_v0-1-*_run5a_*.zip"))
assert len(z) == 1 and "GrandNexus/tests_lab/resultats/learning/learning_train_test68_abc_2026.json" in zipfile.ZipFile(z[0]).namelist(), p.stdout
assert (drive / res.name).exists(), "the result is also copied to the Drive"
assert "session run5a" in subprocess.run("git log -1 --format=%s", shell=True, cwd=repo, capture_output=True, text=True).stdout
q = run(stale, "--tag", "run5a", "--expect", "tests_lab/resultats/learning/learning_*_abc_*.json")
assert q.returncode == 1 and list(drive.glob("GrandNexus_v0_run5a_NO_RESULT_*.zip")), q.stdout
print("ALL OK")
