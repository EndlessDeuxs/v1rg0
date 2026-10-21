import json
from v1rg0_transmission_suit import provider_family

# Phase 9 (2): one shared status vocabulary for tasks, results and proposals.
TASK_STATUSES = ("received", "in_progress", "completed", "failed")
RESULT_STATUSES = ("success", "error")
PROPOSAL_STATUSES = ("PASS", "HELD", "REJECTED")
STATUS_ALIASES = {"EMIT": "PASS"}            # MIT verdict EMIT is recorded as PASS (EMIT->PASS kept)
ALL_STATUSES = TASK_STATUSES + RESULT_STATUSES + PROPOSAL_STATUSES


def normalize_status(status):
    return STATUS_ALIASES.get(status, status)


class V1rg0ValidationGate:
    def __init__(self):
        self._task_schema = {
            "required_fields": ["task_id", "timestamp", "status", "payload"],
            "payload_required_fields": ["prompt"],
            "optional_payload_fields": ["model_id", "system", "max_tokens", "design_brief", "suit_id"]
        }
        self._result_schema = {
            "required_fields": ["status", "model_id", "data"],
            "status_values": list(RESULT_STATUSES)
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
            if normalize_status(task["status"]) not in ALL_STATUSES:
                warnings.append(f"Non-standard status: {task['status']}")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def validate_result(self, result: dict) -> dict:
        errors, warnings = [], []
        for field in self._result_schema["required_fields"]:
            if field not in result:
                errors.append(f"Missing required result field: '{field}'")
        if "status" in result:
            st = normalize_status(result["status"])
            if st not in ALL_STATUSES:
                errors.append(f"Status must be one of: {list(ALL_STATUSES)}")
            elif st not in RESULT_STATUSES:
                warnings.append(f"Non-transport status on a result: {result['status']}")
        if result.get("status") == "success" and "data" in result and not isinstance(result["data"], dict):
            warnings.append("Data not a structured dict")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def extract_content(self, result: dict, model_id: str) -> str | None:
        if result.get("status") != "success" or not result.get("data"):
            return None
        data = result["data"]
        if "claude" in model_id:
            # Phase 21: newer Claude models may put thinking blocks first; take the text blocks only
            try:
                texts = [b["text"] for b in data["content"] if isinstance(b, dict) and b.get("type", "text") == "text"
                         and isinstance(b.get("text"), str)]
            except (KeyError, TypeError):
                return None
            return "\n".join(texts) if texts else None
        if provider_family(model_id) is not None:     # Phase 9 (1): same list as _select_endpoint
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                return None
        if isinstance(data, dict):
            for key in ["response", "text", "output", "message"]:
                if key in data:
                    return str(data[key])
        return None