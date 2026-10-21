# twingate_envelope.py
# Shared envelope standard for Terminal communication across versions

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class TwingateEnvelope:
    """
    Universal envelope for Terminal handoffs.
    Flexible metadata for V1rG0 nuance while remaining version-agnostic.
    """
    version: str                      # "V1rG0", "TG6D", etc.
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_suit: str                  # e.g. "nexus", "dlq_handler", "memory_store"
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)   # nuance / intent
    priority: int = 0
    timeout_seconds: float = 30.0
    timestamp: float = field(default_factory=time.time)
    reply_to: str = "default"         # bus or component name

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}