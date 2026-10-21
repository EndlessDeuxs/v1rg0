# v1rg0_envelope.py
# V1rG0 Envelope — flexible carrier for internal and terminal communication

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class V1rG0Envelope:
    """
    Flexible envelope for V1rG0 relay/terminal communication.
    Metadata allows rich intent without over-generalizing.
    """
    target: str                      # e.g. "twingate_nexus", "twingate_dlq", "memory_store"
    payload: Dict[str, Any]
    version: str = "V1rG0"
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)  # nuance / intent flags
    priority: int = 0                # higher = more urgent
    timeout_seconds: float = 30.0
    timestamp: float = field(default_factory=time.time)
    reply_to: str = "v1rg0_bus"      # bus or component expecting reply

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "correlation_id": self.correlation_id,
            "target": self.target,
            "payload": self.payload,
            "metadata": self.metadata,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
        }