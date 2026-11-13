"""Offline test (no API) of phase D, questions in free language (logbook 91), on the debug seed 5: scripted stand-ins
for the question writer, the fidelity judge and the reader. Checks: the mechanical checks; planted defects are caught
(by a check or by the judge), rewritten, or fall back to the canonical wording; the set is frozen by content sha and
never regenerated; the audit and the gate; the criteria; a question never writes into the memory; a failed question
call counts as wrong; the batch path gives the synchronous results and resumes; nothing of a non-debug seed is printed."""
import contextlib, io, json, pathlib, sys, logging, tempfile
logging.disable(logging.CRITICAL)
sys.path.insert(0, "."); sys.path.insert(0, "tools"); sys.path.insert(0, "tests_lab")
import living_questions as Q
import living_llm as B
import grandnexus.llm_interface.translator_v5 as T
from scripted_translator import Scripted, DualAPI
T.SLEEP = lambda s: None


def quiet(argv, client=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = Q.main(argv, client=client)
    return out, buf.getvalue()


# ---- 1. mechanical checks
C1, C2 = "Is Bob a chess player?", "Does Alice live in Paris?"
assert Q.check(C1, "Does Bob play chess?") is None and Q.check(C2, "Is Paris where Alice lives?") is None
assert Q.check(C1, "Does he play chess?") == "name" and Q.check(C2, "Is that where Alice lives?") == "city"
assert Q.check(C1, "Do Bob and Zack play chess?") == "other name" and Q.check(C2, "Did Alice leave Lyon for Paris?") == "other name"
assert Q.check(C1, "Is it not true that Bob plays chess?") == "negation" and Q.check(C1, "Doesn't Bob play chess?") == "negation"
assert Q.check(C2, "Does Alice no longer live in Paris?") == "negation"
assert Q.check(C1, "Is Bob  a chess player ?") == "same wording" and Q.check(C1, "is bob a chess player?") == "name"
assert Q.check(C1, "Bob plays chess.") == "form" and Q.check(C1, "Does Bob play chess? Really?") == "form" and Q.check(C1, None) == "form"
assert Q.check(C1, "Does Bob " + "really " * 30 + "play chess?") == "form"

# ---- 2. generation with planted defects, frozen set
tmp = pathlib.Path(tempfile.mkdtemp())
ARGS = ["--seed", "5", "--worlds", "4", "--sessions", "12", "--questions-dir", str(tmp), "--no-write"]
canon = Q.canonical_items(5, 4, 12)
uniq = list(dict.fromkeys(it["canonical"] for it in canon))
role = [q for q in uniq if " a " in q or " an " in q]
adj = [q for q in uniq if q.startswith("Is ") and q not in role]
res = [q for q in uniq if q.startswith("Does ")]
defects = {role[0]: "name", res[0]: "negation", adj[0]: "judge", adj[1]: "stubborn", res[1]: "other", "malformed": 1}
sc = Scripted(defects=defects)
fz, text = quiet(ARGS + ["--generate-only"], client=sc)
n = len(fz["items"])
assert n == len(canon) > 60 and fz["sha"] == Q.content_sha(fz["items"])
st = fz["stats"]
assert st["refusals"].get("name", 0) >= 1 and st["refusals"].get("negation", 0) >= 1 and st["refusals"].get("other name", 0) >= 1, st
assert st["refusals"].get("judge", 0) >= 1 + (1 + Q.MAX_REWRITES), st            # one caught once, one stubborn
fb = [it for it in fz["items"] if it["fallback"]]
assert fb and all(it["canonical"] == adj[1] and it["free"] == it["canonical"] and len(it["attempts"]) == 1 + Q.MAX_REWRITES for it in fb)
assert all(Q.check(it["canonical"], it["free"]) is None for it in fz["items"] if not it["fallback"])
assert sc.by["writer"] >= 4 + 1 and sc.by["judge"] >= n                         # one malformed list was asked again
assert role[0] not in text and fz["items"][0]["free"] not in text, "generation must print no question"
calls = sc.calls
again, _ = quiet(ARGS + ["--generate-only"], client=sc)
assert again["sha"] == fz["sha"] and sc.calls == calls, "a frozen set is loaded, never regenerated"
path = Q.frozen_path(5, 4, 12, tmp)
d = json.loads(path.read_text(encoding="utf-8")); d["items"][0]["free"] += " "
bad = tmp / "x"; bad.mkdir(); (bad / path.name).write_text(json.dumps(d), encoding="utf-8")
try:
    Q.load_frozen(bad / path.name)
    raise AssertionError("a modified frozen set must be refused")
except SystemExit:
    pass
assert Q.template_share(fz["items"]) <= 0.5

# ---- 3. audit sheet (debug seeds only), verdict, gate
_, sheet = quiet(ARGS + ["--generate-only", "--audit-sheet"], client=sc)
sample = Q.audit_sample(fz)
assert len(sample) == Q.AUDIT_N and len({(fz["items"][k]["canonical"], fz["items"][k]["free"]) for k in sample}) == Q.AUDIT_N
assert all(not fz["items"][k]["fallback"] for k in sample) and fz["items"][sample[0]]["free"] in sheet
g0, _ = quiet(ARGS + ["--gate"], client=sc)
assert g0["gate"]["G1"] is False and not g0["gate"]["pass"] and sc.by["reading"] == 0, "no audit: no gate, and nothing is read"
quiet(ARGS + ["--audit-verdict", "3, 17"])
g2, _ = quiet(ARGS + ["--gate"], client=sc)
assert not g2["gate"]["G1"] and g2["gate"]["G1_audit"]["unfaithful"] == [3, 17] and sc.by["reading"] == 0
quiet(ARGS + ["--audit-verdict", "none"])
gate, gtext = quiet(ARGS + ["--gate"], client=sc)
assert gate["gate"] == {"G1": True, "G1_audit": {"unfaithful": [], "n": Q.AUDIT_N}, "G2": True, "G3": True, "pass": True}, gate["gate"]
assert "free_nonames" not in gate["pipelines"] and gate["mode"] == "gate"
try:
    quiet(ARGS + ["--audit-verdict", "99"])
    raise AssertionError("a number outside the sheet must be refused")
except SystemExit:
    pass

# ---- 4. the sandbox run: every pipeline, the criteria
sc = Scripted(mute_once={fz["items"][5]["free"]})
sync, stext = quiet(ARGS + ["--sandbox"], client=sc)
P = sync["pipelines"]
assert P["canon"]["pct"] == 100 and P["free_names"]["pct"] == 100 and P["free_names"]["asserted_errors"] == 0, P
assert P["free_names_bfs"]["pct"] == 100 and P["free_nonames"]["pct"] < 100 and P["free_template"]["pct"] < 40, P
cr = sync["criteria"]
assert cr["V"] and cr["D1"] and cr["D3"] and cr["D2"] and cr["D2_paired"][1] == 0 and "claim" not in cr, cr
assert sum(q.get("rounds_names", 0) for q in sync["questions"]) >= 1, "a reading without a question line gets one more round"
assert not any("based_in" in q["names_in_memory"] for q in sync["questions"]), "a question never writes into the memory"
assert any("based_in" in q.get("program_names", "") for q in sync["questions"]), "the planted statement was written by the reader"
assert all(q["goal_names"] for q in sync["questions"]) and sync["failed_calls"] == {"fact_readings": 0, "question_names": 0, "question_nonames": 0}

# ---- 5. a question call that fails after the retries counts as wrong, even when its gold is unknown
unk = next(it for it in fz["items"] if it["gold"] == "unknown" and not it["fallback"])
class Down(Scripted):
    def create(self, model, max_tokens, system, messages, **kw):
        u = messages[0]["content"]
        if unk["free"] in u and "NAMES ALREADY IN MEMORY" in u and "A QUESTION IS ASKED" in u:
            e = type("ServiceUnavailableError", (Exception,), {})("down"); e.status_code = 503
            raise e
        return super().create(model, max_tokens, system, messages, **kw)
down, _ = quiet(ARGS + ["--sandbox"], client=Down())
n_unk = sum(it["free"] == unk["free"] for it in fz["items"])
assert down["failed_calls"]["question_names"] == n_unk and down["retries"] == n_unk * len(T.DEFAULT_RETRY_WAITS)
assert round(down["pipelines"]["free_names"]["pct"] * n / 100) == n - n_unk, "a failed call is never a right answer"
assert down["pipelines"]["free_nonames"]["pct"] == P["free_nonames"]["pct"]

# ---- 6. batch = synchronous, and an interrupted batch run resumes without submitting twice
server = {}
batch, _ = quiet(ARGS + ["--sandbox", "--batch", "--state-dir", str(tmp)], client=DualAPI(server))
assert batch["pipelines"] == {k: v for k, v in sync["pipelines"].items()} and batch["criteria"] == sync["criteria"]
assert batch["batches"] == len(server) >= 12, batch["batches"]                  # 12 chained readings, then the questions
server2 = {}
try:
    quiet(ARGS + ["--sandbox", "--batch", "--state-dir", str(tmp)], client=DualAPI(server2, interrupt_first_wait=True))
    raise AssertionError("the interruption did not propagate")
except KeyboardInterrupt:
    pass
assert len(server2) == 1
resumed, _ = quiet(ARGS + ["--sandbox", "--batch", "--state-dir", str(tmp)], client=DualAPI(server2))
assert len(server2) == len(server) and resumed["pipelines"] == batch["pipelines"]

# ---- 7. a non-debug seed: nothing of its questions is printed or kept in clear in the result; seed guards
for argv in (["--seed", "13"], ["--seed", "17", "--batch"], ["--seed", "5"], ["--seed", "19", "--gate"], ["--seed", "19", "--audit-sheet"]):
    try:
        quiet(argv + ["--no-write", "--questions-dir", str(tmp)], client=Scripted())
        raise AssertionError(f"{argv} must be refused")
    except SystemExit:
        pass
keep = Q.DEBUG_SEEDS, Q.USED_SEEDS
Q.DEBUG_SEEDS, Q.USED_SEEDS = (), ()               # seed 5 treated as a measured seed, for this check only
try:
    tmp2 = pathlib.Path(tempfile.mkdtemp())
    meas, mtext = quiet(["--seed", "5", "--worlds", "2", "--sessions", "8", "--questions-dir", str(tmp2), "--no-write"], client=Scripted())
    items = json.loads(Q.frozen_path(5, 2, 8, tmp2).read_text(encoding="utf-8"))["items"]
    assert meas["mode"] == "measurement" and "claim" in meas["criteria"] and "CLAIM" in mtext
    assert not any(it["canonical"] in mtext or it["free"] in mtext for it in items), "a measured seed's questions were printed"
    assert not any("canonical" in q or "free" in q or "program_names" in q for q in meas["questions"])
    try:
        Q.audit_sheet({"args": {"seed": 5}, "items": items, "sha": "x"})
        raise AssertionError("the audit sheet of a non-debug seed must be refused")
    except SystemExit:
        pass
    # a seed is measured once: with a result on disk, the same command stops before any call
    keep_dirs = Q.RESULTS_DIR, Q.QUESTIONS_DIR
    Q.RESULTS_DIR, Q.QUESTIONS_DIR = tmp2 / "res", tmp2 / "arch"
    try:
        sc2 = Scripted()
        first, _ = quiet(["--seed", "5", "--worlds", "2", "--sessions", "8", "--questions-dir", str(tmp2)], client=sc2)
        assert list(Q.RESULTS_DIR.glob("living_questions_D_measurement_*.json")) and (Q.QUESTIONS_DIR / Q.frozen_path(5, 2, 8).name).exists()
        calls = sc2.calls
        try:
            quiet(["--seed", "5", "--worlds", "2", "--sessions", "8", "--questions-dir", str(tmp2)], client=sc2)
            raise AssertionError("a second measurement of the same seed must be refused")
        except SystemExit:
            assert sc2.calls == calls
    finally:
        Q.RESULTS_DIR, Q.QUESTIONS_DIR = keep_dirs
finally:
    Q.DEBUG_SEEDS, Q.USED_SEEDS = keep
assert not (Q.QUESTIONS_DIR / Q.frozen_path(5, 4, 12).name).exists(), "an offline test must leave no frozen set in the repository"
r = Q.main(["--seed", "19", "--worlds", "10", "--batch", "--dry-run"])
assert r["questions"] > 200 and r["estimated_usd"] < 3
# ---- 8. phase D' (logbook 94): the substitution check, and the question note 2
from grandnexus.nexus_logic import parse
lits = lambda g: B.goal_of_program(parse(f"? {g}."))[1]
assert Q.substitutions("Would you describe Rita as patient?", lits("calm(rita)")) == ["calm"]
assert Q.substitutions("Does Bob fly planes?", lits("pilot(bob)")) == ["pilot"]
assert Q.substitutions("Does Uma bake bread?", lits("baker(uma)")) == []               # a part of the name starts a word
assert Q.substitutions("Is Paris where Alice lives?", lits("lives_in(alice, paris)")) == []
assert Q.substitutions("Is Paris where Alice lives?", lits("lives_in(alice, lyon)")) == ["lyon"]
assert Q.substitutions("Is Alice based in Paris?", lits("lives_in(alice, paris)")) == ["lives_in"]
assert Q.substitutions("Where does Alice live?", lits("lives_in(alice, X)")) == []       # a variable is not a name
assert Q.render_goal(lits("lives_in(alice, paris)")) == "Is it true that Alice lives in Paris?"
assert Q.render_goal(lits("not chess_player(bob)")) == "Is it true that it is not the case that Bob is chess player?"
led = Q.Ledger()
chk = lambda q, g: Q.check_substitution(Scripted(), led, Q.JUDGE_MODEL, q, lits(g))
assert chk("Would you describe Rita as patient?", "calm(rita)")["kept"] is False
assert chk("Is Heidi a courageous person?", "brave(heidi)")["kept"] is True
assert chk("Is Paris where Alice lives?", "lives_in(alice, lyon)")["kept"] is False
assert chk("Is Paris where Alice lives?", "lives_in(alice, paris)") == {"checked": False}
SB = ARGS + ["--sandbox"]
n93, _ = quiet(SB + ["--question-note", "1", "--no-substitution-check"], client=Scripted(attract=True))
assert n93["pipelines"]["free_names"]["asserted_errors"] >= 1 and not n93["criteria"]["D1"], "the defect of n°93 is reproduced"
assert n93["substitution_check"]["checked"] == 0
caught, _ = quiet(SB + ["--question-note", "1"], client=Scripted(attract=True))
sc_ = caught["substitution_check"]
assert caught["pipelines"]["free_names"]["asserted_errors"] == 0 and caught["criteria"]["D1"], caught["pipelines"]["free_names"]
assert sc_["refused"] >= n93["pipelines"]["free_names"]["asserted_errors"] and sc_["kept"] > 0
assert caught["pipelines"]["free_names_unchecked"] == n93["pipelines"]["free_names"], "unchecked = the same readings without the check"
note2, _ = quiet(SB, client=Scripted(attract=True))                                       # the defaults of phase D'
assert note2["pipelines"]["free_names"]["asserted_errors"] == 0 and note2["substitution_check"]["refused"] == 0
assert note2["substitution_check"]["on"] and note2["substitution_check"]["question_note"] == 2
assert "free_nonames" in note2["pipelines"]
skip, _ = quiet(SB + ["--skip-nonames"], client=Scripted())
assert "free_nonames" not in skip["pipelines"] and "D2" not in skip["criteria"]
# the frozen set and the audit kept in the repository are used when the Drive folder lacks them
keep_q = Q.QUESTIONS_DIR
Q.QUESTIONS_DIR = tmp
try:
    tmp3 = pathlib.Path(tempfile.mkdtemp())
    again, _ = quiet(ARGS + ["--gate", "--questions-dir", str(tmp3)], client=Scripted())
    assert (tmp3 / Q.frozen_path(5, 4, 12).name).exists() and again["questions_sha"] == fz["sha"]
    assert again["gate"]["G1"] and again["gate"]["pass"], again["gate"]
finally:
    Q.QUESTIONS_DIR = keep_q
# ---- 9. logbook 96: every API call of the tool through the REAL SDK, offline (its own argument checks)
from scripted_translator import sdk_offline_client, SDK_PARAMS
try:
    Scripted().create("m", 8, "x", [{"role": "user", "content": "x"}], temperature=0.0)
    assert SDK_PARAMS is None, "a keyword the installed SDK does not know must be refused"
except TypeError:
    pass
real = sdk_offline_client()
if real is None:
    print("anthropic or httpx not installed: the real-SDK path is not checked")
else:
    led = Q.Ledger()
    assert Q.check_substitution(real, led, Q.JUDGE_MODEL, "Would you describe Rita as patient?", lits("calm(rita)"))["kept"] is False
    assert Q.write_list(real, led, Q.WRITER_MODEL, ["Is Bob a chess player?"])[0]
    assert Q.judge_same(real, led, Q.JUDGE_MODEL, "Is Bob a chess player?", "Does Bob play chess?")
    tmp4 = pathlib.Path(tempfile.mkdtemp())
    viasdk, _ = quiet(["--seed", "5", "--worlds", "2", "--sessions", "8", "--questions-dir", str(tmp4), "--no-write",
                       "--sandbox"], client=sdk_offline_client(Scripted(attract=True)))
    assert viasdk["criteria"]["D1"] and viasdk["substitution_check"]["checked"] > 0, viasdk["substitution_check"]
    import grandnexus.llm_interface.translator_v5 as T5
    trx = T5.Translator(client=sdk_offline_client())
    assert trx._call(T5.SYSTEM_TRANSLATE, "TEXT:\nA is p.\n\nQUESTION (or statement to verify):\nIs A p?", "x")
print("ALL OK")
