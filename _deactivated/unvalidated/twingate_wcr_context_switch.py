# wcr_context_switch.py
# Purpose: Parseable code generation for WCR context switching
# Token budget: 5/5 (tracked via char-count proxy)

import json
import uuid
from datetime import datetime, timezone

class WCRContextSwitch:
    """Manages parseable atomic state dumps for WCR context switching."""
    
    def __init__(self, session_id: str, wcr_depth: int = 1):
        self.session_id = session_id
        self.wcr_depth = wcr_depth
        self.execution_order = []
        self.checkpoint = None
    
    def generate_atomic_block(self, quest_id: str, action: str, payload: dict) -> dict:
        """Generate a parseable atomic instruction block."""
        block = {
            "block_id": uuid.uuid4().hex[:16],
            "session_id": self.session_id,
            "quest_id": quest_id,
            "action": action,
            "payload": payload,
            "state": "atomic",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return block
    
    def _token_proxy(self, max_budget: int = 5) -> int:
        """
        Approximate remaining token budget using char-count proxy.
        Ensures a non-negative value within [0, max_budget].
        """
        serialized = json.dumps(self.checkpoint or {}, separators=(',', ':'))
        used = len(serialized) // 4
        remaining = max_budget - used
        if remaining < 0:
            remaining = 0
        if remaining > max_budget:
            remaining = max_budget
        return remaining
    
    def atomic_state_dump(self) -> dict:
        """Preserve full WCR context for safe switching."""
        self.checkpoint = {
            "session_id": self.session_id,
            "wcr_depth": self.wcr_depth,
            "current_quest": self.execution_order[-1] if self.execution_order else None,
            "execution_order_position": len(self.execution_order)
        }
        # token_budget_remaining computed after checkpoint is defined
        self.checkpoint["token_budget_remaining"] = self._token_proxy()
        return self.checkpoint
    
    def parse_context(self, dump: dict) -> bool:
        """Restore from atomic state dump."""
        if not isinstance(dump, dict):
            return False
        required_keys = ["session_id", "wcr_depth"]
        if not all(k in dump for k in required_keys):
            return False
        self.session_id = dump["session_id"]
        self.wcr_depth = dump["wcr_depth"]
        self.execution_order = []  # caller may repopulate
        self.checkpoint = dump
        return True