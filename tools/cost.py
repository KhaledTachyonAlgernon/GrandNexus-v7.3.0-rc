#!/usr/bin/env python
"""
API cost of a bench run, from the usage recorded on each row (logbook 63).

Rows written since v7.2.5-rc carry tokens_in (input not read from / written to the prompt cache), tokens_out,
cache_read and cache_write. Older rows only carry `tokens` (input + output, not split): their cost is not estimated.
Prices in USD per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing (read 2026-11-09);
update PRICES when they change. The estimate is for the Messages API at standard rates (no Batch discount).

  python tools/cost.py tests_lab/resultats/learning/learning_train_test68_*.json
"""
from __future__ import annotations

import glob
import json
import sys

PRICES = {   # input, output, 5-minute cache write, cache read (hit or refresh)
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-fable-5-1": {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 0.25},
}
FIELDS = ("tokens_in", "tokens_out", "cache_read", "cache_write")


def usage(rows) -> dict | None:
    """Summed usage of the API rows, or None when the rows predate the split usage fields."""
    api = [r for r in rows if "calls" in r]
    if not api or not all("tokens_in" in r for r in api):
        return None
    return {f: sum(int(r.get(f, 0) or 0) for r in api) for f in FIELDS} | {"calls": sum(r["calls"] for r in api)}


def cost_usd(u: dict | None, model: str) -> dict | None:
    """Actual cost, and what the same tokens would have cost without the prompt cache (cached input at input price)."""
    p = PRICES.get(model)
    if u is None or p is None:
        return None
    m = 1e-6
    actual = (u["tokens_in"] * p["input"] + u["tokens_out"] * p["output"] + u["cache_write"] * p["cache_write"]
              + u["cache_read"] * p["cache_read"]) * m
    without = ((u["tokens_in"] + u["cache_write"] + u["cache_read"]) * p["input"] + u["tokens_out"] * p["output"]) * m
    return {"usd": round(actual, 4), "usd_without_cache": round(without, 4), "calls": u["calls"],
            "cache_hit_share": round(u["cache_read"] / max(1, u["tokens_in"] + u["cache_read"] + u["cache_write"]), 3)}


def from_receipts(receipts, model: str) -> dict | None:
    """Exact cost of every call a Translator made (its receipts), experience phases included."""
    rec = list(receipts)
    if not rec:
        return None
    u = {"tokens_in": sum(r.tokens_in for r in rec), "tokens_out": sum(r.tokens_out for r in rec),
         "cache_read": sum(getattr(r, "cache_read", 0) for r in rec), "cache_write": sum(getattr(r, "cache_write", 0) for r in rec),
         "calls": len(rec)}
    return cost_usd(u, model)


def report(rows_by_condition: dict, model: str) -> dict:
    """{condition: cost dict} for the API conditions, plus a 'total'. Prints one line per condition."""
    out, tot = {}, {f: 0 for f in FIELDS} | {"calls": 0}
    for c, rows in rows_by_condition.items():
        u = usage(rows)
        if u is None:
            continue
        out[c] = cost_usd(u, model)
        for f in tot:
            tot[f] += u[f]
        if out[c]:
            print(f"cost {c:14} ${out[c]['usd']:.3f} ({out[c]['calls']} calls; without the prompt cache ${out[c]['usd_without_cache']:.3f}; "
                  f"cached share of the input {100 * out[c]['cache_hit_share']:.0f}%)")
    if out:
        out["total"] = cost_usd(tot, model)
        if out["total"]:
            t = out["total"]
            print(f"cost TOTAL          ${t['usd']:.3f} (without the prompt cache ${t['usd_without_cache']:.3f}; saved "
                  f"{100 * (1 - t['usd'] / max(t['usd_without_cache'], 1e-9)):.0f}%)")
    return out


if __name__ == "__main__":
    for pattern in sys.argv[1:]:
        for f in sorted(glob.glob(pattern)):
            d = json.load(open(f, encoding="utf-8"))
            model = d["summary"].get("model") or "claude-sonnet-5-5"
            api_rows = {c: rs for c, rs in d["rows"].items() if any("calls" in r for r in rs)}
            print(f"{f}  (model {model})")
            if not report(api_rows, model):
                print("  no split usage on these rows (written before v7.2.5-rc): cost not estimated")
