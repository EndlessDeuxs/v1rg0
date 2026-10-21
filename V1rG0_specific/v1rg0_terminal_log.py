# v1rg0_terminal_log.py
# Terminal-specific logging — clean mechanics, separate from version logs

import time
from typing import Any, Dict, List

class TerminalEventLog:
    def __init__(self, max_entries: int = 1000):
        self.entries: List[Dict] = []
        self.max_entries = max_entries

    def record(self, event_type: str, details: Dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "details": details
        }
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)

    def get_recent(self, limit: int = 50) -> List[Dict]:
        return self.entries[-limit:]

    def clear(self) -> None:
        self.entries.clear()