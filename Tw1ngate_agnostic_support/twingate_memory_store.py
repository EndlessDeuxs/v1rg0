# memory_store.py
from __future__ import annotations
from contract_registry import ContractRegistry, attach_contract_middleware
from pulse import PulseBus, PulseSignal
import logging

logger = logging.getLogger(__name__)

class MemoryStore:
    SUIT_ID = "memory_store"

    def __init__(self, pulse_bus: PulseBus) -> None:
        self.pulse_bus = pulse_bus
        self._store: dict[str, list[dict]] = {}
        ContractRegistry().register_suit(self.SUIT_ID, {"input": {"required_fields": []}})
        attach_contract_middleware(pulse_bus, self.SUIT_ID)
        pulse_bus.subscribe("*", self._log_signal)
        pulse_bus.subscribe("memory_query", self._handle_query)

    def _log_signal(self, signal: PulseSignal) -> None:
        key = f"{signal.source_suit}:{signal.event_type}"
        bucket = self._store.setdefault(key, [])
        bucket.append({
            "signal_id": signal.signal_id,
            "timestamp": signal.timestamp,
            "sequence_id": signal.sequence_id,
            "payload": signal.payload,
        })
        if len(bucket) > 1000:
            self._store[key] = bucket[-1000:]

    def _handle_query(self, signal: PulseSignal) -> None:
        results = self.query(
            source_suit=signal.payload.get("source_suit"),
            event_type=signal.payload.get("event_type"),
            limit=signal.payload.get("limit", 10),
        )
        self.pulse_bus.emit(self.SUIT_ID, "memory_query_result", {
            "request_signal_id": signal.signal_id,
            "results": results,
            "count": len(results),
        })

    def query(self, source_suit: str | None = None, event_type: str | None = None, limit: int = 10) -> list[dict]:
        results: list[dict] = []
        for key, entries in self._store.items():
            suit, etype = key.split(":", 1)
            if source_suit and suit != source_suit:
                continue
            if event_type and etype != event_type:
                continue
            results.extend(entries)
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results[:limit]

    @property
    def store_keys(self) -> list[str]:
        return list(self._store.keys())