#!/usr/bin/env python
"""
Bench jobs through the Message Batches API (logbook 68): same model, same requests, half the price, asynchronous.

The translator and the benches are written for immediate answers (read, check, maybe re-read). Nothing of that logic
changes: a BatchSession stands in for the API client and runs the jobs by REPLAY.
  pass 1  every job runs until its first request; the request is recorded and the job is suspended
          -> one batch with all the first readings; wait; the answers go into a cache
  pass 2  every job runs again from the start: the first request is served from the cache, the job goes on to its
          second request if it has one (corrective round, reflection) -> second batch
  ...     until every job has finished (at most 4 batches: reading, corrective round, reflection, its corrective round)
A job must be a deterministic function of the answers it receives. Each job has its own key space, so two jobs
sending the same request (two conditions, two runs of the same item) get two independent answers, as in the
synchronous bench.

The state (answers received, batches in flight) is saved after every step: when a Colab session dies, running the
same command again resumes without submitting anything twice; a batch keeps running on the API side meanwhile.
Requests that end errored / expired / canceled are not billed; their job gets an exception, as it would from the API.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
from collections import Counter
from types import SimpleNamespace
from typing import Any, Callable, Dict

MAX_REQUESTS_PER_BATCH = 5000        # the API allows 100,000 requests or 256 MB per batch


class Pending(BaseException):
    """A request whose answer is not available yet. Derives from BaseException on purpose: the benches' own
    `except Exception` around an item must not swallow it."""


def _dump(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)


class BatchSession:
    def __init__(self, client, state_path, poll_seconds: float = 30.0, log: Callable[[str], None] = print) -> None:
        self.client, self.state_path, self.poll_seconds, self.log = client, pathlib.Path(state_path), poll_seconds, log
        self.cache: Dict[str, dict] = {}          # key -> {"id", "model", "text", "usage"} or {"error"}
        self.open_batches: list = []              # [{"id": batch id, "keys": {custom_id: key}}], submitted, not collected
        self.pending: Dict[str, dict] = {}        # key -> request params, to submit at the next flush
        self.batches_created = 0
        self._job, self._occ = "", Counter()
        if self.state_path.exists():
            d = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.cache, self.open_batches = d.get("cache", {}), d.get("open_batches", [])
            self.batches_created = d.get("batches_created", 0)
            self.log(f"batch state resumed: {len(self.cache)} answers received, {len(self.open_batches)} batch(es) in flight")

    # ---- the client interface the Translator uses: client.messages.create(...)
    @property
    def messages(self) -> "BatchSession":
        return self

    def create(self, model, max_tokens, system, messages):
        h = hashlib.sha256(_dump([model, max_tokens, system, messages]).encode("utf-8")).hexdigest()
        key = f"{self._job}|{h}|{self._occ[h]}"
        self._occ[h] += 1
        if key in self.cache:
            e = self.cache[key]
            if "error" in e:
                raise RuntimeError(e["error"])
            u = e["usage"]
            return SimpleNamespace(id=e["id"], model=e["model"], content=[SimpleNamespace(text=e["text"])],
                                   usage=SimpleNamespace(input_tokens=u["in"], output_tokens=u["out"],
                                                         cache_read_input_tokens=u["cache_read"], cache_creation_input_tokens=u["cache_write"]))
        if not any(key in b["keys"].values() for b in self.open_batches):
            self.pending[key] = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        raise Pending(key)

    # ---- running jobs
    def run(self, jobs: Dict[str, Callable[[], Any]]) -> Dict[str, Any]:
        """jobs: {job id: function without argument}. Returns {job id: result}; a job that raises gets its exception
        object as result (the caller decides). Blocks until every job has finished."""
        done: Dict[str, Any] = {}
        while True:
            for job_id, fn in jobs.items():
                if job_id in done:
                    continue
                self._job, self._occ = job_id, Counter()
                try:
                    done[job_id] = fn()
                except Pending:
                    pass
                except Exception as e:  # noqa: BLE001
                    done[job_id] = e
            if len(done) == len(jobs):
                return done
            self._flush()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(_dump({"cache": self.cache, "open_batches": self.open_batches, "batches_created": self.batches_created}), encoding="utf-8")
        tmp.replace(self.state_path)

    def _flush(self) -> None:
        keys = list(self.pending)
        for i in range(0, len(keys), MAX_REQUESTS_PER_BATCH):
            chunk = keys[i: i + MAX_REQUESTS_PER_BATCH]
            ids = {"r" + hashlib.sha256(k.encode("utf-8")).hexdigest()[:40]: k for k in chunk}
            batch = self.client.messages.batches.create(requests=[{"custom_id": cid, "params": self.pending[k]} for cid, k in ids.items()])
            self.batches_created += 1
            self.open_batches.append({"id": batch.id, "keys": ids})
            self._save()                                   # the batch id is on disk before anything else can fail
            self.log(f"batch {self.batches_created} submitted: {len(chunk)} requests ({batch.id})")
        self.pending = {}
        for ob in list(self.open_batches):
            t0 = time.time()
            while True:
                b = self.client.messages.batches.retrieve(ob["id"])
                if b.processing_status == "ended":
                    break
                c = getattr(b, "request_counts", None)
                self.log(f"  waiting for {ob['id']}: {getattr(c, 'processing', '?')} processing, {getattr(c, 'succeeded', '?')} done "
                         f"({int(time.time() - t0)} s)")
                time.sleep(self.poll_seconds)
            n_ok = n_bad = 0
            for entry in self.client.messages.batches.results(ob["id"]):
                key = ob["keys"].get(entry.custom_id)
                if key is None:
                    continue
                res = entry.result
                if res.type == "succeeded":
                    m, u = res.message, res.message.usage
                    g = lambda f: int(getattr(u, f, 0) or 0)
                    self.cache[key] = {"id": getattr(m, "id", "?"), "model": getattr(m, "model", "?"),
                                       "text": "".join(getattr(blk, "text", "") for blk in m.content),
                                       "usage": {"in": g("input_tokens"), "out": g("output_tokens"),
                                                 "cache_read": g("cache_read_input_tokens"), "cache_write": g("cache_creation_input_tokens")}}
                    n_ok += 1
                else:
                    err = getattr(getattr(getattr(res, "error", None), "error", None), "message", "") or ""
                    self.cache[key] = {"error": f"batch request {res.type}" + (f": {err}" if err else "")}
                    n_bad += 1
            for key in ob["keys"].values():                # a request the results did not mention
                self.cache.setdefault(key, {"error": "batch request missing from the results"})
            self.open_batches.remove(ob)
            self._save()
            self.log(f"  batch {ob['id']} collected: {n_ok} answers" + (f", {n_bad} not answered (not billed)" if n_bad else ""))

    # ---- accounting
    def usage(self) -> dict:
        """Every answer received, counted once (replays do not count twice)."""
        tot = {"tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "calls": 0, "batch": True}
        for e in self.cache.values():
            if "usage" in e:
                tot["tokens_in"] += e["usage"]["in"]; tot["tokens_out"] += e["usage"]["out"]
                tot["cache_read"] += e["usage"]["cache_read"]; tot["cache_write"] += e["usage"]["cache_write"]
                tot["calls"] += 1
        return tot

    def finish(self) -> None:
        """The results are written: the state is no longer needed."""
        if self.state_path.exists():
            self.state_path.unlink()
