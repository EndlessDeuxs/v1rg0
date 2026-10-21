"""Round 2 chain: DeepSeek -> Kimi -> DeepSeek (see ROUND2_PLAN.md).

Exactly 3 live calls, in order, through the orchestrator's normal path (allowlist, one-call lock,
injection filter, persistence). Kimi is switched on in v1rg0_providers.json only immediately before
call 2 and the original file is restored immediately after it (try/finally, also on errors).
Stops on the first HELD / REJECTED / empty reply. No retries. Outputs go to _prot_replies/round2/.

Run (only after you approve these 3 live calls):
  cd /workspace/V1rG0 && set -a && . ./.env && set +a && \\
  V1RG0_MAX_TOKENS=8000 PYTHONPATH=V1rG0_specific:unvalidated python3 tools/round2_chain.py \\
      --i-approve-this-run --preface-file PREFACE.txt --questions-file PROT_QUESTIONS.md \\
      --round1-summary-file ROUND1_SUMMARY.md
"""
import argparse
import re
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "V1rG0_specific"), os.path.join(ROOT, "unvalidated")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

KIMI_PROVIDER = "kimi"          # provider name in v1rg0_providers.json (the model id is kimi_k2_6)
DEEPSEEK_MODEL_ID = "deepseek_chat"
KIMI_MODEL_ID = "kimi_k2_6"

CALL1_ASK = ("You are about to consult a second system, Kimi, for independent input. Write the message you "
             "want sent to Kimi: introduce V1rG0 and yourself briefly, and pose the same five questions from "
             "round 1 (listed below). Do NOT include your own answers, so Kimi's input stays independent.")
CALL3_ASK = ("Review Kimi's input. For each point: APPROVE, or ISSUE with a reason. Then write a joint plan for "
             "the next step (3-6 ordered items in the 12-field proposal format, mode PASS), marking which items "
             "both systems agree on and which are disputed.")


class ChainStop(Exception):
    pass


def _read(path, label):
    if not path or not os.path.isfile(path):
        raise ChainStop(f"missing {label}: {path!r}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


class KimiWindow:
    """Enable Kimi in the providers file for the duration of the with-block, then restore the exact original bytes."""
    def __init__(self, oc, path):
        self.oc, self.path, self.original = oc, path, None

    def __enter__(self):
        with open(self.path, "rb") as f:
            self.original = f.read()
        crlf = b"\r\n" in self.original
        cfg = json.loads(self.original.decode("utf-8"))
        if KIMI_PROVIDER not in cfg.get("providers", {}):
            raise ChainStop("kimi is not listed in the providers file")
        if KIMI_PROVIDER not in cfg["enabled_providers"]:
            cfg["enabled_providers"] = list(cfg["enabled_providers"]) + [KIMI_PROVIDER]
        text = json.dumps(cfg, indent=2) + "\n"
        with open(self.path, "wb") as f:
            f.write((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        print(f"[ROUND2] Kimi ENABLED for call 2 ({self.path})")
        return self.oc.load_provider_config(self.path)

    def __exit__(self, *exc):
        with open(self.path, "wb") as f:
            f.write(self.original)
        with open(self.path, "rb") as f:
            restored = f.read() == self.original
        print(f"[ROUND2] Kimi window closed; providers file restored: {restored}")
        if not restored:
            raise ChainStop("providers file was NOT restored; fix it by hand before anything else")
        return False


def run_chain(args) -> dict:
    import v1rg0_orchestrator_core as oc
    from v1rg0_keychain import V1rg0Keychain
    from v1rg0_extra_providers import V1rg0ExtendedTransmissionSuit
    from v1rg0_validation_gate import V1rg0ValidationGate
    from v1rg0_prompt_injector import V1rg0PromptInjector

    print(f"[ROUND2] packs: deepseek={args.context_file} kimi={args.kimi_context_file} code={args.kimi_code_file}")
    os.environ["KIMI_THINKING"] = "disabled"                     # per plan; Moonshot default would be enabled
    preface = _read(args.preface_file, "preface")
    context = _read(args.context_file, "context pack")
    kimi_context = _read(args.kimi_context_file, "Kimi context pack")
    code_excerpt = _read(args.kimi_code_file, "redacted code excerpt") if args.kimi_code_file else ""
    if args.mode == "chain" and not (args.questions_file and args.round1_summary_file):
        raise ChainStop("chain mode needs --questions-file and --round1-summary-file")
    questions = _read(args.questions_file, "questions") if args.mode == "chain" else ""
    round1 = _read(args.round1_summary_file, "round 1 summary") if args.mode == "chain" else ""
    master_pw = oc.get_master_password()
    if not master_pw:
        raise ChainStop("V1RG0_MASTER_PW is not set")

    approval = f"user (via --i-approve-this-run, {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})"
    # Phase 9 (8): every run gets its own subfolder and timestamped summary; nothing is ever overwritten.
    run_dir, stamp = _new_run_dir(args.out_dir, args.mode)
    summary_path = os.path.join(run_dir, f"summary_{args.mode}_{stamp}.json")
    print(f"[ROUND2] run folder: {run_dir}")
    providers_path = oc.PROVIDERS_FILE
    base_cfg = oc.load_provider_config(providers_path)
    if KIMI_PROVIDER in base_cfg["enabled"]:
        print("[ROUND2] note: Kimi was already enabled before the run; the file will still be restored as-is")

    suit = V1rg0ExtendedTransmissionSuit(V1rg0Keychain(master_password=master_pw))
    gate = V1rg0ValidationGate()
    memory = oc.MemoryStore()
    proposals = oc.ProposalBuilder()
    dlq = oc.DLQHandler(memory)
    summary = {"context_file": args.context_file,
               "kimi_context_file": None if args.mode == "review" else args.kimi_context_file,
               "kimi_code_file": args.kimi_code_file, "owner_approval": approval, "calls": [], "completed": False, "stopped_reason": None}

    def call(n, model_id, prompt, cfg, outfile):
        inj = V1rg0PromptInjector()
        inj.receive_task(json.dumps({"prompt": prompt, "model_id": model_id,
                                     "proposal": {"owner_approval": approval, "stage": "plan",
                                                  "title": f"Round 2 call {n}"}}))
        task = inj.get_task()
        before = len(proposals.proposals)
        out = oc.process_task(task, suit, gate, memory, proposals, dlq, cfg)
        new = [p for p in proposals.proposals[before:]
               if str((p.get("record") or {}).get("id", "")).startswith(str(task["task_id"]))]
        status = new[-1]["status"] if new else ("NO_RESPONSE" if out is None else "UNKNOWN")
        if out is not None and not str(out).strip():
            status = "EMPTY"
        entry = {"call": n, "model_id": model_id, "task_id": task["task_id"], "status": status,
                 "output_file": None, "reasons": (new[-1].get("rejection_reasons") or new[-1].get("hold_reasons"))
                 if new else None}
        summary["calls"].append(entry)
        if out is None or not str(out).strip() or status in ("HELD", "REJECTED", "NO_RESPONSE", "UNKNOWN", "EMPTY"):
            raise ChainStop(f"call {n} ({model_id}) ended with status {status}; stopping (no retries)")
        path = os.path.join(run_dir, outfile)
        _write_new(path, out)
        entry["output_file"] = path
        print(f"[ROUND2] call {n} {model_id}: {status}, saved {path}")
        return out

    if args.mode == "review":
        if not code_excerpt:
            raise ChainStop("--mode review needs --kimi-code-file")
        try:
            pa = (f"{preface}\n\n=== CODE EXCERPT (read-only, redacted) ===\n{code_excerpt}\n"
                  f"=== END OF EXCERPT ===\n\n{REVIEW_KIMI_ASK}")
            with KimiWindow(oc, providers_path) as kimi_cfg:
                ra = call(1, KIMI_MODEL_ID, pa, kimi_cfg, "review1_kimi.md")
            cfg_after = oc.load_provider_config(providers_path)
            if KIMI_PROVIDER in cfg_after["enabled"] and KIMI_PROVIDER not in base_cfg["enabled"]:
                raise ChainStop("Kimi still enabled after call 1; stopping")
            pb = (f"{preface}\n\n{context}\n\n=== CODE EXCERPT (read-only, redacted) ===\n{code_excerpt}\n"
                  f"=== END OF EXCERPT ===\n\nKimi's review in full:\n{ra}\n\n{REVIEW_DEEPSEEK_ASK}")
            call(2, DEEPSEEK_MODEL_ID, pb, cfg_after, "review2_deepseek.md")
            summary["completed"] = True
        except ChainStop as e:
            summary["stopped_reason"] = str(e)
            print(f"[ROUND2] STOP: {e}")
        finally:
            _write_new(summary_path, json.dumps(summary, indent=1))
        return summary

    try:
        p1 = f"{preface}\n\n{context}\n\nSummary of round 1 advice:\n{round1}\n\n{CALL1_ASK}\n\n{questions}"
        r1 = call(1, DEEPSEEK_MODEL_ID, p1, base_cfg, "call1_deepseek_request.md")

        p2 = (f"{preface}\n\n{kimi_context}\n\n"
              "=== THE QUESTION FOR YOU (sent by DeepSeek, already final; this is not a draft) ===\n"
              f"{re.sub(r'P_ROT_OGRAPH_R', 'the V1rG0 planning model', r1)}\n=== END OF QUESTION ===\n\n"
              + (f"=== REDACTED CODE EXCERPT (read-only; keys and personal data removed) ===\n"
                 f"{code_excerpt}\n=== END OF EXCERPT ===\n\n" if code_excerpt else "")
              + "Please answer the question above directly, using the excerpt where it helps. "
              "Where the excerpt is not enough, say exactly which file or function you need next.")
        with KimiWindow(oc, providers_path) as kimi_cfg:
            r2 = call(2, KIMI_MODEL_ID, p2, kimi_cfg, "call2_kimi.md")
        cfg_after = oc.load_provider_config(providers_path)
        if KIMI_PROVIDER in cfg_after["enabled"] and KIMI_PROVIDER not in base_cfg["enabled"]:
            raise ChainStop("Kimi still enabled after call 2; stopping")

        p3 = (f"{preface}\n\n{context}\n\nSummary of round 1 advice:\n{round1}\n\n"
              f"Kimi's answer in full:\n{r2}\n\n{CALL3_ASK}")
        call(3, DEEPSEEK_MODEL_ID, p3, cfg_after, "call3_deepseek_review.md")
        summary["completed"] = True
    except ChainStop as e:
        summary["stopped_reason"] = str(e)
        print(f"[ROUND2] STOP: {e}")
    finally:
        _write_new(summary_path, json.dumps(summary, indent=1))
    return summary


REVIEW_KIMI_ASK = ("You asked to see the real code before answering. Above is a read-only, redacted excerpt. "
    "Please give your general opinion of it: what looks sound, what looks risky or wrong, and what you would "
    "change first, citing file and function. This is one call; if you stop early, say where.")
REVIEW_DEEPSEEK_ASK = ("Please give your own general opinion of the same code, then go through Kimi's review: "
    "what you agree with, what you take issue with and why, and a short joint list of first changes. "
    "Opinion only; nothing will be applied from this call. If you stop early, say where.")

def _new_run_dir(out_dir, mode):
    """Create out_dir/<mode>_<UTC stamp>[_N]/ exclusively; returns (path, stamp)."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for n in range(1000):
        name = f"{mode}_{stamp}" + (f"_{n}" if n else "")
        path = os.path.join(out_dir, name)
        try:
            os.mkdir(path)
            return path, stamp + (f"_{n}" if n else "")
        except FileExistsError:
            continue
    raise ChainStop("could not create a fresh run folder")


def _write_new(path, text):
    """Write a file that must not exist yet (mode 'x'): never overwrites an earlier run."""
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Round 2: DeepSeek -> Kimi -> DeepSeek (3 live calls, no retries)")
    ap.add_argument("--i-approve-this-run", action="store_true", dest="approved",
                    help="Required. Confirms you (the person running it) approve these 3 live calls.")
    ap.add_argument("--preface-file", required=True, help="the collective's preface text")
    ap.add_argument("--questions-file", default=None, help="Q1-Q5 text (PROT_QUESTIONS.md)")
    ap.add_argument("--mode", choices=["chain", "review"], default="chain",
                    help="chain: DeepSeek>Kimi>DeepSeek (3 calls); review: Kimi>DeepSeek code review (2 calls)")
    ap.add_argument("--round1-summary-file", default=None, help="short summary of round 1 advice")
    ap.add_argument("--context-file", default=os.path.join(ROOT, "_map", "CONTEXT_PACK.md"))
    ap.add_argument("--kimi-context-file", default=os.path.join(ROOT, "_map", "CONTEXT_PACK_KIMI.md"))
    ap.add_argument("--kimi-code-file", default=None, help="redacted read-only code excerpt for Kimi")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "_prot_replies", "round2"))
    args = ap.parse_args(argv)
    if not args.approved:
        print("[ROUND2] refused: --i-approve-this-run is required (3 paid live calls).")
        return 2
    try:
        summary = run_chain(args)
    except ChainStop as e:
        print(f"[ROUND2] refused before any call: {e}")
        return 2
    print("[ROUND2] summary:")
    for c in summary["calls"]:
        print(f"  call {c['call']} {c['model_id']}: {c['status']} -> {c['output_file']}")
    print(f"  completed: {summary['completed']}  stopped: {summary['stopped_reason']}")
    return 0 if summary["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
