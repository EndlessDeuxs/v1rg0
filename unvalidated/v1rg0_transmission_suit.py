# v1rg0_transmission_suit.py
import os
import requests
import json
import re

# Phase 9 (1): single source of truth for providers that answer in OpenAI chat-completions shape.
# Used by _select_endpoint here (and the extended suit) and by V1rg0ValidationGate.extract_content.
# deepseek/kimi are routed here; gemini/mistral/grok slots live in V1rG0_specific/v1rg0_extra_providers.py (disabled).
CHAT_COMPLETIONS_FAMILIES = ("deepseek", "kimi", "gemini", "mistral", "grok", "openai")


def provider_family(model_id) -> str | None:
    """Return the family prefix a model_id belongs to, or None if it is not a known chat-completions provider."""
    mid = str(model_id or "").lower()
    for fam in CHAT_COMPLETIONS_FAMILIES:
        if fam in mid:
            return fam
    return None


def max_tokens_cap() -> int:
    """Phase 9 (4): hard ceiling from V1RG0_MAX_TOKENS (default 4096)."""
    try:
        return max(1, int(os.environ.get("V1RG0_MAX_TOKENS", "4096")))
    except ValueError:
        return 4096


def bounded_max_tokens(concept: dict) -> int:
    """Requested max_tokens clamped to [1, cap]; never exceeds V1RG0_MAX_TOKENS."""
    cap = max_tokens_cap()
    try:
        req = int(concept.get("max_tokens", cap))
    except (TypeError, ValueError):
        req = cap
    return min(max(1, req), cap)


# Phase 10: suit prompts come from V1rG0_specific/v1rg0_suits.json (override path: V1RG0_SUITS_FILE).
SUITS_FILE = os.environ.get("V1RG0_SUITS_FILE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                              "V1rG0_specific", "v1rg0_suits.json"))
NEUTRAL_PROMPT = "You are a helpful assistant. Answer clearly and directly."


USER_SUITS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "V1rG0_specific", "user_suits.json")
SUIT_ID_RE = re.compile(r"^[a-z0-9_]{2,32}$")
MAX_USER_SUITS, MAX_PURPOSE, MAX_PROMPT = 20, 160, 4000


class UserSuitsError(Exception):
    """Phase 17: a bad user_suits.json. Not a ValueError on purpose, so it is never swallowed as 'no suits file'."""


def merge_user_suits(data: dict, user: dict) -> dict:
    """Phase 17: add the user's own suits next to the built-in ones, or, with "use_only_my_suits": true,
    use only theirs. Built-in ids can't be reused. Everything is checked before any call."""
    if not isinstance(user, dict) or not isinstance(user.get("suits", {}), dict):
        raise UserSuitsError("user_suits.json must be an object with a \"suits\" object")
    mine = user.get("suits", {})
    only_mine = user.get("use_only_my_suits", False)
    if not isinstance(only_mine, bool):
        raise UserSuitsError("use_only_my_suits must be true or false")
    if len(mine) > MAX_USER_SUITS:
        raise UserSuitsError(f"at most {MAX_USER_SUITS} user suits (found {len(mine)})")
    if only_mine and not mine:
        raise UserSuitsError("use_only_my_suits is true but no user suits are defined")
    builtin = data.get("suits", {})
    for sid, suit in mine.items():
        if not SUIT_ID_RE.match(str(sid)):
            raise UserSuitsError(f"suit id {sid!r}: use 2-32 characters a-z, 0-9 or _")
        if sid in builtin:
            raise UserSuitsError(f"suit id {sid!r} is a built-in suit; pick another id")
        if not isinstance(suit, dict):
            raise UserSuitsError(f"suit {sid!r} must be an object with purpose and prompt")
        purpose, prompt = suit.get("purpose"), suit.get("prompt")
        if not isinstance(purpose, str) or not purpose.strip() or "\n" in purpose or len(purpose) > MAX_PURPOSE:
            raise UserSuitsError(f"suit {sid!r}: purpose must be one line of 1-{MAX_PURPOSE} characters")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
            raise UserSuitsError(f"suit {sid!r}: prompt must be 1-{MAX_PROMPT} characters")
    out = dict(data)
    out["suits"] = dict(mine) if only_mine else {**builtin, **mine}
    out["use_only_my_suits"] = only_mine
    start = user.get("start_suit")
    if only_mine and not start:
        raise UserSuitsError("use_only_my_suits is true, so start_suit must name one of your suits")
    if start:
        if start not in out["suits"]:
            raise UserSuitsError(f"start_suit {start!r} is not a known suit")
        out["start_suit"] = start
    if only_mine:
        out["default_suit"] = start
    return out


def load_suits(path: str = None) -> dict:
    explicit = path or os.environ.get("V1RG0_SUITS_FILE")
    with open(explicit or SUITS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if explicit:                                  # an explicit suits file replaces everything, as before
        return data
    user_path = os.environ.get("V1RG0_USER_SUITS_FILE", USER_SUITS_FILE)
    if not os.path.isfile(user_path):
        return data
    try:
        with open(user_path, "r", encoding="utf-8") as f:
            user = json.load(f)
    except ValueError as e:
        raise UserSuitsError(f"user_suits.json is not valid JSON: {e}")
    return merge_user_suits(data, user)


def suit_prompt(concept: dict) -> str:
    """System prompt for a call: explicit 'system' wins; else the assigned suit_id; else the file's default_suit.
    'blank' (or a missing suits file) gives the neutral prompt. Unknown suit ids raise ValueError."""
    if concept.get("system"):
        return concept["system"]
    try:
        data = load_suits()
    except (OSError, ValueError):
        return NEUTRAL_PROMPT
    sid = concept.get("suit_id") or data.get("default_suit", "blank")
    suit = data.get("suits", {}).get(sid)
    if suit is None:
        raise ValueError(f"unknown suit_id {sid!r}")
    base = suit.get("prompt") or NEUTRAL_PROMPT
    note = data.get("scope_note")
    return f"{base}\n\n{note}" if note else base


class V1rg0TransmissionSuit:
    def __init__(self, keychain: 'V1rg0Keychain'):
        self._keychain = keychain

    def _select_endpoint(self, model_id: str) -> dict | None:
        if provider_family(model_id) is None:
            return None
        # Claude -> DeepSeek, OpenAI slot -> Kimi K2.6 (both OpenAI-compatible)
        registry = {
            "deepseek_chat": {
                "url": os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"),
                "headers": {"Authorization": None, "content-type": "application/json"},
                "model_name": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                "format_fn": self._format_openai_prompt
            },
            "kimi_k2_6": {
                "url": os.environ.get("MOONSHOT_API_URL", "https://api.moonshot.ai/v1/chat/completions"),
                "headers": {"Authorization": None, "content-type": "application/json"},
                "model_name": os.environ.get("KIMI_MODEL", "kimi-k2.6"),
                "format_fn": self._format_kimi_prompt
            }
        }
        return registry.get(model_id)

    def _format_claude_prompt(self, concept: dict, model_name: str = None) -> dict:
        return {
            "model": model_name,
            "max_tokens": bounded_max_tokens(concept),
            "system": suit_prompt(concept),
            "messages": [{"role": "user", "content": concept.get("prompt", "Proceed.")}]
        }

    def _format_openai_prompt(self, concept: dict, model_name: str = None) -> dict:
        return {
            "model": model_name,
            "max_tokens": bounded_max_tokens(concept),
            "messages": [
                {"role": "system", "content": suit_prompt(concept)},
                {"role": "user", "content": concept.get("prompt", "Proceed.")}
            ]
        }

    def _format_kimi_prompt(self, concept: dict, model_name: str = None) -> dict:
        payload = self._format_openai_prompt(concept, model_name)
        # KIMI_THINKING=disabled (default) or enabled
        payload["thinking"] = {"type": os.environ.get("KIMI_THINKING", "disabled")}
        return payload

    def transmit(self, model_id: str, concept: dict) -> dict:
        endpoint = self._select_endpoint(model_id)
        if not endpoint:
            return {"status": "error", "error": f"Unknown model_id: {model_id}", "data": None}
        api_key = self._keychain.get_key(model_id)
        if not api_key:
            return {"status": "error", "error": f"No API key found for {model_id}", "data": None}
        headers = endpoint["headers"].copy()
        if "x-api-key" in headers:
            headers["x-api-key"] = api_key
        elif "Authorization" in headers:
            headers["Authorization"] = f"Bearer {api_key}"
        model_name = endpoint["model_name"]          # Phase 9 (3): local per call, no shared state
        try:
            payload = endpoint["format_fn"](concept, model_name)
        except Exception as e:
            return {"status": "error", "error": f"Prompt formatting failed: {str(e)}", "data": None}
        try:
            response = requests.post(endpoint["url"], headers=headers, json=payload, timeout=int(os.environ.get("V1RG0_HTTP_TIMEOUT", "120")))
            response.raise_for_status()
            return {"status": "success", "model_id": model_id, "data": response.json()}
        except requests.exceptions.RequestException as e:
            return {"status": "error", "error": f"API call failed: {str(e)}", "data": None}
        except json.JSONDecodeError as e:
            return {"status": "error", "error": f"Response parsing failed: {str(e)}", "data": None}