"""Offline test (no API) of the retry of transient API errors in the translator (logbook 90): an unavailable or
overloaded API is retried with growing waits and the reading succeeds once it answers; a non-transient error is raised
at once; when the retries run out the last error is raised (the bench counts the reading as failed); the batch
replay's Pending and errored batch requests are never retried; the SDK's own exception classes are recognised."""
import sys, logging
from types import SimpleNamespace
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import grandnexus.llm_interface.translator_v5 as T
from batch_runner import Pending

waits = []
T.SLEEP = waits.append                     # no real waiting in the test

REPLY = "```nx\np(a). @ \"A is p\"\n? p(a).\n```"


def err(name, status=None, headers=None):
    cls = type(name, (Exception,), {})
    e = cls(f"{name} (fake)")
    if status is not None:
        e.status_code = status
    if headers is not None:
        e.response = SimpleNamespace(headers=headers)
    return e


class Flaky:
    """Raises the given errors in order, then answers."""
    def __init__(self, errors):
        self.errors, self.calls, self.messages = list(errors), 0, self

    def create(self, **kw):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return SimpleNamespace(id="ok", model="fake", content=[SimpleNamespace(text=REPLY)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))


# 1. two transient errors (503, then 529 overloaded), then an answer: the reading succeeds, two retries logged
c = Flaky([err("ServiceUnavailableError", 503), err("OverloadedError", 529)])
tr = T.Translator(client=c, retry_waits=(5, 15, 30))
out = tr.translate("A is p.", "Is A p?")
assert c.calls == 3 and len(tr.receipts) == 1, (c.calls, len(tr.receipts))
assert [x["status"] for x in tr.retry_log] == [503, 529] and len(waits) == 2
assert 4.0 <= waits[0] <= 6.0 and 12.0 <= waits[1] <= 18.0, waits
assert out["parsed"].facts, "the reading after the retries must be the normal one"

# 2. connection error without status code (recognised by class name), and a retry-after header that asks for longer
waits.clear()
c = Flaky([err("APIConnectionError"), err("RateLimitError", 429, {"retry-after": "42"})])
tr = T.Translator(client=c, retry_waits=(5, 15))
tr.translate("A is p.", "Is A p?")
assert c.calls == 3 and waits[1] >= 42, waits

# 3. a non-transient error (bad request) is raised at once, without waiting
waits.clear()
c = Flaky([err("BadRequestError", 400)])
tr = T.Translator(client=c, retry_waits=(5, 15))
try:
    tr.translate("A is p.", "Is A p?")
    raise AssertionError("a 400 must be raised")
except Exception as e:  # noqa: BLE001
    assert type(e).__name__ == "BadRequestError" and c.calls == 1 and not waits and not tr.retry_log

# 4. the retries run out: the last transient error is raised after len(waits) + 1 attempts
waits.clear()
c = Flaky([err("ServiceUnavailableError", 503) for _ in range(10)])
tr = T.Translator(client=c, retry_waits=(5, 15, 30))
try:
    tr.translate("A is p.", "Is A p?")
    raise AssertionError("must give up")
except Exception as e:  # noqa: BLE001
    assert type(e).__name__ == "ServiceUnavailableError" and c.calls == 4 and len(waits) == 3

# 5. batch replay: Pending (BaseException) passes through untouched; an errored batch request (RuntimeError) too
class Replay:
    def __init__(self, exc): self.exc, self.calls, self.messages = exc, 0, self
    def create(self, **kw):
        self.calls += 1
        raise self.exc
for exc, kind in ((Pending("k"), Pending), (RuntimeError("overloaded_error"), RuntimeError)):
    waits.clear()
    c = Replay(exc)
    tr = T.Translator(client=c, retry_waits=(5, 15))
    try:
        tr.translate("A is p.", "Is A p?")
        raise AssertionError("must raise")
    except kind:
        pass
    assert c.calls == 1 and not waits, (kind, c.calls)

# 6. the default policy waits up to about 8 minutes in all
assert 400 <= sum(T.DEFAULT_RETRY_WAITS) <= 600

# 7. the real SDK exception classes, when the SDK is installed
try:
    import anthropic, httpx
except ImportError:
    print("anthropic or httpx not installed: SDK classes not checked")
else:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    def sdk(name, status):
        cls = getattr(anthropic, name, None) or anthropic.InternalServerError
        return cls("x", response=httpx.Response(status, request=req), body=None)
    for name, status in (("ServiceUnavailableError", 503), ("OverloadedError", 529), ("RateLimitError", 429),
                         ("InternalServerError", 500)):
        assert T.is_transient(sdk(name, status)), name
    for name, status in (("BadRequestError", 400), ("AuthenticationError", 401), ("NotFoundError", 404)):
        assert not T.is_transient(sdk(name, status)), name
    assert T.is_transient(anthropic.APIConnectionError(request=req))
    assert T.is_transient(anthropic.APITimeoutError(request=req))
    print(f"SDK {anthropic.__version__}: exception classes recognised")
print("ALL OK")
