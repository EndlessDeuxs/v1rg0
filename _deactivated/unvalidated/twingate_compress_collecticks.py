# compress_collecticks.py — PATCHED
# Token budget: 5/5 (sandbox constraint)
# Production: No token limit enforced for external API responses

import json
import logging

def compress_instruction(raw: str) -> str:
    """
    Strip narrative, keep only parseable JSON.
    On failure, log the error and return the raw input for recovery.
    """
    if not isinstance(raw, str):
        return ""
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, separators=(',', ':'))
    except json.JSONDecodeError as e:
        # PATCH: Log failure, preserve raw input
        logging.warning(f"compress_instruction: JSON parse failed — {e}")
        return raw  # Return raw input instead of empty string

def validate_token_budget(block: dict, max_tokens: int = 5) -> bool:
    """
    Token budget validation.
    Sandbox: 5-token limit enforced.
    Production: No limit.
    """
    if not isinstance(block, dict):
        return False
    serialized = json.dumps(block, separators=(',', ':'))
    token_count = len(serialized) // 4  # char-count proxy
    return token_count <= max_tokens
