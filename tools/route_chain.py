"""Route chain (Phase 10): each call picks the next system + suit, with hard stops.

Start: DeepSeek wearing Plann.r. Every call gets the suit menu and the allowed system list and must end with
exactly one line:  NEXT: system=<id> suit=<id> reason=<text>   or   NEXT: STOP
V1rG0 checks that line and refuses (and stops) on: disabled/not-allowed system, unknown suit, malformed or
missing line, the same system+suit twice in a row, A-B-A-B ping-pong, or a repeated question (reason text).
Caps: --max-calls (default 4, absolute max 6) and an optional --max-est-tokens estimate (chars/4).
On any stop, one final DeepSeek + Plann.r review call summarises the run, if it still fits inside the absolute
max of 6 calls and the token cap was not the reason for stopping. Nothing is ever applied.
A non-deepseek system is switched on in v1rg0_providers.json only for its own call (exact bytes restored after).

Run only after you have read the task and approve this run:
  cd /workspace/V1rG0 && set -a && . ./.env && set +a && \\
  V1RG0_MAX_TOKENS=8000 python3 tools/route_chain.py --i-approve-this-run --task-file TASK.md
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "V1rG0_specific"), os.path.join(ROOT, "unvalidated")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ABSOLUTE_MAX_CALLS = 6
LONG_RUN_MAX_ROUTED = 30       # Phase 22 (was 20, Phase 13): --allow-long-run ceiling for routed calls (extends included); review (+1) and image are on top -> 31 text calls
DEFAULT_MAX_CALLS = 4
START_SYSTEM, START_SUIT = "deepseek", "plann_r"
NEXT_RE = re.compile(r"^NEXT:\s*(?:(STOP)|EXTEND\s+reason=(.+)|system=(\S+)\s+suit=(\S+)\s+reason=(.+))\s*$")


class RouteStop(Exception):
    pass


def _read(path, label):
    if not path or not os.path.isfile(path):
        raise RouteStop(f"missing {label}: {path!r}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


class ProviderWindow:
    """Enable one provider in the providers file for the with-block, then restore the exact original bytes.
    Generalised KimiWindow. Only providers in `allowed` may be switched on."""
    def __init__(self, oc, path, provider, allowed):
        self.oc, self.path, self.provider, self.allowed, self.original = oc, path, provider, set(allowed), None

    def __enter__(self):
        if self.provider not in self.allowed:
            raise RouteStop(f"system '{self.provider}' is not in --allow-systems")
        with open(self.path, "rb") as f:
            self.original = f.read()
        cfg = json.loads(self.original.decode("utf-8"))
        if self.provider not in cfg.get("providers", {}):
            raise RouteStop(f"system '{self.provider}' is not listed in the providers file")
        if self.provider not in cfg["enabled_providers"]:
            cfg["enabled_providers"] = list(cfg["enabled_providers"]) + [self.provider]
            text = json.dumps(cfg, indent=2) + "\n"
            if b"\r\n" in self.original:
                text = text.replace("\n", "\r\n")
            with open(self.path, "wb") as f:
                f.write(text.encode("utf-8"))
            print(f"[ROUTE] {self.provider} ENABLED for one call")
        return self.oc.load_provider_config(self.path)

    def __exit__(self, *exc):
        if self.original is None:
            return False
        with open(self.path, "wb") as f:
            f.write(self.original)
        with open(self.path, "rb") as f:
            ok = f.read() == self.original
        print(f"[ROUTE] {self.provider} window closed; providers file restored: {ok}")
        if not ok:
            raise RouteStop("providers file was NOT restored; fix it by hand before anything else")
        return False


def parse_next(reply):
    """Return ('STOP',), ('EXTEND', reason) or ('GO', system, suit, reason), or raise RouteStop if missing/malformed."""
    # tolerate markdown dressing on the routing line, e.g. "**NEXT**: ..." or "- `NEXT: ...`"
    # (only * and ` are stripped; underscores stay, since suit ids use them)
    lines = [re.sub(r"^[#>\-\s]+", "", l.replace("*", "").replace("`", "")).strip()
             for l in str(reply or "").strip().splitlines()]
    lines = [l for l in lines if l]
    nexts = [l for l in lines if l.upper().startswith("NEXT:")]
    if not lines or not nexts:
        raise RouteStop("refused: reply has no NEXT line")
    if len(nexts) != 1 or lines[-1] != nexts[0]:
        raise RouteStop("refused: NEXT line must appear exactly once, as the last line")
    m = NEXT_RE.match(nexts[0])
    if not m:
        raise RouteStop(f"refused: malformed NEXT line: {nexts[0][:120]!r}")
    if m.group(1):
        return ("STOP",)
    if m.group(2):
        return ("EXTEND", m.group(2).strip())
    return ("GO", m.group(3), m.group(4), m.group(5).strip())


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def check_route(nxt, path, allowed, providers, suits, reasons):
    """Refusal rules. path = list of (system, suit) already called; reasons = earlier reason texts."""
    _, system, suit, reason = nxt
    if system not in allowed or system not in providers:
        raise RouteStop(f"refused: system '{system}' is not enabled for routing (allowed: {sorted(allowed)})")
    if suit not in suits:
        raise RouteStop(f"refused: unknown suit '{suit}'")
    pair = (system, suit)
    if path and path[-1] == pair:
        raise RouteStop(f"refused: same system+suit twice in a row {pair}")
    if len(path) >= 3 and pair == path[-2] and path[-1] == path[-3]:
        raise RouteStop(f"refused: A-B-A-B ping-pong between {path[-1]} and {pair}")
    if _norm(reason) in {_norm(r) for r in reasons}:
        raise RouteStop("refused: repeated question (same reason as an earlier step)")


def _new_run_dir(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for n in range(1000):
        tag = stamp + (f"_{n}" if n else "")
        path = os.path.join(out_dir, f"route_{tag}")
        try:
            os.mkdir(path)
            return path, tag
        except FileExistsError:
            continue
    raise RouteStop("could not create a fresh run folder")


def _write_new(path, text):
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)


def _file_info(path):
    """Path + sha256 of an input file, recorded in the run log (Phase 12b)."""
    if not path:
        return None
    with open(path, "rb") as f:
        return {"path": os.path.abspath(path), "sha256": hashlib.sha256(f.read()).hexdigest()}


def cost_from_usage(usage_by_system, prices):
    """Phase 16: estimated USD per system from the providers' own token counts and a human-filled price table.
    Output tokens = total - prompt (so billed reasoning tokens count). Systems without both prices are listed, not guessed."""
    by_sys, missing = {}, []
    for system, u in sorted((usage_by_system or {}).items()):
        p = (prices or {}).get(system) or {}
        pin, pout = p.get("input_per_million"), p.get("output_per_million")
        if not isinstance(pin, (int, float)) or not isinstance(pout, (int, float)):
            missing.append(system); continue
        prompt = u.get("prompt_tokens", 0)
        output = max(u.get("total_tokens", prompt + u.get("completion_tokens", 0)) - prompt, 0)
        by_sys[system] = round(prompt / 1e6 * pin + output / 1e6 * pout, 6)
    return {"by_system": by_sys, "total": round(sum(by_sys.values()), 6), "missing_prices": missing}


def write_readout(path, task_name, entries, review_text, summary):
    """Phase 16: one plain markdown file with every step reply in order plus the final review, for the user to read
    or paste into any other AI tool. Stays in the private run folder, like the other replies."""
    lines = [f"# V1rG0 run readout", "", f"Task file: {task_name}", f"Calls: {summary.get('calls_made')}",
             f"Stopped: {summary.get('stopped_reason')}", ""]
    cost = summary.get("est_cost_usd")
    if cost and (cost["by_system"] or cost["missing_prices"]):
        lines.append(f"Estimated cost: ${cost['total']:.4f}" + (f" (no price set for: {', '.join(cost['missing_prices'])})"
                                                                 if cost["missing_prices"] else ""))
        lines.append("")
    for head, text in entries:
        lines += [f"## {head}", "", str(text).strip(), ""]
    if review_text:
        lines += ["## Final review (DeepSeek)", "", str(review_text).strip(), ""]
    img = summary.get("image")
    if img:
        if img.get("made"):
            lines += ["## Image (AI-generated)", "", f"Model: {img.get('model')}  Date: {time.strftime('%Y-%m-%d', time.gmtime())}",
                      f"File: {os.path.basename(img['file'])}" + (f"  Marked copy: {os.path.basename(img['marked_file'])}"
                                                                    if img.get("marked_file") else ""),
                      f"Image cost: ${summary.get('image_cost_usd', 0):.2f}"]
            if img.get("text_file"):
                lines += [f"With card text (added by code, not the image model): {os.path.basename(img['text_file'])}"
                          + (f"  Marked: {os.path.basename(img['text_marked_file'])}" if img.get("text_marked_file") else "")]
            lines += [""]
        else:
            lines += ["## Image", "", f"No image made: {img.get('refused') or img.get('error')}", ""]
    _write_new(path, "\n".join(lines))


_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9._:/@+-]{1,80}$")


def _returned_model(data):
    """Phase 18: the model name the provider says served the call ("model", or Gemini's "modelVersion").
    Only a short plain name is kept; anything else is dropped."""
    if not isinstance(data, dict):
        return None
    for key in ("model", "modelVersion"):
        v = data.get(key)
        if isinstance(v, str) and _MODEL_NAME_RE.match(v):
            return v
    return None


def _numeric_usage(u):
    """Keep only numeric token counts (flattening one level, e.g. completion_tokens_details.reasoning_tokens)."""
    if not isinstance(u, dict):
        return None
    out = {}
    for k, v in u.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, (int, float)) and not isinstance(v2, bool):
                    out[f"{k}.{k2}"] = v2
    return out or None


def _usage_aliases(u):
    """Phase 21: Anthropic reports input_tokens/output_tokens; add the OpenAI-style names the totals and cost use."""
    if not u or "prompt_tokens" in u or "input_tokens" not in u:
        return u
    u = dict(u)
    u["prompt_tokens"] = u["input_tokens"]
    u["completion_tokens"] = u.get("output_tokens", 0)
    u["total_tokens"] = u["prompt_tokens"] + u["completion_tokens"]
    return u


def _est_tokens(*texts):
    return sum(len(t or "") for t in texts) // 4 + 1


INSTRUCTIONS = ("End your reply with exactly one final line, either\n"
                "NEXT: system=<system id> suit=<suit id> reason=<one-line question or task for that step>\n"
                "or\nNEXT: STOP\nChoose STOP when the task is answered well enough or more calls would only repeat. "
                "Do not pick the same system and suit you are now, and do not repeat an earlier question. "
                "Nothing you say is applied automatically.")
REVIEW_ASK = ("The routed run has stopped. Review the steps below: summarise what was learned, what is still open, "
              "and recommend whether a human should start another run. Opinion only. End with: NEXT: STOP")


def run_route(args) -> dict:
    import v1rg0_orchestrator_core as oc
    from v1rg0_keychain import V1rg0Keychain
    from v1rg0_extra_providers import V1rg0ExtendedTransmissionSuit
    from v1rg0_validation_gate import V1rg0ValidationGate
    from v1rg0_prompt_injector import V1rg0PromptInjector
    from v1rg0_transmission_suit import load_suits

    max_calls = args.max_calls
    long_run = bool(getattr(args, "allow_long_run", False))
    ceiling = LONG_RUN_MAX_ROUTED if long_run else ABSOLUTE_MAX_CALLS
    if not 1 <= max_calls <= ceiling:
        raise RouteStop(f"--max-calls must be 1..{ceiling}" + ("" if long_run else " (more needs --allow-long-run)"))
    visit_limit = getattr(args, "visits_per_system", None)
    if args.each_system_once:
        if visit_limit not in (None, 1):
            raise RouteStop("--each-system-once conflicts with --visits-per-system > 1")
        visit_limit = 1
    if visit_limit is not None and not 1 <= visit_limit <= LONG_RUN_MAX_ROUTED:
        raise RouteStop(f"--visits-per-system must be 1..{LONG_RUN_MAX_ROUTED}")
    extend_on = bool(getattr(args, "extend_thinking", False))
    allowed = [s.strip() for s in args.allow_systems.split(",") if s.strip()]
    if START_SYSTEM not in allowed:
        raise RouteStop("deepseek must be in --allow-systems (it starts and reviews)")
    task_text = _read(args.task_file, "task file")
    preface = _read(args.preface_file, "preface") if args.preface_file else ""
    context = _read(args.context_file, "routed context pack")
    print(f"[ROUTE] context pack: {args.context_file}")
    preface = f"{preface}\n\n{context}".strip()
    master_pw = oc.get_master_password()
    if not master_pw:
        raise RouteStop("V1RG0_MASTER_PW is not set")

    providers_path = oc.PROVIDERS_FILE
    with open(providers_path, "r", encoding="utf-8") as f:
        prov_file = json.load(f)
    providers = {name: p["model_ids"][0] for name, p in prov_file.get("providers", {}).items() if p.get("model_ids")}
    unknown = [s for s in allowed if s not in providers]
    if unknown:
        raise RouteStop(f"--allow-systems lists unknown system(s) {unknown}")
    from v1rg0_transmission_suit import UserSuitsError
    try:
        suits_data = load_suits()
    except UserSuitsError as e:
        raise RouteStop(f"user suits refused: {e}")
    suits = suits_data["suits"]
    start_suit = suits_data.get("start_suit") or START_SUIT      # Phase 17: the file's start_suit is read
    if start_suit not in suits:
        raise RouteStop(f"start suit {start_suit!r} is not in the suit list")
    base_cfg = oc.load_provider_config(providers_path)

    approval = f"user (via --i-approve-this-run, {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})"
    run_dir, tag = _new_run_dir(args.out_dir)
    summary_path = os.path.join(run_dir, f"summary_route_{tag}.json")
    print(f"[ROUTE] run folder: {run_dir}")
    suit_tx = V1rg0ExtendedTransmissionSuit(V1rg0Keychain(master_password=master_pw))
    # Phase 14: record each provider's own reported token usage (numbers only, never content)
    _last_usage = {}
    _orig_transmit = suit_tx.transmit
    def _transmit_with_usage(model_id, concept):
        r = _orig_transmit(model_id, concept)
        data = r.get("data") if isinstance(r, dict) else None
        _last_usage["usage"] = _usage_aliases(_numeric_usage((data or {}).get("usage"))) if isinstance(data, dict) else None
        _last_usage["model"] = _returned_model(data)                   # Phase 18: name only, never content
        return r
    suit_tx.transmit = _transmit_with_usage
    gate = V1rg0ValidationGate()
    memory, proposals = oc.MemoryStore(), oc.ProposalBuilder()
    dlq = oc.DLQHandler(memory)
    menu = "\n".join(f"- {sid}: {s['purpose']}" for sid, s in suits.items())
    summary = {"suits_mode": "only_mine" if suits_data.get("use_only_my_suits") else "built_in_plus_mine",
               "start_suit": start_suit, "owner_approval": approval, "max_calls": max_calls, "absolute_max": ABSOLUTE_MAX_CALLS,
               "max_est_tokens": args.max_est_tokens, "allow_systems": allowed, "steps": [],
               "stopped_reason": None, "review": None, "est_tokens": 0, "calls_made": 0,
               "usage": [], "usage_by_system": {}, "models_seen": {},
               "inputs": {"task_file": _file_info(args.task_file), "context_file": _file_info(args.context_file),
                          "preface_file": _file_info(args.preface_file),
                          "review_question_file": _file_info(args.review_question_file)},
               "long_run": long_run, "ceiling_routed": ceiling, "visits_per_system": visit_limit,
               "extend_thinking": extend_on}

    def call(n, system, suit, prompt, label):
        _last_usage.clear()
        try:
            return _call(n, system, suit, prompt, label)
        finally:
            u = _last_usage.get("usage")
            rm = _last_usage.get("model")
            summary["usage"].append({"call": summary["calls_made"], "label": label, "system": system, "usage": u,
                                     "returned_model": rm})
            if rm:
                seen = summary["models_seen"].setdefault(system, [])
                if rm not in seen:
                    seen.append(rm)
            if u:
                tot = summary["usage_by_system"].setdefault(system, {})
                for k, v in u.items():
                    if k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        tot[k] = tot.get(k, 0) + v

    def _call(n, system, suit, prompt, label):
        model_id = providers[system]
        inj = V1rg0PromptInjector()
        inj.receive_task(json.dumps({"prompt": prompt, "model_id": model_id, "suit_id": suit,
                                     "proposal": {"owner_approval": approval, "stage": "plan",
                                                  "title": f"Route call {n} {system}/{suit}"}}))
        task = inj.get_task()
        before = len(proposals.proposals)
        summary["calls_made"] += 1
        if system == START_SYSTEM and START_SYSTEM in base_cfg["enabled"]:
            out = oc.process_task(task, suit_tx, gate, memory, proposals, dlq, base_cfg)
        else:
            with ProviderWindow(oc, providers_path, system, allowed) as cfg:
                out = oc.process_task(task, suit_tx, gate, memory, proposals, dlq, cfg)
        new = [p for p in proposals.proposals[before:]
               if str((p.get("record") or {}).get("id", "")).startswith(str(task["task_id"]))]
        status = new[-1]["status"] if new else ("NO_RESPONSE" if out is None else "UNKNOWN")
        if out is not None and not str(out).strip():
            status = "EMPTY"
        summary["est_tokens"] += _est_tokens(prompt, out)
        path = None
        if status == "PASS":
            path = os.path.join(run_dir, f"{label}_{system}_{suit}.md")
            _write_new(path, out)
        return out, status, path

    first_hop = [x.strip() for x in (args.first_hop_systems or '').split(',') if x.strip()]
    review_q = _read(args.review_question_file, "review question") if args.review_question_file else ""
    replace_ask = bool(getattr(args, "review_replaces_ask", False))     # Phase 15
    image_on = bool(getattr(args, "image_from_review", False))         # Phase 19
    if image_on and not review_q:
        raise RouteStop("--image-from-review needs --review-question-file")
    if image_on:
        replace_ask = True
    if replace_ask and not review_q:
        raise RouteStop("--review-replaces-ask needs --review-question-file")
    summary["review_replaces_ask"] = replace_ask
    image_provider, image_ask = None, ""
    if image_on:
        import image_step
        try:
            iconf = image_step.load_image_providers()
        except (OSError, ValueError) as e:
            raise RouteStop(f"image providers file unreadable: {e}")
        image_provider = getattr(args, "image_provider", None) or iconf.get("default")
        icfg = iconf.get("providers", {}).get(image_provider)
        if not icfg:
            raise RouteStop(f"unknown image provider {image_provider!r}")
        if not os.environ.get(icfg.get("env_key", "")):
            raise RouteStop(f"{icfg.get('env_key')} is not set (needed for the image)")
        image_ask = image_step.IMAGE_ASK.format(max_chars=image_step.desc_limit(icfg))
    card_text = None
    if getattr(args, "image_text_file", None):                         # Phase 20
        if not image_on:
            raise RouteStop("--image-text-file needs --image-from-review")
        try:
            card_text = image_step.load_card_text(args.image_text_file)
            image_step._font_path()
        except (OSError, image_step.ImageStepError) as e:
            raise RouteStop(f"card text: {e}")
        image_ask += "\n" + image_step.TEXT_NOTE
    summary["card_text"] = card_text
    summary["card_text_file_sha256"] = (hashlib.sha256(open(args.image_text_file, "rb").read()).hexdigest()
                                        if card_text else None)
    summary["image_from_review"] = image_on
    visits = {x: 0 for x in allowed}
    extended = set()                             # systems that already used their one extended-thinking call
    def visits_left(x):
        return visit_limit is None or visits.get(x, 0) < visit_limit
    def handoff_pool(first):
        return first_hop if (first and first_hop) else allowed
    def can_route(first, current):
        pool = handoff_pool(first)
        if visit_limit is None:
            return list(pool)
        return [x for x in pool if x != current and visits_left(x)]
    def token_cap():
        if args.max_est_tokens and summary["est_tokens"] >= args.max_est_tokens:
            raise RouteStop(f"cap: estimated tokens {summary['est_tokens']} >= --max-est-tokens {args.max_est_tokens}")
    path, reasons = [], []                       # path = normal visits only (extended calls are not visits)
    system, suit, reason, is_ext = START_SYSTEM, start_suit, f"start (fixed: DeepSeek + {start_suit})", False
    transcript = []
    readout, review_text = [], None
    routed = 0
    try:
        while True:
            if routed >= ceiling:
                raise RouteStop(f"cap: hard ceiling of {ceiling} routed calls reached")
            n = routed + 1
            step = {"step": n, "system": system, "suit": suit, "reason": reason}
            if extend_on:
                step["extended"] = is_ext
            summary["steps"].append(step)
            if not is_ext:
                visits[system] = visits.get(system, 0) + 1
            first = (len(path) + (0 if is_ext else 1)) == 1
            routes = can_route(first, system)
            if is_ext:
                ask = (f"=== YOUR STEP ===\nStep {n}: this is your ONE extended-thinking call, continuing your previous "
                       f"step as {suit}. Think further about: {reason}\n\n")
            elif extend_on or long_run:
                ask = (f"=== YOUR STEP ===\nYou are step {n} (visit {len(path) + 1} of at most {max_calls}; "
                       f"hard ceiling {ceiling} calls). Asked of you: {reason}\n\n")
            else:
                ask = f"=== YOUR STEP ===\nYou are step {n} of at most {max_calls}. Asked of you: {reason}\n\n"
            ext_note = ""
            if extend_on:
                ext_note = ("Extended thinking: you have ONE extra call to yourself this run. To use it, end with "
                            "NEXT: EXTEND reason=<what to think through further> (routing to yourself counts the same). "
                            "After it, the turn must go to a different system.\n\n"
                            if system not in extended and not is_ext else
                            "Your extended-thinking call is used: NEXT must name a different system, or STOP.\n\n")
            prompt = (f"{preface}\n\n=== TASK ===\n{task_text}\n\n"
                      + ("=== EARLIER STEPS ===\n" + "\n\n".join(transcript) + "\n\n" if transcript else "")
                      + ask
                      + f"Suit menu (id: purpose):\n{menu}\n\nSystems you may route to: {', '.join(routes) or 'none left: every system has been called, so end with NEXT: STOP'}\n\n"
                      + ext_note + f"{INSTRUCTIONS}").strip()
            out, status, saved = call(n, system, suit, prompt, f"step{n}" + ("_ext" if is_ext else ""))
            routed += 1
            step.update({"status": status, "output_file": saved})
            if is_ext:
                extended.add(system)
            else:
                path.append((system, suit))
            reasons.append(reason)
            if status != "PASS":
                raise RouteStop(f"step {n} ({system}/{suit}) ended with status {status}")
            if "IMAGE_DESCRIPTION" in str(out):        # Phase 19: routed steps never make images
                step["image_request_ignored"] = "routed step"
            transcript.append(f"[step {n}: {system} as {suit}{' (extended thinking)' if is_ext else ''}]\n{out}")
            readout.append((f"Step {n}: {system} as {suit}{' (extended thinking)' if is_ext else ''}", out))
            first = len(path) == 1
            try:
                nxt = parse_next(out)
                if nxt[0] == "STOP":
                    step["next"] = "STOP"; step["accepted"] = True
                    raise RouteStop("model chose NEXT: STOP")
                if nxt[0] == "EXTEND" and not extend_on:
                    raise RouteStop("refused: NEXT: EXTEND needs --extend-thinking")
                wants_ext = nxt[0] == "EXTEND" or nxt[1] == system
                if extend_on and wants_ext and system not in extended:
                    ext_reason = nxt[-1]
                    if _norm(ext_reason) in {_norm(r) for r in reasons}:
                        raise RouteStop("refused: repeated question (same reason as an earlier step)")
                    step["next"] = {"extend": True, "reason": ext_reason}; step["accepted"] = True
                    if nxt[0] == "GO":
                        step["next"]["self_pick"] = {"system": nxt[1], "suit": nxt[2]}
                    token_cap()
                    reason, is_ext = ext_reason, True    # same system, same suit
                    continue
                if nxt[0] == "EXTEND":                   # extend already used: treat as a pick of itself
                    nxt = ("GO", system, suit, nxt[1])
                if visit_limit is not None and nxt[1] in allowed and (nxt[1] == system or not visits_left(nxt[1])):
                    # reroute (no extra call): keep the chosen suit and reason, hand the turn to the first system
                    # in --allow-systems (or first-hop) order that has visits left and is not the current one
                    left = [x for x in handoff_pool(first) if x != system and visits_left(x)]
                    if not left:
                        what = "no uncalled systems are left" if visit_limit == 1 else "no systems with visits left"
                        raise RouteStop(f"refused: '{nxt[1]}' was already called and {what} (visit limit {visit_limit})")
                    step["rerouted_from"] = nxt[1]
                    print(f"[ROUTE] '{nxt[1]}' already called; rerouted to '{left[0]}' (suit {nxt[2]} kept)")
                    nxt = (nxt[0], left[0], nxt[2], nxt[3])
                elif extend_on and nxt[1] == system:
                    raise RouteStop(f"refused: '{system}' already used its extended-thinking call; the turn must go to a different system")
                check_route(nxt, path, allowed, providers, suits, reasons)
                if first and first_hop and nxt[1] not in first_hop:
                    raise RouteStop(f"refused: step 1 must route to one of {first_hop}, got '{nxt[1]}'")
            except RouteStop as e:
                if "accepted" not in step:
                    step["accepted"] = False; step["refused"] = str(e)
                raise
            step["next"] = {"system": nxt[1], "suit": nxt[2], "reason": nxt[3]}; step["accepted"] = True
            if len(path) >= max_calls:
                raise RouteStop(f"cap: --max-calls {max_calls} reached")
            token_cap()
            system, suit, reason, is_ext = nxt[1], nxt[2], nxt[3], False
    except RouteStop as e:
        summary["stopped_reason"] = str(e)
        print(f"[ROUTE] STOP: {e}")
    except Exception as e:                       # crash: log it, never review, re-raise (windows already restored)
        summary["stopped_reason"] = f"crashed: {type(e).__name__}: {e}"
        summary["review"] = {"skipped": "crash"}
        _write_new(summary_path, json.dumps(summary, indent=1))
        raise
    # final review call
    reason_txt = summary["stopped_reason"]
    summary.update({"routed_calls": routed, "extend_calls": len(extended), "extends_used": sorted(extended),
                    "visits": {k: v for k, v in visits.items() if v}})
    if "not restored" in reason_txt:
        summary["review"] = {"skipped": "providers file not restored"}
    elif not long_run and summary["calls_made"] >= ABSOLUTE_MAX_CALLS:
        summary["review"] = {"skipped": f"absolute max of {ABSOLUTE_MAX_CALLS} calls already used"}
    elif reason_txt.startswith("cap: estimated tokens"):
        summary["review"] = {"skipped": "token cap reached"}
    else:
        steps_txt = json.dumps(summary["steps"], indent=1)
        prompt = (f"{preface}\n\n=== TASK ===\n{task_text}\n\n=== STEPS LOG ===\n{steps_txt}\n\n"
                  f"=== STOP REASON ===\n{reason_txt}\n\n"
                  + ("=== REPLIES ===\n" + "\n\n".join(transcript) + "\n\n" if transcript else "")
                  + ((f"=== YOUR TASK ===\n{review_q}\n\n" + (f"{image_ask}\n\n" if image_ask else "")
                      + "End with: NEXT: STOP") if (review_q and replace_ask) else
                     ((f"=== REVIEW QUESTION ===\n{review_q}\n\n" if review_q else "") + REVIEW_ASK))).strip()
        try:
            out, status, saved = call(summary["calls_made"] + 1, START_SYSTEM, start_suit, prompt, "review")
            summary["review"] = {"status": status, "output_file": saved}
            if status == "PASS":
                review_text = out
        except RouteStop as e:
            summary["review"] = {"status": "STOPPED", "error": str(e)}
    # Phase 19: at most one image, only here, only from a passing review
    summary["image"] = None
    if image_on and review_text:
        import image_step
        summary["image"] = image_step.run_image_step(review_text, run_dir, tag, image_provider, images_made=0,
                                                   card_text=card_text)
    elif image_on:
        summary["image"] = {"made": False, "refused": "no passing review, so no image"}
    img = summary["image"] or {}
    summary["image_cost_usd"] = (img.get("price_per_image") or 0) if img.get("made") else 0
    # Phase 16: cost estimate + readout file
    prices_file = getattr(args, "prices_file", None) or os.path.join(ROOT, "V1rG0_specific", "v1rg0_prices.json")
    prices = {}
    if os.path.isfile(prices_file):
        with open(prices_file, "r", encoding="utf-8") as f:
            prices = json.load(f).get("prices", {})
    summary["inputs"]["prices_file"] = _file_info(prices_file) if os.path.isfile(prices_file) else None
    summary["est_cost_usd"] = cost_from_usage(summary.get("usage_by_system"), prices)
    readout_path = os.path.join(run_dir, f"readout_route_{tag}.md")
    write_readout(readout_path, os.path.basename(args.task_file), readout, review_text, summary)
    summary["readout_file"] = readout_path
    c = summary["est_cost_usd"]
    print(f"[ROUTE] estimated cost ${c['total']:.4f}" + (f" (no price set for {c['missing_prices']})" if c["missing_prices"] else ""))
    print(f"[ROUTE] readout: {readout_path}")
    _write_new(summary_path, json.dumps(summary, indent=1))
    summary["summary_file"] = summary_path
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Routed chain: each call picks the next system + suit (hard caps)")
    ap.add_argument("--i-approve-this-run", action="store_true", dest="approved")
    ap.add_argument("--task-file", required=True)
    ap.add_argument("--each-system-once", action="store_true", help="each allowed system may be called at most once (DeepSeek review excepted)")
    ap.add_argument("--visits-per-system", type=int, default=None,
                    help="each allowed system may get at most N normal visits (N=1 is --each-system-once); repeat picks are rerouted")
    ap.add_argument("--extend-thinking", action="store_true",
                    help="each system may make ONE extra call to itself per run (NEXT: EXTEND or a self-pick); then the turn moves on")
    ap.add_argument("--allow-long-run", action="store_true",
                    help=f"raise the routed-call ceiling from {ABSOLUTE_MAX_CALLS} to {LONG_RUN_MAX_ROUTED}; the DeepSeek review is always added on top")
    ap.add_argument("--prices-file", default=None, help="price table for the cost estimate (default V1rG0_specific/v1rg0_prices.json)")
    ap.add_argument("--image-from-review", action="store_true",
                    help="Phase 19: the final review describes ONE image and V1rG0 makes it (needs --review-question-file)")
    ap.add_argument("--image-text-file", default=None,
                    help="Phase 20: TOP:/BOTTOM: card text, added by code above and below the image (needs --image-from-review)")
    ap.add_argument("--image-provider", default=None, help="entry in V1rG0_specific/v1rg0_image_providers.json (default: its 'default')")
    ap.add_argument("--review-replaces-ask", action="store_true",
                    help="the review question file becomes the whole final instruction (e.g. 'write the article'), "
                         "instead of being followed by the built-in summarise/critique ask")
    ap.add_argument("--review-question-file", default=None, help="extra question for the final DeepSeek review")
    ap.add_argument("--first-hop-systems", default=None, help="e.g. kimi,mistral: systems step 1 may hand off to")
    ap.add_argument("--preface-file", default=None)
    ap.add_argument("--context-file", default=os.path.join(ROOT, "_map", "CONTEXT_PACK_ROUTED.md"))
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                    help=f"routed calls before forced stop (default {DEFAULT_MAX_CALLS}, max {ABSOLUTE_MAX_CALLS}; review counts toward {ABSOLUTE_MAX_CALLS})")
    ap.add_argument("--max-est-tokens", type=int, default=None, help="optional spend cap: estimated tokens (chars/4)")
    ap.add_argument("--allow-systems", default="deepseek,kimi")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "_prot_replies", "route"))
    args = ap.parse_args(argv)
    if not args.approved:
        print("[ROUTE] refused: --i-approve-this-run is required (paid live calls).")
        return 2
    try:
        summary = run_route(args)
    except RouteStop as e:
        print(f"[ROUTE] refused before any call: {e}")
        return 2
    for s in summary["steps"]:
        print(f"  step {s['step']} {s['system']}/{s['suit']}: {s.get('status')} accepted={s.get('accepted')} "
              f"{s.get('refused') or ''}")
    print(f"  stopped: {summary['stopped_reason']}  review: {summary['review']}  calls: {summary['calls_made']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
