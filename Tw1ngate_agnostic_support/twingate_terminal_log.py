# twingate_terminal_log.py
# Shared, clean logging for Terminal — mechanics independent of version logs

import time
from typing import Dict, List, Any

class TwingateTerminalLog:
    def __init__(self, max_entries: int = 2000):
        self.entries: List[Dict[str, Any]] = []
        self.max_entries = max_entries

    def record(self, event_type: str, details: Dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "version": details.get("version"),
            "correlation_id": details.get("correlation_id"),
            "target_suit": details.get("target_suit"),
            "details": details
        }
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)

    def get_recent(self, limit: int = 100, version: Optional[str] = None) -> List[Dict]:
        recent = self.entries[-limit:]
        if version:
            return [e for e in recent if e.get("version") == version]
        return recent

    def clear(self) -> None:
        self.entries.clear()