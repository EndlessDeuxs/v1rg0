#Communications_Pathways
# FILENAME: UIT_registry_unknowns.py
"""
UIT Unknown Registry – Graded unknown tracking with decay.
"""
import json
import os
import time
from typing import Dict, List, Optional
from .UIT_interfaces import UnknownGradient, UnknownType

UNKNOWN_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "uit_unknowns.json")

class UnknownRegistry:
    def __init__(self, path: str = UNKNOWN_REGISTRY_PATH, decay_rate: float = 0.02):
        self.path = path
        self.decay_rate = decay_rate
        self.entries: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, default=str)

    def log(self, unknown: UnknownGradient, context: Optional[str] = None):
        self.entries.append({
            "timestamp": time.time(),
            "type": unknown.type.value if isinstance(unknown.type, UnknownType) else unknown.type,
            "magnitude": unknown.magnitude,
            "context_note": unknown.context_note or context,
            "resolved": False,
            "historical": False,
            "decay": 1.0
        })
        self.save()

    def get_active(self) -> List[Dict]:
        now = time.time()
        active = []
        for entry in self.entries:
            if entry.get("resolved", False) or entry.get("historical", False):
                continue
            age = (now - entry["timestamp"]) / 3600.0
            entry["decay"] = max(0.1, 1.0 - (age * self.decay_rate))
            active.append(entry)
        return active

    def resolve(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries[index]["resolved"] = True
            self.entries[index]["resolved_timestamp"] = time.time()
            self.entries[index]["historical"] = True
            self.save()