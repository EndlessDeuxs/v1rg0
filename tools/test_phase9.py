"""Offline tests for Phase 9 (items 1-8). No network, fake keys only, temp data dir."""
import os, sys, json, glob, tempfile, shutil, io, contextlib, inspect
for _k in ("DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY",
           "ANTHROPIC_API_KEY", "ANTHROPIC_API_URL", "ANTHROPIC_MODEL",
           "V1RG0_JUDGE_MODEL", "V1RG0_MAX_TOKENS", "V1RG0_MAX_PACKETS"):
    os.environ.pop(_k, None)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="v1rg0_phase9_test_")
os.environ["V1RG0_DATA_DIR"] = os.path.join(WORK, "data")
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "V1rG0_specific"), os.path.join(ROOT, "unvalidated")]
import requests
from unittest import mock
def _no_network(*a, **k): raise RuntimeError("network disabled in test")
requests.post = requests.get = _no_network

import v1rg0_transmission_suit as ts_mod
from v1rg0_transmission_suit import V1rg0TransmissionSuit, provider_family, CHAT_COMPLETIONS_FAMILIES
from v1rg0_extra_providers import V1rg0ExtendedTransmissionSuit, EXTRA_ENV_KEYS
import v1rg0_validation_gate as vg_mod
from v1rg0_validation_gate import V1rg0ValidationGate
import v1rg0_orchestrator_core as oc
from v1rg0_proposal_builder import ProposalBuilder as RealPB

class FakeKC:
    def get_key(self, k): return "fake-" + k
suit = V1rg0ExtendedTransmissionSuit(FakeKC()); gate = V1rg0ValidationGate()
reply = {"status": "success", "data": {"choices": [{"message": {"content": "HI"}}]}}

# 1) one provider list: every routable model id is extractable, and vice versa for unknowns
ids = ["deepseek_chat", "kimi_k2_6", *[m for m in EXTRA_ENV_KEYS if "claude" not in m]]
# Phase 21: Claude is the one non-chat-completions slot (Anthropic Messages shape), checked on its own
assert suit._select_endpoint("claude_sonnet") is not None and provider_family("claude_sonnet") is None
assert gate.extract_content({"status": "success", "data": {"content": [{"type": "text", "text": "HI"}]}}, "claude_sonnet") == "HI"
assert gate.extract_content(reply, "claude_sonnet") is None        # an OpenAI-shaped reply is not read as Claude
for mid in ids:
    assert suit._select_endpoint(mid) is not None, mid
    assert provider_family(mid) in CHAT_COMPLETIONS_FAMILIES, mid
    assert gate.extract_content(reply, mid) == "HI", mid
assert suit._select_endpoint("mystery_model") is None and provider_family("mystery_model") is None
assert vg_mod.provider_family is ts_mod.provider_family           # shared, not copied
print("1 OK provider sets aligned:", ids)

# 2) shared status vocabulary
for s in ("PASS", "HELD", "REJECTED", "EMIT", "received", "completed"):
    assert not [w for w in gate.validate_task({"task_id": 1, "timestamp": 0, "status": s, "payload": {"prompt": "x"}})["warnings"]
                if "Non-standard" in w], s
assert gate.validate_task({"task_id": 1, "timestamp": 0, "status": "bogus", "payload": {"prompt": "x"}})["warnings"]
assert gate.validate_result({"status": "success", "model_id": "m", "data": {}})["valid"]
assert gate.validate_result({"status": "HELD", "model_id": "m", "data": {}})["valid"]
assert not gate.validate_result({"status": "bogus", "model_id": "m", "data": {}})["valid"]
assert vg_mod.normalize_status("EMIT") == "PASS" and oc.MIT_TO_PROPOSAL["EMIT"] == "PASS"
print("2 OK status enums shared, EMIT->PASS kept")

# 3) no self._model_name mutation in transmit
sent = []
def fake_post(url, headers, json, timeout):
    sent.append(json); r = mock.Mock(); r.raise_for_status.return_value = None
    r.json.return_value = {"choices": [{"message": {"content": "ok"}}]}; return r
with mock.patch("requests.post", side_effect=fake_post):
    suit.transmit("deepseek_chat", {"prompt": "a"}); suit.transmit("kimi_k2_6", {"prompt": "b"})
assert not hasattr(suit, "_model_name") and "_model_name" not in inspect.getsource(ts_mod)
assert sent[0]["model"] == "deepseek-chat" and sent[1]["model"] == "kimi-k2.6"
print("3 OK model name is per-call")

# 4) max_tokens hard cap
os.environ["V1RG0_MAX_TOKENS"] = "1000"
with mock.patch("requests.post", side_effect=fake_post):
    for want, asked in ((1000, 50000), (1000, None), (300, 300), (1, 0)):
        suit.transmit("deepseek_chat", {"prompt": "x"} if asked is None else {"prompt": "x", "max_tokens": asked})
        assert sent[-1]["max_tokens"] == want, (asked, sent[-1]["max_tokens"])
os.environ.pop("V1RG0_MAX_TOKENS")
print("4 OK max_tokens clamped to V1RG0_MAX_TOKENS")

# 5) judge_model checked at load, fallback deepseek with warning
def cfg_with(judge):
    p = os.path.join(WORK, "prov.json")
    json.dump({"enabled_providers": ["deepseek"], "judge_model": judge,
               "providers": {"deepseek": {"model_ids": ["deepseek_chat"]}, "kimi": {"model_ids": ["kimi_k2_6"]}}}, open(p, "w"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c = oc.load_provider_config(p)
    return c, buf.getvalue()
for bad in ("kimi_k2_6", "nonexistent"):
    c, out = cfg_with(bad)
    assert c["judge_model"] == "deepseek_chat" and "WARNING" in out and bad in out, (bad, out)
c, out = cfg_with("deepseek_chat"); assert c["judge_model"] == "deepseek_chat" and "WARNING" not in out
assert json.load(open(os.path.join(ROOT, "V1rG0_specific", "v1rg0_providers.json")))["enabled_providers"] == ["deepseek"]
print("5 OK judge_model fallback to deepseek_chat")

# 6) memory persistence + max_packets
os.environ["V1RG0_MAX_PACKETS"] = "5"
m = oc.MemoryStore()
for i in range(8):
    m.push_memory({"tier": "RETAIN", "composite": 0.1, "salience": {}, "pressure": 0.0, "n": i})
disk = json.load(open(os.path.join(os.environ["V1RG0_DATA_DIR"], "memory.json")))
assert [p["n"] for p in disk] == [3, 4, 5, 6, 7]
assert [p["n"] for p in m.store.pull_recent(50)] == [3, 4, 5, 6, 7]
m2 = oc.MemoryStore(); assert [p["n"] for p in m2.store.pull_recent(50)] == [3, 4, 5, 6, 7]
os.environ["V1RG0_MAX_PACKETS"] = "2"
m3 = oc.MemoryStore(); assert len(json.load(open(m3.file.path))) == 2
os.environ.pop("V1RG0_MAX_PACKETS")
print("6 OK memory.json persisted, oldest dropped at cap")

# 7) clock injection
p = {"proposal_id": "t", "created_at": 1000.0, "ttl_seconds": 60}
assert RealPB.is_expired(p, now=1030.0) is False and RealPB.is_expired(p, now=1061.0) is True
assert RealPB.is_expired(p, clock=lambda: 1100.0) is True and RealPB.is_expired(p) is True
print("7 OK is_expired accepts now=/clock=")

# 8) round2_chain never overwrites earlier runs
import round2_chain
os.environ["DEEPSEEK_API_KEY"] = "test-ds"; os.environ["MOONSHOT_API_KEY"] = "test-km"; os.environ["V1RG0_MASTER_PW"] = "test-only"
PROV = os.path.join(WORK, "v1rg0_providers.json")
shutil.copy(os.path.join(ROOT, "V1rG0_specific", "v1rg0_providers.json"), PROV)
os.environ["V1RG0_PROVIDERS_FILE"] = PROV; oc.PROVIDERS_FILE = PROV
cwd = os.getcwd(); os.chdir(WORK)
for n, t in (("pre.txt", "P"), ("code.md", "CODE")):
    open(os.path.join(WORK, n), "w").write(t)
out = os.path.join(WORK, "out")
def go():
    with mock.patch("requests.post", side_effect=fake_post), contextlib.redirect_stdout(io.StringIO()):
        return round2_chain.main(["--mode", "review", "--i-approve-this-run", "--preface-file", os.path.join(WORK, "pre.txt"),
                                  "--kimi-code-file", os.path.join(WORK, "code.md"), "--out-dir", out])
assert go() == 0
first = {f: open(f).read() for f in glob.glob(os.path.join(out, "*", "*"))}
assert go() == 0
runs = sorted(glob.glob(os.path.join(out, "review_*")))
assert len(runs) == 2, runs
for r in runs:
    assert len(glob.glob(os.path.join(r, "summary_review_*.json"))) == 1
    assert os.path.exists(os.path.join(r, "review1_kimi.md")) and os.path.exists(os.path.join(r, "review2_deepseek.md"))
assert all(open(f).read() == c for f, c in first.items())           # first run untouched
try:
    round2_chain._write_new(next(iter(first)), "X"); raise AssertionError("overwrote")
except FileExistsError:
    pass
os.chdir(cwd)
print("8 OK each run in its own folder, summary_<mode>_<UTC>.json, no overwrite")

shutil.rmtree(WORK, ignore_errors=True)
print("PHASE9 TEST OK: items 1-8")
