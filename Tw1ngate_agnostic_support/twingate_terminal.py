# twingate_terminal.py
# Central Terminal — Airlock for shared twingate_* subsystems

import time
import threading
from typing import Dict, Any, Optional, Union
from twingate_envelope import TwingateEnvelope
from twingate_terminal_log import TwingateTerminalLog

class TwingateTerminal:
    """
    Central bridge for version-specific buses → shared supports.
    Uses TwingateEnvelope as the universal handoff format.
    """

    def __init__(self, log: Optional[TwingateTerminalLog] = None):
        self.log = log or TwingateTerminalLog()
        self._lock = threading.Lock()
        self._active_session: Optional[Dict] = None
        self._hold_queue: list[TwingateEnvelope] = []
        self._drain_mode = False
        self._drain_threshold = 8

    def _check_drain_mode(self):
        depth = len(self._hold_queue)
        if depth >= self._drain_threshold and not self._drain_mode:
            self._drain_mode = True
            self.log.record("drain_mode_engaged", {"queue_depth": depth})
        elif depth < self._drain_threshold // 2 and self._drain_mode:
            self._drain_mode = False
            self.log.record("drain_mode_disengaged", {"queue_depth": depth})

    def submit(self, envelope: Union[TwingateEnvelope, Dict]) -> Dict[str, Any]:
        """Accept either TwingateEnvelope or a dict (for easy V1rG0 calls)."""
        if isinstance(envelope, dict):
            envelope = TwingateEnvelope(**envelope)  # convert

        envelope.timestamp = time.time()

        with self._lock:
            self._check_drain_mode()
            self.log.record("envelope_received", envelope.to_dict())

            if self._active_session is None:
                self._active_session = {"envelope": envelope, "start_time": time.time()}
                self.log.record("session_started", {"correlation_id": envelope.correlation_id})
                return {"status": "accepted", "correlation_id": envelope.correlation_id}

            self._hold_queue.append(envelope)
            self._hold_queue.sort(key=lambda e: e.priority, reverse=True)
            self.log.record("enqueued", {
                "correlation_id": envelope.correlation_id,
                "queue_depth": len(self._hold_queue),
                "drain_mode": self._drain_mode
            })
            return {"status": "queued", "correlation_id": envelope.correlation_id}

    def complete_session(self, correlation_id: str, result: Dict[str, Any]) -> None:
        """Agnostic bus calls this when done."""
        with self._lock:
            if self._active_session and self._active_session["envelope"].correlation_id == correlation_id:
                self.log.record("session_completed", {
                    "correlation_id": correlation_id,
                    "result_status": result.get("status")
                })
                self._active_session = None
                self._process_next_in_queue()
            else:
                self.log.record("orphaned_reply", {"correlation_id": correlation_id})

    def _process_next_in_queue(self):
        if self._hold_queue:
            next_envelope = self._hold_queue.pop(0)
            self._active_session = {"envelope": next_envelope, "start_time": time.time()}
            self.log.record("dequeued_to_active", {"correlation_id": next_envelope.correlation_id})

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_session": bool(self._active_session),
                "hold_queue_depth": len(self._hold_queue),
                "drain_mode": self._drain_mode,
            }