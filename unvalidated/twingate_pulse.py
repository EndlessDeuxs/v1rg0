# pulse.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable
import time
import uuid
import logging

logger = logging.getLogger(__name__)

@dataclass
class PulseSignal:
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_suit: str = ""
    event_type: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    sequence_id: int = 0

class PulseBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}
        self._sequence_counter: int = 0
        self._dlq: list[PulseSignal] = []

    def emit(self, source: str, event_type: str, payload: dict | None = None) -> PulseSignal:
        self._sequence_counter += 1
        signal = PulseSignal(
            source_suit=source,
            event_type=event_type,
            payload=payload or {},
            sequence_id=self._sequence_counter,
        )
        self._route(signal)
        return signal

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def _route(self, signal: PulseSignal) -> None:
        specific = self._subscribers.get(signal.event_type, [])
        wildcard = self._subscribers.get("*", [])
        all_handlers = specific + wildcard

        if not all_handlers:
            self._dlq.append(signal)
            if signal.event_type not in ("error", "contract_violation"):
                self.emit("pulse_bus", "error", {
                    "reason": "no_handlers",
                    "unhandled_signal_id": signal.signal_id,
                    "unhandled_event_type": signal.event_type,
                    "source": signal.source_suit,
                })
            return

        for handler in all_handlers:
            try:
                handler(signal)
            except Exception as exc:
                self._dlq.append(signal)
                if signal.event_type != "error":
                    self.emit("pulse_bus", "error", {
                        "reason": "handler_exception",
                        "signal_id": signal.signal_id,
                        "handler": handler.__name__,
                        "error": str(exc),
                    })

    @property
    def dlq(self) -> list[PulseSignal]:
        return list(self._dlq)

    @property
    def sequence_counter(self) -> int:
        return self._sequence_counter