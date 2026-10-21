# v1rg0_extra_providers.py
# Extra provider slots (gemini, mistral, grok/xAI), isolated from the DeepSeek path:
# DeepSeek and Kimi requests are still built by V1rg0TransmissionSuit unchanged (via super()).
# All slots are DISABLED in v1rg0_providers.json. Model ids checked against official docs on 2026-10-19
# (see PHASE6.md, Phase 6b); re-check before enabling, ids change often.
import os
from v1rg0_transmission_suit import V1rg0TransmissionSuit

EXTRA_ENV_KEYS = {
    "gemini_flash": "GEMINI_API_KEY",
    "mistral_large": "MISTRAL_API_KEY",
    "grok_xai": "XAI_API_KEY",
    "grok_xai_fast": "XAI_API_KEY",
    "claude_sonnet": "ANTHROPIC_API_KEY",      # Phase 21: disabled slot; key from env only, never logged
}

# Phase 21: Anthropic Messages API (docs.anthropic.com, checked 2026-10-20). Not OpenAI-shaped: x-api-key header,
# anthropic-version header, top-level "system", reply text in content[] blocks of type "text".
ANTHROPIC_VERSION = "2023-06-01"


class _KeyResolver:
    """Wraps the keychain: extra providers read their own env var; everything else is delegated unchanged."""
    def __init__(self, keychain):
        self._inner = keychain

    def get_key(self, key_id):
        env_name = EXTRA_ENV_KEYS.get(key_id)
        if env_name:
            return os.environ.get(env_name) or None
        return self._inner.get_key(key_id)


class V1rg0ExtendedTransmissionSuit(V1rg0TransmissionSuit):
    def __init__(self, keychain):
        super().__init__(_KeyResolver(keychain))

    def _select_endpoint(self, model_id):
        base = super()._select_endpoint(model_id)
        if base is not None:
            return base                                   # deepseek_chat / kimi_k2_6: untouched
        extra = {
            # OpenAI-compatible endpoints (official docs, checked 2026-10-19)
            "mistral_large": {
                "url": os.environ.get("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions"),
                "model_name": os.environ.get("MISTRAL_MODEL", "mistral-large-latest"),    # docs.mistral.ai API example; mistral-large-4 is preview
            },
            "grok_xai": {
                "url": os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions"),
                "model_name": os.environ.get("XAI_MODEL", "grok-4.7"),                    # flagship, docs.x.ai/docs/models
            },
            "grok_xai_fast": {
                "url": os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions"),
                "model_name": os.environ.get("XAI_FAST_MODEL", "grok-4.3"),               # cheaper, docs.x.ai/docs/models
            },
            # Gemini OpenAI-compatibility endpoint (ai.google.dev/gemini-api/docs/openai; Google labels it beta).
            "gemini_flash": {
                "url": os.environ.get("GEMINI_API_URL",
                                      "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
                "model_name": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),    # cheap stable id, ai.google.dev/gemini-api/docs/models
            },
        }.get(model_id)
        if model_id == "claude_sonnet":
            return {"url": os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages"),
                    "model_name": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),   # docs models overview
                    "headers": {"x-api-key": None, "anthropic-version": ANTHROPIC_VERSION,
                                "content-type": "application/json"},
                    "format_fn": self._format_claude_prompt}
        if extra is None:
            return None
        return {"url": extra["url"], "model_name": extra["model_name"],
                "headers": {"Authorization": None, "content-type": "application/json"},
                "format_fn": self._format_openai_prompt}
