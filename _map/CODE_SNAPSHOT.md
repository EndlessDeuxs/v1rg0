# V1rG0 code snapshot for outside review (read-only, no secrets; built by Collec.tor)

## unvalidated/v1rg0_transmission_suit.py (full)
```
# v1rg0_transmission_suit.py
import os
import requests
import json

class V1rg0TransmissionSuit:
    def __init__(self, keychain: 'V1rg0Keychain'):
        self._keychain = keychain

    def _select_endpoint(self, model_id: str) -> dict | None:
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

    def _format_claude_prompt(self, concept: dict) -> dict:
        return {
            "model": self._model_name,
            "max_tokens": concept.get("max_tokens", int(os.environ.get("V1RG0_MAX_TOKENS", "4096"))),
            "system": concept.get("system", "You are P_ROT_OGRAPH_R of the Twingate. Respond in character."),
            "messages": [{"role": "user", "content": concept.get("prompt", "Proceed.")}]
        }

    def _format_openai_prompt(self, concept: dict) -> dict:
        return {
            "model": self._model_name,
            "max_tokens": concept.get("max_tokens", int(os.environ.get("V1RG0_MAX_TOKENS", "4096"))),
            "messages": [
                {"role": "system", "content": concept.get("system", "You are P_ROT_OGRAPH_R of the Twingate. Respond in character.")},
                {"role": "user", "content": concept.get("prompt", "Proceed.")}
            ]
        }

    def _format_kimi_prompt(self, concept: dict) -> dict:
        payload = self._format_openai_prompt(concept)
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
        self._model_name = endpoint["model_name"]
        try:
            payload = endpoint["format_fn"](concept)
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
```

## unvalidated/v1rg0_validation_gate.py (full)
```
import json

class V1rg0ValidationGate:
    def __init__(self):
        self._task_schema = {
            "required_fields": ["task_id", "timestamp", "status", "payload"],
            "payload_required_fields": ["prompt"],
            "optional_payload_fields": ["model_id", "system", "max_tokens", "design_brief"]
        }
        self._result_schema = {
            "required_fields": ["status", "model_id", "data"],
            "status_values": ["success", "error"]
        }

    def validate_task(self, task: dict) -> dict:
        errors, warnings = [], []
        for field in self._task_schema["required_fields"]:
            if field not in task:
                errors.append(f"Missing required field: '{field}'")
        if "payload" in task:
            payload = task["payload"]
            for field in self._task_schema["payload_required_fields"]:
                if field not in payload:
                    errors.append(f"Missing required payload field: '{field}'")
            if "prompt" in payload and not isinstance(payload["prompt"], str):
                errors.append("Payload field 'prompt' must be a string")
            if "max_tokens" in payload:
                if not isinstance(payload["max_tokens"], int):
                    errors.append("Payload field 'max_tokens' must be an integer")
                elif payload["max_tokens"] < 1 or payload["max_tokens"] > 8192:
                    warnings.append(f"max_tokens ({payload['max_tokens']}) outside [1, 8192]")
            if "model_id" in payload and not isinstance(payload["model_id"], str):
                errors.append("Payload field 'model_id' must be a string")
        if "status" in task:
            valid_statuses = ["received", "in_progress", "completed", "failed"]
            if task["status"] not in valid_statuses:
                warnings.append(f"Non-standard status: {task['status']}")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def validate_result(self, result: dict) -> dict:
        errors, warnings = [], []
        for field in self._result_schema["required_fields"]:
            if field not in result:
                errors.append(f"Missing required result field: '{field}'")
        if "status" in result and result["status"] not in self._result_schema["status_values"]:
            errors.append(f"Status must be one of: {self._result_schema['status_values']}")
        if result.get("status") == "success" and "data" in result and not isinstance(result["data"], dict):
            warnings.append("Data not a structured dict")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def extract_content(self, result: dict, model_id: str) -> str | None:
        if result.get("status") != "success" or not result.get("data"):
            return None
        data = result["data"]
        if "claude" in model_id:
            try:
                return data["content"][0]["text"]
            except (KeyError, IndexError, TypeError):
                return None
        if any(k in model_id for k in ("openai", "deepseek", "kimi", "gemini", "mistral", "grok")):
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                return None
        if isinstance(data, dict):
            for key in ["response", "text", "output", "message"]:
                if key in data:
                    return str(data[key])
        return None
```

## V1rG0_specific/v1rg0_providers.json (full)
```
{
  "_comment": "Provider allowlist. Only providers in enabled_providers can be called. Enabling any provider other than deepseek is a human edit by the owner. Model ids for gemini/mistral/grok were checked against official docs on 2026-10-19; re-check before enabling.",
  "enabled_providers": ["deepseek"],
  "judge_model": "deepseek_chat",
  "providers": {
    "deepseek": {"model_ids": ["deepseek_chat"], "role": "primary + default/fallback judge", "env_key": "DEEPSEEK_API_KEY"},
    "kimi": {"model_ids": ["kimi_k2_6"], "role": "secondary (idle until owner enables; cross-check is design-only)", "env_key": "MOONSHOT_API_KEY"},
    "gemini": {"model_ids": ["gemini_flash"], "role": "slot (disabled): gemini-3.5-flash-lite", "env_key": "GEMINI_API_KEY"},
    "mistral": {"model_ids": ["mistral_large"], "role": "slot (disabled): mistral-large-latest", "env_key": "MISTRAL_API_KEY"},
    "grok": {"model_ids": ["grok_xai", "grok_xai_fast"], "role": "slot (disabled): grok_xai=grok-4.7 flagship, grok_xai_fast=grok-4.3 cheaper", "env_key": "XAI_API_KEY"}
  }
}

```

## unvalidated/v1rg0_proposal_builder.py (outline: classes and functions only)
```
class ProposalType  # Maps from mit_action tokens to proposal types.
class UrgencyLevel  # Routes the proposal through the downstream handler.
class ProposalBuildError  # Raised when a proposal cannot be built from the given inputs.
class ProposalBuilder  # Transforms MIT evaluation output into structured, actionable proposals.
def __init__(self, session_id, default_ttl_seconds)
def build(self, mit_evaluation, event_context, override_urgency, extra_notes)  # Build a proposal from an MIT evaluation result.
def build_batch(self, evaluations)  # Build multiple proposals from a list of (mit_evaluation, event_context) pairs.
def is_expired(proposal)  # Returns True if the proposal has exceeded its TTL.
def get_routing_token(proposal)  # Compact routing token for downstream decision-making.
def _validate_mit_evaluation(self, evaluation, trace)  # Validate that the MIT evaluation contains all required fields.
def _validate_event_context(self, context, trace)  # Validate that the event context contains all required fields.
def _resolve_proposal_type(self, mit_action, trace)  # Map mit_action token to ProposalType. Raises on unknown token.
def _derive_urgency(self, score)  # Derive urgency from MIT score using defined thresholds.
def _derive_ttl(self, urgency)  # Derive time-to-live from urgency level.
def _build_proposal_id(self, event_id, mit_action, ttl)  # Build a deterministic proposal ID using SHA-256.
```

## V1rG0_specific/v1rg0_memory_store.py (outline: classes and functions only)
```
class MemoryStore  # Persistent (in-session) memory store for V1rG0 packets.
def __init__(self)
def push_memory(self, packet)  # PUSH: Store a packet.
def pull_latest(self)  # PULL: Return the most recently stored packet.
def pull_by_tier(self, tier, limit)  # PULL: Return recent packets for a specific tier.
def pull_recent(self, limit)  # PULL: Return recent packets across all tiers.
def pull_tier_counts(self)  # PULL: Return count of stored packets per tier.
def pull_push_count(self)  # PULL: Return total successful pushes this session.
def is_empty(self)  # True if no packets have been stored.
def flush_tier(self, tier)  # Clear a specific tier queue.
```
