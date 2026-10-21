"""Offline test for tools/route_chain.py (Phase 10). Mocked HTTP, fake keys, temp data dir + temp providers file."""
import os, sys, json, glob, tempfile, shutil, io, contextlib
for _k in ("DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY",
           "ANTHROPIC_API_KEY", "ANTHROPIC_API_URL", "ANTHROPIC_MODEL",
           "DEEPSEEK_API_URL", "MOONSHOT_API_URL", "MISTRAL_API_URL", "DEEPSEEK_MODEL", "KIMI_MODEL", "MISTRAL_MODEL",
           "V1RG0_JUDGE_MODEL", "V1RG0_MAX_TOKENS", "V1RG0_SUITS_FILE"):
    os.environ.pop(_k, None)                                  # SAFETY: never use real keys
os.environ.update({"DEEPSEEK_API_KEY": "test-ds", "MOONSHOT_API_KEY": "test-km", "MISTRAL_API_KEY": "test-mi", "XAI_API_KEY": "test-xa", "GEMINI_API_KEY": "test-ge",
                   "V1RG0_MASTER_PW": "test-only"})
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="v1rg0_route_test_")
os.environ["V1RG0_DATA_DIR"] = os.path.join(WORK, "data")
PROV = os.path.join(WORK, "v1rg0_providers.json")
shutil.copy(os.path.join(ROOT, "V1rG0_specific", "v1rg0_providers.json"), PROV)
os.environ["V1RG0_PROVIDERS_FILE"] = PROV
os.chdir(WORK)
ORIGINAL = open(PROV, "rb").read()
USER_SUITS = os.path.join(WORK, "user_suits.json")         # Phase 17: never read a real user_suits.json
os.environ["V1RG0_USER_SUITS_FILE"] = USER_SUITS
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "V1rG0_specific"), os.path.join(ROOT, "unvalidated")]
import requests
from unittest import mock
def _no_network(*a, **k): raise RuntimeError("network disabled in test")
requests.post = requests.get = _no_network
import route_chain
import v1rg0_orchestrator_core as oc
oc.PROVIDERS_FILE = PROV
SUITS = json.load(open(os.path.join(ROOT, "V1rG0_specific", "v1rg0_suits.json")))["suits"]
NOTE = json.load(open(os.path.join(ROOT, "V1rG0_specific", "v1rg0_suits.json")))["scope_note"]
open(os.path.join(WORK, "task.md"), "w").write("TASK: review the router")

def enabled_now():
    return json.load(open(PROV))["enabled_providers"]

IMG_LOG = []                                                  # Phase 19: image calls, kept apart from chat calls
IMG_REPLY = [None]
def run(replies, out, extra=(), approved=True):
    log = []
    def fake_post(url, headers, json, timeout):
        if "images/generations" in url:
            IMG_LOG.append({"url": url, "payload": json, "auth": headers.get("Authorization")})
            return IMG_REPLY[0](json)
        i = len(log)
        log.append({"url": url, "model": json["model"], "system": json["messages"][0]["content"],
                    "prompt": json["messages"][1]["content"], "enabled": enabled_now(), "payload": json})
        item = replies[i]
        if isinstance(item, BaseException):
            raise item
        r = mock.Mock(); r.raise_for_status.return_value = None
        r.json.return_value = {"model": json["model"] + "-served", "choices": [{"message": {"content": item}}],
                               "usage": {"prompt_tokens": 100 + i, "completion_tokens": 10, "total_tokens": 110 + i,
                                         "completion_tokens_details": {"reasoning_tokens": 3}, "model": "x"}}
        return r
    argv = (["--i-approve-this-run"] if approved else []) + ["--task-file", os.path.join(WORK, "task.md"),
            "--out-dir", os.path.join(WORK, out), *extra]
    with mock.patch("requests.post", side_effect=fake_post), contextlib.redirect_stdout(io.StringIO()):
        try:
            code = route_chain.main(argv)
        except Exception as e:
            code = e
    s = sorted(glob.glob(os.path.join(WORK, out, "route_*", "summary_route_*.json")))
    return code, log, (json.load(open(s[-1])) if s else None)

def ok_restored():
    assert open(PROV, "rb").read() == ORIGINAL and enabled_now() == ["deepseek"]

def N(sys_, suit, why): return f"body\nNEXT: system={sys_} suit={suit} reason={why}"

# happy path: DS/Plann.r -> Kimi/Explor.r -> DS/Remind.r -> STOP, then review DS/Plann.r
code, log, s = run([N("kimi", "explor_r", "map the flows"), N("deepseek", "remind_r", "list anchors"),
                    "done\nNEXT: STOP", "review text\nNEXT: STOP"], "happy")
assert code == 0 and len(log) == 4, (code, len(log))
assert [l["model"] for l in log] == ["deepseek-chat", "kimi-k2.6", "deepseek-chat", "deepseek-chat"]
assert [l["system"] for l in log] == [SUITS[k]["prompt"] + "\n\n" + NOTE for k in ("plann_r", "explor_r", "remind_r", "plann_r")]
assert all(NOTE in l["system"] for l in log)  # scope rule on every suited call
assert [("kimi" in l["enabled"]) for l in log] == [False, True, False, False]
assert "explor_r:" in log[0]["prompt"] and "deepseek, kimi" in log[0]["prompt"] and "NEXT: STOP" in log[0]["prompt"]
assert s["stopped_reason"] == "model chose NEXT: STOP" and s["review"]["status"] == "PASS" and s["calls_made"] == 4
assert [st["accepted"] for st in s["steps"]] == [True, True, True]
assert s["steps"][1] ["reason"] == "map the flows" and os.path.exists(s["steps"][1]["output_file"])
ok_restored(); print("happy path OK")

# refusals: each stops the chain, logs refused, and still gets one review call
cases = {
    "disabled system": [N("gemini", "drift_r", "x")],
    "unknown suit":    [N("kimi", "alpha", "x")],
    "malformed":       ["body\nNEXT: go to kimi please"],
    "missing":         ["no routing line here"],
    "same pair":       [N("deepseek", "plann_r", "again")],
    "ping-pong":       [N("kimi", "explor_r", "q1"), N("deepseek", "plann_r", "q2"), N("kimi", "explor_r", "q3")],
    "repeated q":      [N("kimi", "explor_r", "Map the flows"), N("deepseek", "remind_r", "map the FLOWS!")],
}
expect = {"disabled system": "not enabled", "unknown suit": "unknown suit", "malformed": "malformed",
          "missing": "no NEXT", "same pair": "twice in a row", "ping-pong": "ping-pong", "repeated q": "repeated question"}
for i, (name, replies) in enumerate(cases.items()):
    code, log, s = run(replies + ["review\nNEXT: STOP"], f"ref{i}", ["--max-calls", "5"])
    assert code == 0 and len(log) == len(replies) + 1, (name, len(log))
    assert expect[name] in s["stopped_reason"] and s["steps"][-1]["accepted"] is False, (name, s["stopped_reason"])
    assert log[-1]["system"] == SUITS["plann_r"]["prompt"] + "\n\n" + NOTE and "refused" in log[-1]["prompt"]
    ok_restored()
print("refusals OK:", ", ".join(cases))

# caps
chain = [N("kimi", "explor_r", "a"), N("deepseek", "remind_r", "b"), N("kimi", "drift_r", "c"),
         N("deepseek", "explor_r", "d"), N("kimi", "remind_r", "e"), N("deepseek", "drift_r", "f"), "x\nNEXT: STOP"]
code, log, s = run(chain[:2] + ["review\nNEXT: STOP"], "cap2", ["--max-calls", "2"])
assert len(log) == 3 and "max-calls 2" in s["stopped_reason"] and s["review"]["status"] == "PASS"
code, log, s = run(chain, "cap4")                                   # default 4 -> 4 + review = 5
assert len(log) == 5 and "max-calls 4" in s["stopped_reason"] and s["calls_made"] == 5
code, log, s = run(chain, "cap6", ["--max-calls", "6"])             # absolute max hit -> no review
assert len(log) == 6 and "skipped" in s["review"] and s["calls_made"] == 6
code, log, s = run(chain, "cap7", ["--max-calls", "7"])
assert code == 2 and log == [] and s is None
code, log, s = run(chain, "tok", ["--max-est-tokens", "10"])        # spend cap -> stop after 1, no review
assert len(log) == 1 and "estimated tokens" in s["stopped_reason"] and "skipped" in s["review"]
ok_restored(); print("caps OK")

# restore on error / crash
code, log, s = run([N("kimi", "explor_r", "a"), requests.exceptions.ConnectionError("boom"), "review\nNEXT: STOP"], "err")
assert code == 0 and len(log) == 3 and log[1]["enabled"] == ["deepseek", "kimi"] and "NO_RESPONSE" in s["stopped_reason"]
ok_restored()
code, log, s = run([N("kimi", "explor_r", "a"), RuntimeError("crash")], "crash")
assert isinstance(code, RuntimeError) and len(log) == 2 and s["stopped_reason"].startswith("crashed")
assert not os.path.exists(os.path.join(os.environ["V1RG0_DATA_DIR"], "v1rg0_call.lock"))
ok_restored(); print("restore on success/error/crash OK")

# approval required
code, log, s = run(chain, "noapp", approved=False)
assert code == 2 and log == [] and not os.path.exists(os.path.join(WORK, "noapp"))
print("approval required OK")

# each system once: DeepSeek -> Mistral -> Grok -> Kimi -> Gemini -> STOP, then DeepSeek review with extra question
open(os.path.join(WORK, "rq.md"), "w").write("REVIEWQ: is there a reliable path?")
EO = ["--each-system-once", "--allow-systems", "deepseek,kimi,mistral,grok,gemini", "--max-calls", "5",
      "--review-question-file", os.path.join(WORK, "rq.md")]
code, log, s = run([N("mistral", "drift_r", "a"), N("grok", "explor_r", "b"), N("kimi", "remind_r", "c"),
                    N("gemini", "p_rot_ograph_r", "d"), "g\nNEXT: STOP", "review\nNEXT: STOP"], "eo_yes", EO)
assert code == 0 and len(log) == 6, (code, len(log), s["stopped_reason"], [l["model"] for l in log])
assert [l["model"] for l in log] == ["deepseek-chat", "mistral-large-latest", "grok-4.7", "kimi-k2.6", "gemini-3.5-flash-lite", "deepseek-chat"], [l["model"] for l in log]
assert "deepseek" not in log[0]["prompt"].split("Systems you may route to:")[1].split("\n")[0]
assert "none left" in log[4]["prompt"] and "REVIEWQ" in log[5]["prompt"]
assert [len(l["enabled"]) for l in log] == [1, 2, 2, 2, 2, 1]
ok_restored()
# repeat pick -> rerouted to first uncalled system (allow order: kimi), suit kept, no extra call
code, log, s = run([N("mistral", "drift_r", "a"), N("deepseek", "remind_r", "b"), "k\nNEXT: STOP", "review\nNEXT: STOP"], "eo_re", EO)
assert code == 0 and len(log) == 4 and log[2]["model"] == "kimi-k2.6", [l["model"] for l in log]
assert s["steps"][1]["rerouted_from"] == "deepseek" and s["steps"][2]["suit"] == "remind_r"
ok_restored()
# self pick with same suit (Mistral -> Mistral/drift_r, as in the live run) -> rerouted, not refused
code, log, s = run([N("mistral", "drift_r", "a"), N("mistral", "drift_r", "b"), "k\nNEXT: STOP", "review\nNEXT: STOP"], "eo_self", EO)
assert code == 0 and len(log) == 4 and log[2]["model"] == "kimi-k2.6" and s["steps"][1]["rerouted_from"] == "mistral"
ok_restored()
# nothing left: all five called, last one names a called system -> stop + review
code, log, s = run([N("mistral", "drift_r", "a"), N("grok", "explor_r", "b"), N("kimi", "remind_r", "c"),
                    N("gemini", "p_rot_ograph_r", "d"), N("kimi", "drift_r", "e"), "review\nNEXT: STOP"], "eo_none", EO)
assert len(log) == 6 and "no uncalled systems" in s["stopped_reason"], s["stopped_reason"]
ok_restored(); print("each system once OK")

# Phase 12b: run log records input files with sha256
code, log, s = run([N("mistral", "drift_r", "a"), "m\nNEXT: STOP", "review\nNEXT: STOP"], "inputs", EO)
assert s["inputs"]["task_file"]["path"].endswith("task.md") and len(s["inputs"]["task_file"]["sha256"]) == 64
assert s["inputs"]["review_question_file"]["path"].endswith("rq.md") and s["inputs"]["preface_file"] is None
assert s["inputs"]["context_file"]["path"].endswith("CONTEXT_PACK_ROUTED.md")
ok_restored(); print("inputs log OK")
# Phase 12b: step-1 reroute stays inside --first-hop-systems
code, log, s = run([N("deepseek", "remind_r", "x"), "m\nNEXT: STOP", "review\nNEXT: STOP"], "fh_rr",
                   ["--each-system-once", "--first-hop-systems", "mistral", "--allow-systems", "deepseek,kimi,mistral"])
assert len(log) == 3 and log[1]["model"] == "mistral-large-latest" and s["steps"][0]["rerouted_from"] == "deepseek", s["stopped_reason"]
ok_restored(); print("first-hop reroute OK")

# markdown-dressed NEXT line (Mistral live run 3 wrote "**NEXT**: system=...") is accepted
for i, dressed in enumerate(["**NEXT**: system=kimi suit=p_rot_ograph_r reason=x", "- `NEXT: system=kimi suit=p_rot_ograph_r reason=x`",
                             "### NEXT: system=kimi suit=p_rot_ograph_r reason=x"]):
    code, log, s = run(["body\n\n" + dressed, "k\nNEXT: STOP", "review\nNEXT: STOP"], f"md{i}", ["--allow-systems", "deepseek,kimi"])
    assert code == 0 and len(log) == 3 and log[1]["model"] == "kimi-k2.6" and s["steps"][1]["suit"] == "p_rot_ograph_r", (dressed, s["stopped_reason"])
    ok_restored()
print("markdown NEXT OK")

# Phase 14: providers' own usage recorded per call (numbers only) and totalled per system, review included
code, log, s = run([N("kimi", "explor_r", "u1"), "k\nNEXT: STOP", "review\nNEXT: STOP"], "usage", ["--allow-systems", "deepseek,kimi"])
assert code == 0 and len(s["usage"]) == 3 and [u["label"] for u in s["usage"]] == ["step1", "step2", "review"], s["usage"]
assert s["usage"][0]["usage"] == {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110, "completion_tokens_details.reasoning_tokens": 3}
assert s["usage_by_system"] == {"deepseek": {"prompt_tokens": 202, "completion_tokens": 20, "total_tokens": 222},
                                "kimi": {"prompt_tokens": 101, "completion_tokens": 10, "total_tokens": 111}}, s["usage_by_system"]
ok_restored(); print("usage capture OK")

# first hop restricted (the collective: DeepSeek must hand step 1 to Kimi or Mistral)
FH = ["--first-hop-systems", "kimi,mistral", "--allow-systems", "deepseek,kimi,mistral"]
code, log, s = run([N("deepseek", "remind_r", "x"), "review\nNEXT: STOP"], "fh_no", FH)
assert len(log) == 2 and "step 1 must route" in s["stopped_reason"] and "kimi, mistral" in log[0]["prompt"]
code, log, s = run([N("mistral", "drift_r", "a"), N("kimi", "explor_r", "b"), "k\nNEXT: STOP", "review\nNEXT: STOP"], "fh_yes", FH)
assert code == 0 and len(log) == 4 and [l["model"] for l in log][1:3] == ["mistral-large-latest", "kimi-k2.6"]
ok_restored(); print("first hop OK")

# mistral: refused unless allowed; when allowed, on for exactly its one call, extra_providers request format
code, log, s = run([N("mistral", "drift_r", "alternatives"), "review\nNEXT: STOP"], "mi_no")
assert len(log) == 2 and "not enabled" in s["stopped_reason"]
code, log, s = run([N("mistral", "drift_r", "alternatives"), "m\nNEXT: STOP", "review\nNEXT: STOP"], "mi_yes",
                   ["--allow-systems", "deepseek,mistral"])
assert code == 0 and len(log) == 3
assert log[1]["url"] == "https://api.mistral.ai/v1/chat/completions" and log[1]["model"] == "mistral-large-latest"
assert "thinking" not in log[1]["payload"] and log[1]["system"] == SUITS["drift_r"]["prompt"] + "\n\n" + NOTE
assert [("mistral" in l["enabled"]) for l in log] == [False, True, False]
ok_restored(); print("mistral one-call window OK")

# suit prompts in the transmission suit: blank -> neutral, default -> P_ROT_OGRAPH_R (unchanged default persona)
from v1rg0_transmission_suit import suit_prompt, NEUTRAL_PROMPT
assert suit_prompt({"suit_id": "blank"}) == NEUTRAL_PROMPT + "\n\n" + NOTE
assert suit_prompt({}).startswith("You are P_ROT_OGRAPH_R") and suit_prompt({"system": "S"}) == "S"
try: suit_prompt({"suit_id": "alpha"}); raise AssertionError
except ValueError: pass
assert set(SUITS) == {"plann_r", "p_rot_ograph_r", "drift_r", "explor_r", "remind_r", "blank"}
print("suit prompts OK")

# ---- Phase 13: extended thinking, --visits-per-system, --allow-long-run ----
X = ["--extend-thinking", "--max-calls", "5"]
def E(why): return f"thinking\nNEXT: EXTEND reason={why}"
MODEL = {"deepseek": "deepseek-chat", "kimi": "kimi-k2.6", "mistral": "mistral-large-latest", "grok": "grok-4.7", "gemini": "gemini-3.5-flash-lite"}
# no flag: EXTEND line refused
code, log, s = run([E("more"), "review\nNEXT: STOP"], "x_off")
assert len(log) == 2 and "needs --extend-thinking" in s["stopped_reason"] and "extended" not in s["steps"][0]
ok_restored()
# explicit EXTEND: one extra call to itself (same suit), then a second self-pick is refused (no visit limit)
code, log, s = run([N("kimi", "explor_r", "a"), E("deeper"), N("kimi", "drift_r", "again"), "review\nNEXT: STOP"], "x_basic", X)
assert code == 0 and [l["model"] for l in log] == ["deepseek-chat", "kimi-k2.6", "kimi-k2.6", "deepseek-chat"], [l["model"] for l in log]
assert [st["extended"] for st in s["steps"]] == [False, False, True] and s["steps"][2]["suit"] == "explor_r"
assert "ONE extended-thinking call" in log[2]["prompt"] and "NEXT: EXTEND" in log[1]["prompt"] and "is used" in log[2]["prompt"]
assert "already used its extended-thinking call" in s["stopped_reason"] and s["extends_used"] == ["kimi"]
assert log[2]["system"] == SUITS["explor_r"]["prompt"] + "\n\n" + NOTE
ok_restored()
# self-pick counts as the extend (suit stays), then the turn moves on
code, log, s = run([N("kimi", "explor_r", "a"), N("kimi", "drift_r", "more on a"), N("deepseek", "remind_r", "b"),
                    "d\nNEXT: STOP", "review\nNEXT: STOP"], "x_self", X)
assert code == 0 and [l["model"] for l in log] == ["deepseek-chat", "kimi-k2.6", "kimi-k2.6", "deepseek-chat", "deepseek-chat"]
assert s["steps"][1]["next"]["extend"] is True and s["steps"][2]["extended"] is True and s["steps"][2]["suit"] == "explor_r"
assert s["stopped_reason"] == "model chose NEXT: STOP" and s["review"]["status"] == "PASS"
ok_restored()
# extend + visit limit: after the extend, a self-pick is rerouted instead of refused
EV = ["--extend-thinking", "--visits-per-system", "1", "--allow-systems", "deepseek,kimi,mistral", "--max-calls", "5"]
code, log, s = run([N("kimi", "explor_r", "a"), E("deeper"), N("kimi", "drift_r", "c"), "m\nNEXT: STOP", "review\nNEXT: STOP"], "x_rr", EV)
assert [l["model"] for l in log] == ["deepseek-chat", "kimi-k2.6", "kimi-k2.6", "mistral-large-latest", "deepseek-chat"], [l["model"] for l in log]
assert s["steps"][2]["rerouted_from"] == "kimi" and s["steps"][3]["suit"] == "drift_r"
ok_restored()
# token cap stops before the extended call
code, log, s = run([E("more")], "x_tok", X + ["--max-est-tokens", "10"])
assert len(log) == 1 and "estimated tokens" in s["stopped_reason"] and "skipped" in s["review"]
ok_restored()
# flag checks before any call
for name, extra in {"31 with long run": ["--allow-long-run", "--max-calls", "31"],   # Phase 22: was 21
                    "7 without long run": ["--extend-thinking", "--max-calls", "7"],
                    "each-once vs visits 3": ["--each-system-once", "--visits-per-system", "3"]}.items():
    code, log, s = run([E("x")], "x_flag" + str(len(name)), extra)
    assert code == 2 and log == [] and s is None, name
print("extended thinking OK")

# 21-call ceiling: 5 systems x 3 visits, each extends once -> 15 + 5 = 20 routed, + guaranteed review = 21
ORDER = ["deepseek", "mistral", "grok", "kimi", "gemini"]
SUIT_CYCLE = ["drift_r", "explor_r", "remind_r", "p_rot_ograph_r", "plann_r"]
LR = ["--extend-thinking", "--allow-long-run", "--allow-systems", ",".join(ORDER)]
def script(visits, extend_every_visit=False):
    out, k = [], 0
    for v in range(visits):
        nxt_sys = ORDER[(v + 1) % 5]
        if v < 5 or extend_every_visit:
            out.append(N(ORDER[v % 5], "blank", f"self {v}"))      # self-pick = extend (rerouted once used)
            if v < 5:
                out.append(N(nxt_sys, SUIT_CYCLE[v % 5], f"r{v}"))
        else:
            out.append(N(nxt_sys, SUIT_CYCLE[v % 5], f"r{v}"))
    return out + ["review\nNEXT: STOP"]
code, log, s = run(script(15), "lr21", LR + ["--visits-per-system", "3", "--max-calls", "15"])
assert code == 0 and len(log) == 21, (len(log), s["stopped_reason"])
assert s["routed_calls"] == 20 and s["extend_calls"] == 5 and sorted(s["extends_used"]) == sorted(ORDER)
assert s["visits"] == {x: 3 for x in ORDER} and "no systems with visits left" in s["stopped_reason"], s["stopped_reason"]
assert s["review"]["status"] == "PASS" and s["calls_made"] == 21 and log[-1]["model"] == "deepseek-chat"
assert [l["model"] for l in log[:20]] == [MODEL[x] for v in range(15) for x in ([ORDER[v % 5]] * (2 if v < 5 else 1))]
ok_restored()
# hard ceiling wins (Phase 22: was 20, now 30): 4 visits x 5 + 5 extends = 25 routed now fits under it
code, log, s = run(script(20), "lr_ceiling", LR + ["--visits-per-system", "4", "--max-calls", "20"])
assert len(log) == 26 and s["routed_calls"] == 25 and "no systems with visits left" in s["stopped_reason"], (len(log), s["stopped_reason"])
assert s["review"]["status"] == "PASS" and s["calls_made"] == 26
ok_restored()
# Phase 22: the long-run ceiling is 30 routed calls. 7 visits x 5 systems + 5 extends would be 40 -> stops at 30, review makes 31
assert route_chain.LONG_RUN_MAX_ROUTED == 30
code, log, s = run(script(35), "lr_ceiling30", LR + ["--visits-per-system", "7", "--max-calls", "30"])
assert len(log) == 31 and "hard ceiling of 30" in s["stopped_reason"] and s["routed_calls"] == 30, (len(log), s["stopped_reason"])
assert s["review"]["status"] == "PASS" and s["calls_made"] == 31 and log[-1]["model"] == "deepseek-chat"
ok_restored()
print("30-call ceiling OK")
# a model that tries to extend on every visit still gets only one extend each and never passes 21
code, log, s = run(script(15, extend_every_visit=True), "lr_greedy", LR + ["--visits-per-system", "3", "--max-calls", "15"])
assert len(log) <= 21 and s["extend_calls"] <= 5 and s["calls_made"] <= 21, (len(log), s["stopped_reason"])
assert any(st.get("rerouted_from") for st in s["steps"])
ok_restored()
# without --allow-long-run the old 6-call line holds, extends included, and the review is skipped at 6
code, log, s = run([E("x"), N("kimi", "explor_r", "a"), E("y"), N("deepseek", "remind_r", "b"), N("kimi", "drift_r", "c"),
                    N("deepseek", "explor_r", "d"), "review\nNEXT: STOP"], "x_six", ["--extend-thinking", "--max-calls", "6"])
assert len(log) == 6 and "hard ceiling of 6" in s["stopped_reason"] and "skipped" in s["review"], (len(log), s["stopped_reason"])
ok_restored(); print("21-call ceiling OK")

# ---- Phase 15: --review-replaces-ask ----
open(os.path.join(WORK, "art.md"), "w").write("ARTICLEQ: write the final article")
RA = ["--review-question-file", os.path.join(WORK, "art.md")]
code, log, s = run([N("kimi", "explor_r", "a"), "k\nNEXT: STOP", "article\nNEXT: STOP"], "ra_off", RA)
assert "ARTICLEQ" in log[-1]["prompt"] and "summarise what was learned" in log[-1]["prompt"] and s["review_replaces_ask"] is False
code, log, s = run([N("kimi", "explor_r", "a"), "k\nNEXT: STOP", "article\nNEXT: STOP"], "ra_on", RA + ["--review-replaces-ask"])
assert code == 0 and len(log) == 3 and s["review"]["status"] == "PASS" and s["review_replaces_ask"] is True
assert "=== YOUR TASK ===\nARTICLEQ" in log[-1]["prompt"] and "summarise what was learned" not in log[-1]["prompt"]
assert log[-1]["prompt"].rstrip().endswith("End with: NEXT: STOP") and "=== REPLIES ===" in log[-1]["prompt"]
code, log, s = run([N("kimi", "explor_r", "a")], "ra_bad", ["--review-replaces-ask"])
assert code == 2 and log == [], code
ok_restored(); print("review replaces ask OK")

# ---- Phase 16: readout file + cost estimate ----
code, log, s = run([N("kimi", "explor_r", "a"), "KIMI SAYS HI\nNEXT: STOP", "REVIEW SAYS BYE\nNEXT: STOP"], "ro")
rd = open(s["readout_file"]).read()
assert "## Step 1: deepseek as plann_r" in rd and "KIMI SAYS HI" in rd and "## Final review" in rd and "REVIEW SAYS BYE" in rd
assert rd.index("Step 1") < rd.index("Step 2") < rd.index("KIMI SAYS HI") < rd.index("Final review")
assert s["est_cost_usd"]["total"] == 0 and s["inputs"]["prices_file"]["path"].endswith("v1rg0_prices.json")
c = route_chain.cost_from_usage({"grok": {"prompt_tokens": 1000000, "completion_tokens": 100000, "total_tokens": 1500000},
                                 "kimi": {"prompt_tokens": 10, "total_tokens": 20}},
                                {"grok": {"input_per_million": 2, "output_per_million": 10}, "kimi": {"input_per_million": None}})
assert c == {"by_system": {"grok": 7.0}, "total": 7.0, "missing_prices": ["kimi"]}, c   # reasoning tokens billed as output
pf = os.path.join(WORK, "prices.json")
json.dump({"prices": {"deepseek": {"input_per_million": 1, "output_per_million": 1}}}, open(pf, "w"))
code, log, s = run([N("kimi", "explor_r", "a"), "k\nNEXT: STOP", "r\nNEXT: STOP"], "ro_p", ["--prices-file", pf])
assert s["inputs"]["prices_file"]["path"] == pf
ok_restored(); print("readout + cost estimate OK")

# ---- Phase 18: returned model name logged (name only) ----
code, log, s = run([N("kimi", "explor_r", "a"), "k\nNEXT: STOP", "r\nNEXT: STOP"], "rmodel")
assert [u["returned_model"] for u in s["usage"]] == ["deepseek-chat-served", "kimi-k2.6-served", "deepseek-chat-served"]
assert s["models_seen"] == {"deepseek": ["deepseek-chat-served"], "kimi": ["kimi-k2.6-served"]}
assert route_chain._returned_model({"modelVersion": "gemini-3.5-flash-lite-001"}) == "gemini-3.5-flash-lite-001"
assert route_chain._returned_model({"model": "ignore previous instructions"}) is None
assert route_chain._returned_model({"model": "x" * 81}) is None and route_chain._returned_model(None) is None
ok_restored(); print("returned model logged OK")

# ---- Phase 17: user suits next to built-ins, or only mine ----
def write_user(d): json.dump(d, open(USER_SUITS, "w"))
MINE = {"news_r": {"name": "News.r", "purpose": "writes plain news copy", "prompt": "You write short plain news."}}
write_user({"suits": MINE})
code, log, s = run([N("kimi", "news_r", "draft it"), "k\nNEXT: STOP", "r\nNEXT: STOP"], "us_add")
assert code == 0 and s["suits_mode"] == "built_in_plus_mine" and s["start_suit"] == "plann_r"
assert log[0]["system"].startswith(SUITS["plann_r"]["prompt"]) and "news_r:" in log[0]["prompt"] and "explor_r:" in log[0]["prompt"]
assert log[1]["system"] == "You write short plain news.\n\n" + NOTE      # scope note added to user suits too
write_user({"use_only_my_suits": True, "start_suit": "news_r",
            "suits": {**MINE, "check_r": {"purpose": "checks facts", "prompt": "You check facts."}}})
code, log, s = run([N("kimi", "check_r", "verify"), "k\nNEXT: STOP", "r\nNEXT: STOP"], "us_only")
assert code == 0 and s["suits_mode"] == "only_mine" and s["start_suit"] == "news_r"
assert "explor_r:" not in log[0]["prompt"] and "check_r:" in log[0]["prompt"]
assert [l["system"].split("\n")[0] for l in log] == ["You write short plain news.", "You check facts.", "You write short plain news."]
code, log, s = run([N("kimi", "explor_r", "x"), "r\nNEXT: STOP"], "us_only_ref", ["--max-calls", "5"])
assert "unknown suit" in s["stopped_reason"]                     # built-ins are off in only-mine mode
bad = {"built-in id": {"suits": {"plann_r": MINE["news_r"]}},
       "bad id": {"suits": {"News R": MINE["news_r"]}},
       "long purpose": {"suits": {"news_r": {"purpose": "x" * 161, "prompt": "p"}}},
       "long prompt": {"suits": {"news_r": {"purpose": "p", "prompt": "x" * 4001}}},
       "too many": {"suits": {f"s{i:02d}": MINE["news_r"] for i in range(21)}},
       "only, no start": {"use_only_my_suits": True, "suits": MINE},
       "only, empty": {"use_only_my_suits": True, "start_suit": "news_r", "suits": {}},
       "start unknown": {"start_suit": "nope", "suits": MINE},
       "flag not bool": {"use_only_my_suits": "yes", "suits": MINE}}
for i, (name, d) in enumerate(bad.items()):
    write_user(d)
    code, log, s = run(["never"], f"us_bad{i}")
    assert len(log) == 0 and s is None and code != 0, (name, code, len(log))
open(USER_SUITS, "w").write("{not json")
code, log, s = run(["never"], "us_badjson"); assert len(log) == 0 and s is None
os.remove(USER_SUITS)
ok_restored(); print("user suits OK:", len(bad) + 1, "refusals")

# ---- Phase 21: Anthropic usage names map onto the totals and cost; returned model logged ----
u21 = route_chain._usage_aliases(route_chain._numeric_usage({"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 0}))
assert (u21["prompt_tokens"], u21["completion_tokens"], u21["total_tokens"]) == (1000, 500, 1500) and u21["input_tokens"] == 1000
assert route_chain._usage_aliases({"prompt_tokens": 5, "total_tokens": 9}) == {"prompt_tokens": 5, "total_tokens": 9}
assert route_chain._usage_aliases(None) is None
c21 = route_chain.cost_from_usage({"claude": u21}, {"claude": {"input_per_million": 2, "output_per_million": 10}})
assert abs(c21["by_system"]["claude"] - 0.007) < 1e-9
assert route_chain._returned_model({"model": "claude-sonnet-5-5", "content": []}) == "claude-sonnet-5-5"
print("anthropic usage OK")

# ---- Phase 19: one image from the final review only ----
import base64 as _b64, hashlib, image_step
from PIL import Image as _Image
def _png(color, size=(200, 100)):
    b = io.BytesIO(); _Image.new("RGB", size, color).save(b, "PNG"); return b.getvalue()
PNG = _png((10, 20, 30))
MARKF = os.path.join(WORK, "mark.png"); _Image.new("RGBA", (40, 40), (255, 0, 0, 255)).save(MARKF)
os.environ["V1RG0_MARK_FILE"] = MARKF
def img_ok(payload):
    r = mock.Mock(); r.raise_for_status.return_value = None
    r.json.return_value = {"model": payload["model"], "data": [{"b64_json": _b64.b64encode(PNG).decode()}]}
    return r
IMG_REPLY[0] = img_ok
rq = os.path.join(WORK, "rq.md"); open(rq, "w").write("Write a short greeting card message.")
BLOCK = "Card text here.\nIMAGE_DESCRIPTION:\nA calm sunrise over hills, soft gold light.\nEND_IMAGE\nNEXT: STOP"
IMG = ["--image-from-review", "--review-question-file", rq]
# flag off: no image call even if the review writes a block
IMG_LOG.clear(); code, log, s = run([N("kimi", "explor_r", "a"), "k\nNEXT: STOP", BLOCK], "img_off")
assert IMG_LOG == [] and s["image"] is None and s["image_cost_usd"] == 0
# flag on: exactly one call, n=1, model 2.0, saved + stamped, cost line, review ask carries the block rules
IMG_LOG.clear(); code, log, s = run([N("kimi", "explor_r", "a"), "k\nNEXT: STOP", BLOCK], "img_on", IMG)
assert code == 0 and len(IMG_LOG) == 1 and IMG_LOG[0]["payload"] == {"model": "grok-imagine-image-2.0", "n": 1,
    "prompt": "A calm sunrise over hills, soft gold light. " + image_step.SAFETY_LINE}
assert "no real people" in IMG_LOG[0]["payload"]["prompt"] and s["image"]["safety_line_added"]
assert IMG_LOG[0]["url"] == "https://api.x.ai/v1/images/generations" and IMG_LOG[0]["auth"] == "Bearer test-xa"
assert f"at most {image_step.desc_limit(image_step.load_image_providers()['providers']['xai_image'])} characters" in log[-1]["prompt"]
assert "IMAGE_DESCRIPTION:" in log[-1]["prompt"] and "Write a short greeting card message." in log[-1]["prompt"]
assert "IMAGE_DESCRIPTION" not in log[0]["prompt"] and "IMAGE_DESCRIPTION" not in log[1]["prompt"]
im = s["image"]; assert im["made"] and open(im["file"], "rb").read() == PNG and s["image_cost_usd"] == 0.04
with _Image.open(im["marked_file"]) as m:
    assert m.size == (200, 100) and m.getpixel((200 - 4 - 8, 100 - 4 - 8))[:3] == (255, 0, 0) and m.getpixel((5, 5))[:3] == (10, 20, 30)
rd = open(s["readout_file"]).read(); assert "## Image (AI-generated)" in rd and "grok-imagine-image-2.0" in rd and "http" not in rd.split("## Image")[1]
# routed step writing a block: ignored, still only the review's one image
ROUTED_BLOCK = "IMAGE_DESCRIPTION:\nA red car.\nEND_IMAGE\n"
IMG_LOG.clear(); code, log, s = run(["body\n" + ROUTED_BLOCK + "NEXT: system=kimi suit=explor_r reason=a",
                                     ROUTED_BLOCK + "NEXT: STOP", "plain review, no block\nNEXT: STOP"], "img_routed", IMG)
assert len(IMG_LOG) == 0 and [st.get("image_request_ignored") for st in s["steps"]] == ["routed step", "routed step"]
assert s["image"]["refused"] == "no IMAGE_DESCRIPTION block" and s["image_cost_usd"] == 0
# code-level guard: only the review label may call
cfg = image_step.load_image_providers()["providers"]["xai_image"]
for lab in ("step1", "step2_ext", "review2"):
    try: image_step.make_image(lab, "x", cfg, 0); raise AssertionError(lab)
    except image_step.ImageStepError as e: assert "only the final review" in str(e)
try: image_step.make_image("review", "x", cfg, 1); raise AssertionError("cap")
except image_step.ImageStepError as e: assert "1 image per run" in str(e)
# bad blocks / blocked terms: refused, no call
bads = {"none": "just text\nNEXT: STOP",
        "two": BLOCK.replace("NEXT: STOP", "") + "\n" + BLOCK,
        "empty": "x\nIMAGE_DESCRIPTION:\n   \nEND_IMAGE\nNEXT: STOP",
        "long": "x\nIMAGE_DESCRIPTION:\n" + "a" * (image_step.desc_limit(cfg) + 1) + "\nEND_IMAGE\nNEXT: STOP",
        "brand": "x\nIMAGE_DESCRIPTION:\nA cartoon mouse like Disney's\nEND_IMAGE\nNEXT: STOP"}
for i, (name, rev) in enumerate(bads.items()):
    IMG_LOG.clear(); code, log, s = run(["k\nNEXT: STOP", rev], f"img_bad{i}", IMG)
    assert len(IMG_LOG) == 0 and not s["image"]["made"] and s["image"].get("refused"), (name, s["image"])
    assert s["image_cost_usd"] == 0
# link replies: only https on x.ai, size-capped; provider error: logged, no retry
def img_url(u):
    def f(payload):
        r = mock.Mock(); r.raise_for_status.return_value = None; r.json.return_value = {"data": [{"url": u}]}; return r
    return f
for u in ("http://imgen.x.ai/a.png", "https://evil.example/x.ai/a.png", "https://x.ai.evil.com/a.png"):
    IMG_REPLY[0] = img_url(u); IMG_LOG.clear()
    code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_badurl" + str(len(u)), IMG)
    assert len(IMG_LOG) == 1 and "link refused" in s["image"]["error"] and not s["image"]["made"], u
IMG_REPLY[0] = img_url("https://imgen.x.ai/a.png")
g = mock.Mock(status_code=200); g.raise_for_status.return_value = None; g.iter_content.return_value = [PNG]
with mock.patch("requests.get", return_value=g) as gm:
    code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_url_ok", IMG)
assert s["image"]["made"] and gm.call_count == 1 and gm.call_args.kwargs["allow_redirects"] is False
g3 = mock.Mock(status_code=302); g3.raise_for_status.return_value = None
with mock.patch("requests.get", return_value=g3):
    code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_url_redirect", IMG)
assert not s["image"]["made"] and "302" in s["image"]["error"] and "imgen" not in open(s["readout_file"]).read()
g.iter_content.return_value = [b"\x89PNG\r\n\x1a\n" + b"0" * 20_000_001]
with mock.patch("requests.get", return_value=g):
    code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_url_big", IMG)
assert "larger than" in s["image"]["error"]
def img_fail(payload): raise requests.exceptions.ConnectionError("boom")
IMG_REPLY[0] = img_fail; IMG_LOG.clear()
code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_err", IMG)
assert len(IMG_LOG) == 1 and "ConnectionError" in s["image"]["error"] and s["image_cost_usd"] == 0
IMG_REPLY[0] = lambda p: (lambda r: (setattr(r, "raise_for_status", lambda: None), r.json.__setattr__("return_value", {"data": [{"b64_json": _b64.b64encode(b"GIF89a").decode()}]}), r)[-1])(mock.Mock())
code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_notpng", IMG)
assert "not a PNG or JPEG" in s["image"]["error"]
IMG_REPLY[0] = img_ok
# harmless words pass: "no logos", "in the style of a pencil sketch", brand-like substrings inside other words
_bt = image_step.load_image_providers()["blocked_terms"]
for ok in ("A star, no logos or text, in the style of a pencil sketch.", "A monikers list", "Applesauce on a table"):
    assert image_step.check_description(ok, cfg, _bt) is None, ok
assert image_step.check_description("A Nike shoe", cfg, _bt)
# safety line always fits: description at the limit passes, one over is refused, full prompt never exceeds 1000
_lim = image_step.desc_limit(cfg)
assert image_step.check_description("a" * _lim, cfg, []) is None and image_step.check_description("a" * (_lim + 1), cfg, [])
assert len(image_step.full_prompt("a" * _lim)) == int(cfg["max_prompt_chars"]) == 1500
# black mark on light corners, white on dark; mark only shrunk, never cleaned up
MD = os.path.join(WORK, "marks"); os.makedirs(MD)
_Image.new("RGBA", (50, 80), (0, 0, 0, 255)).save(os.path.join(MD, "deux_symbol_black.png"))
_Image.new("RGBA", (50, 80), (255, 255, 255, 255)).save(os.path.join(MD, "deux_symbol_white.png"))
del os.environ["V1RG0_MARK_FILE"]; os.environ["V1RG0_MARK_DIR"] = MD
for color, want in (((240, 240, 230), "deux_symbol_black.png"), ((15, 15, 25), "deux_symbol_white.png")):
    PNG = _png(color, (1000, 600)); IMG_REPLY[0] = img_ok
    code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_mark_" + want[11:16], IMG)
    assert s["image"]["mark_used"] == want, s["image"]
    with _Image.open(s["image"]["marked_file"]) as m:
        px = m.getpixel((1000 - 20 - 40, 600 - 20 - 64))[:3]
        assert px == ((0, 0, 0) if "black" in want else (255, 255, 255)) and m.getpixel((5, 5))[:3] == color
# the real grainy symbols: shrink only, files themselves untouched
REAL = "/workspace/V1rG0_assets"
if os.path.isfile(os.path.join(REAL, "deux_symbol_black.png")):
    _h = lambda f: hashlib.sha256(open(os.path.join(REAL, f), "rb").read()).hexdigest()[:8]
    assert (_h("deux_symbol_black.png"), _h("deux_symbol_white.png")) == ("e1dec0e4", "4609ad1d")
    bp = os.path.join(WORK, "real_base.png"); _Image.new("RGB", (1024, 1024), (200, 200, 200)).save(bp)
    image_step.stamp(bp, os.path.join(REAL, "deux_symbol_black.png"), os.path.join(WORK, "real_marked.png"))
    assert (_h("deux_symbol_black.png"), _h("deux_symbol_white.png")) == ("e1dec0e4", "4609ad1d")
    print("real symbol stamp OK")
del os.environ["V1RG0_MARK_DIR"]; PNG = _png((10, 20, 30))
# no mark file: original only
os.environ["V1RG0_MARK_FILE"] = os.path.join(WORK, "none.png")
code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_nomark", IMG)
assert s["image"]["made"] and s["image"]["marked_file"] is None
# ---- Phase 20: exact card text added by code ----
TXT = os.path.join(WORK, "card.txt")
open(TXT, "w").write("TOP: God, Devil and Death are all one Entity.\nBOTTOM: The separation between them is the illusion. Only the Monad is real.\n")
os.environ["V1RG0_MARK_FILE"] = MARKF; PNG = _png((0, 0, 0), (1024, 1024)); IMG_REPLY[0] = img_ok; IMG_LOG.clear()
code, log, s = run(["k\nNEXT: STOP", BLOCK], "img_text", IMG + ["--image-text-file", TXT])
im = s["image"]; assert code == 0 and im["made"] and len(IMG_LOG) == 1
assert image_step.TEXT_NOTE in log[-1]["prompt"] and "God, Devil" not in IMG_LOG[0]["payload"]["prompt"]
assert open(im["file"], "rb").read() == PNG                                  # clean original untouched
with _Image.open(im["text_file"]) as t:
    assert t.width == 1024 and t.height > 1024 and t.getpixel((0, 0)) == (0, 0, 0)
    top_band = t.crop((0, 0, 1024, (t.height - 1024) // 2)); assert top_band.getextrema()[0][1] > 200   # white text present
assert s["card_text_file_sha256"] == hashlib.sha256(open(TXT, "rb").read()).hexdigest()
assert im["text_marked_file"] and im["card_text"]["top"] == "God, Devil and Death are all one Entity."
rd = open(s["readout_file"]).read(); assert "added by code" in rd and os.path.basename(im["text_marked_file"]) in rd
# bad card text files refuse to start, before any call
for i, body in enumerate(["", "MIDDLE: x\n", "TOP: a\nTOP: b\n", "TOP: " + "a" * 121 + "\n"]):
    open(TXT, "w").write(body)
    code, log, s = run(["never"], f"img_badtext{i}", IMG + ["--image-text-file", TXT]); assert len(log) == 0 and s is None, body
open(TXT, "w").write("TOP: hi\n")
code, log, s = run(["never"], "img_text_noflag", ["--image-text-file", TXT]); assert len(log) == 0 and s is None
os.environ["V1RG0_FONT_FILE"] = os.path.join(WORK, "nofont.ttf")
code, log, s = run(["never"], "img_text_nofont", IMG + ["--image-text-file", TXT]); assert len(log) == 0 and s is None
del os.environ["V1RG0_FONT_FILE"]; os.environ["V1RG0_MARK_FILE"] = os.path.join(WORK, "none.png"); PNG = _png((10, 20, 30))
print("card text OK")
# start refusals: no review question file; missing key
code, log, s = run(["never"], "img_noq", ["--image-from-review"]); assert len(log) == 0 and s is None
_xa = os.environ.pop("XAI_API_KEY")
code, log, s = run(["never"], "img_nokey", IMG); assert len(log) == 0 and s is None
os.environ["XAI_API_KEY"] = _xa
ok_restored(); print("image from review OK")

for _k in ("MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY"): os.environ.pop(_k, None)
shutil.rmtree(WORK, ignore_errors=True)
print("ROUTE TEST OK")
