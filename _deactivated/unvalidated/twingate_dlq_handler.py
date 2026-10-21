# dlq_handler.py
from __future__ import annotations
from pulse import PulseBus, PulseSignal
import logging

logger = logging.getLogger(__name__)


class DLQHandler:
    """
    pull = _handle_error()    → error / contract_violation signals
    push = emit('recovery_needed', 'retry', 'escalated') → drive recovery loops
    """

    SUIT_ID = "dlq_handler"

    def __init__(self, pulse_bus: PulseBus, max_retries: int = 3) -> None:
        self.pulse_bus = pulse_bus
        self.max_retries = max_retries
        self._dead_letters: list[dict] = []

        # Subscribe to error-like events
        pulse_bus.subscribe("error", self._handle_error)
        pulse_bus.subscribe("contract_violation", self._handle_contract_violation)

    # ------------------------------------------------------------------
    # PULL: generic errors
    # ------------------------------------------------------------------
    def _handle_error(self, signal: PulseSignal) -> None:
        entry = {
            "signal": signal,
            "retry_count": 0,
            "last_attempt": signal.timestamp,
            "status": "queued",
            "type": "error",
        }
        self._dead_letters.append(entry)

        # Push recovery_needed for ProposalBuilder / orchestration
        self.pulse_bus.emit(
            self.SUIT_ID,
            "recovery_needed",
            {
                "dead_letter_id": signal.signal_id,
                "source": signal.source_suit,
                "error_payload": signal.payload,
            },
        )

    # ------------------------------------------------------------------
    # PULL: contract violations also enter DLQ
    # ------------------------------------------------------------------
    def _handle_contract_violation(self, signal: PulseSignal) -> None:
        entry = {
            "signal": signal,
            "retry_count": 0,
            "last_attempt": signal.timestamp,
            "status": "queued",
            "type": "contract_violation",
        }
        self._dead_letters.append(entry)

        self.pulse_bus.emit(
            self.SUIT_ID,
            "recovery_needed",
            {
                "dead_letter_id": signal.signal_id,
                "source": signal.source_suit,
                "error_payload": signal.payload,
            },
        )

    def _handle_concept_error(self, signal: PulseSignal):
    payload = signal.payload
    request_id = payload.get("request_id")
    if request_id and request_id in self._pending_requests:
        self._return_response(
            request_id,
            500,
            {"error": "concept_transform_failed", "reason": payload.get("reason")},
        )

    def _calculate_retry_delay(self, attempt: int) -> int:
    return min((2 ** attempt) * 100, 30000)  # Cap at 30s


    # ------------------------------------------------------------------
    # PULL: retry a dead letter via explicit retry event
    # ------------------------------------------------------------------
    def retry(self, signal_id: str) -> bool:
        for entry in self._dead_letters:
            if entry["signal"].signal_id == signal_id and entry["retry_count"] < self.max_retries:
                entry["retry_count"] += 1
                entry["status"] = "retrying"
                logger.info(
                    "DLQ RETRY | signal=%s | count=%d",
                    signal_id,
                    entry["retry_count"],
                )

                # Push explicit retry event; orchestrator decides how to re-handle
                self.pulse_bus.emit(
                    self.SUIT_ID,
                    "retry",
                    {
                        "original_signal": {
                            "signal_id": entry["signal"].signal_id,
                            "source_suit": entry["signal"].source_suit,
                            "event_type": entry["signal"].event_type,
                            "payload": entry["signal"].payload,
                            "sequence_id": entry["signal"].sequence_id,
                        },
                        "retry_count": entry["retry_count"],
                    },
                )
                return True
        return False

    # ------------------------------------------------------------------
    # PULL: escalate a dead letter
    # ------------------------------------------------------------------
    def escalate(self, signal_id: str) -> None:
        for entry in self._dead_letters:
            if entry["signal"].signal_id == signal_id:
                entry["status"] = "escalated"
                logger.warning("DLQ ESCALATE | signal=%s", signal_id)
                self.pulse_bus.emit(
                    self.SUIT_ID,
                    "escalated",
                    {
                        "signal_id": signal_id,
                        "retries_attempted": entry["retry_count"],
                        "original_payload": entry["signal"].payload,
                        "type": entry["type"],
                    },
                )
                return

    @property
    def dead_letters(self) -> list[dict]:
        return list(self._dead_letters)

