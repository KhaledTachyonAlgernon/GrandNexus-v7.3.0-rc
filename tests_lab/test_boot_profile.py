"""Offline test of v7.3.0 (logbook 64-65): the minimal profile answers like the full one on the offline frozen sets and on
scripted nx readings, stays small (modules, threads, boot and shutdown times), imports only core / supported modules,
and the module tags are complete and consistent with MODULES.md. No API call, no item text printed."""
import pathlib, sys
sys.path.insert(0, "."); sys.path.insert(0, "tools")
import boot_profiles
from grandnexus.module_status import table, status, TAGS
out = boot_profiles.main(["--no-write"])
failed = [name for name, c in out["criteria"].items() if not c["pass"]]
assert not failed, f"criteria failed: {failed}"
assert all(t in TAGS for t, _ in status().values())
md = pathlib.Path("MODULES.md").read_text(encoding="utf-8")
assert md.endswith(table()), "MODULES.md is not up to date: regenerate it from grandnexus/module_status.py"
print("ALL OK")
