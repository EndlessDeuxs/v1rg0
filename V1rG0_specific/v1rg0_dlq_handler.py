# v1rg0_dlq_handler.py
# V1rG0-specific Dead Letter Queue with compensation integration

import logging
import time
from typing import Dict, List, Optional
from v1rg0_compensation import PushPullCompensator, CompensationStrategy
from v1rg0_memory_store import MemoryStore  # For tiered storage if desired

log = logging.getLogger("V1rG0.DLQ")


class V1rG0DLQHandler:
    """
    V1rG0 Dead Letter Queue Handler.
    Works with Orchestrator, PushPullCompensator, and MemoryStore.
    """

    SUIT_ID = "v1rg0_dlq_handler"  # Kept for contract compatibility

    def __init__(self, compensator: Optional[PushPullCompensator] = None,
                 memory_store: Optional[MemoryStore] = None,
                 max_retries: int = 3):
        self.compensator = compensator or PushPullCompensator(max_retries=max_retries)
        self.memory_store = memory_store
        self._dead_letters: List[Dict] = []
        self.max_retries = max_retries

    def handle_error(self, error_context: Dict) -> None:
        """Main entrypoint for errors from orchestrator / MIT / activator."""
        entry = {
            "dead_letter_id": error_context.get("event_id") or f"dlq_{int(time.time())}",
            "timestamp": time.time(),
            "source": error_context.get("source", "unknown"),
            "error_payload": error_context.get("error_payload") or error_context,
            "retry_count": 0,
            "status": "queued",
            "mit_action": error_context.get("mit_action"),
        }

        self._dead_letters.append(entry)

        # Optional: Store in V1rG0 MemoryStore (FLUSH or UNKNOWN tier)
        if self.memory_store:
            self.memory_store.push_memory({
                "tier": "FLUSH",
                "composite": 0.0,
                "salience": {"survival": 0.9},
                "pressure": 0.8,
                "payload": entry
            })

        log.warning(f"DLQ: queued dead letter {entry['dead_letter_id']} from {entry['source']}")

        # Push recovery via compensator
        self.compensator.push_with_compensation(
            push_fn=lambda: self._attempt_recovery(entry),
            strategy=CompensationStrategy.RETRY,
            context=f"dlq_recovery_{entry['dead_letter_id']}"
        )

    def _attempt_recovery(self, entry: Dict) -> bool:
        """Internal recovery attempt with compensation."""
        entry["retry_count"] += 1
        entry["last_attempt"] = time.time()

        if entry["retry_count"] > self.max_retries:
            entry["status"] = "escalated"
            log.error(f"DLQ: max retries exceeded for {entry['dead_letter_id']}")
            # Could trigger proposal for human escalation here
            return False

        # TODO: Re-inject into orchestrator or specific recovery path
        # For now we mark success if under retry limit
        entry["status"] = "retried"
        log.info(f"DLQ: retry {entry['retry_count']}/{self.max_retries} for {entry['dead_letter_id']}")
        return True

    def retry(self, dead_letter_id: str) -> bool:
        """Manual retry trigger."""
        for entry in self._dead_letters:
            if entry["dead_letter_id"] == dead_letter_id:
                return self._attempt_recovery(entry)
        return False

    def escalate(self, dead_letter_id: str) -> None:
        """Escalate to human / fallback."""
        for entry in self._dead_letters:
            if entry["dead_letter_id"] == dead_letter_id:
                entry["status"] = "escalated"
                log.warning(f"DLQ: escalated {dead_letter_id}")
                # Could emit proposal with mit_action="escalate"
                return

    def get_dead_letters(self, status: Optional[str] = None) -> List[Dict]:
        """Pull current dead letters."""
        if status:
            return [e for e in self._dead_letters if e["status"] == status]
        return list(self._dead_letters)

    def clear(self) -> int:
        """Clear processed letters."""
        initial_len = len(self._dead_letters)
        self._dead_letters = [e for e in self._dead_letters if e["status"] not in ("retried", "escalated")]
        return initial_len - len(self._dead_letters)
