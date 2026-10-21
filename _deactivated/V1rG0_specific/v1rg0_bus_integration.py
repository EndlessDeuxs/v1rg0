# v1rg0_bus_integration.py
# Bus integration layer for the V1rG0 pipeline with Terminal support.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from twingate_envelope import TwingateEnvelope
from twingate_terminal import TwingateTerminal

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ENUMS + RESULT TYPES (unchanged)
# ---------------------------------------------------------------------------

class BusPublishStatus(str, Enum):
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    REJECTED = "REJECTED"
    STUB     = "STUB"


@dataclass
class BusPublishResult:
    proposal_id:  str
    topic:        str
    status:       BusPublishStatus
    attempt_count: int
    published_at: Optional[float]  = None
    elapsed_ms:   float            = 0.0
    notes:        List[str]        = field(default_factory=list)
    error:        Optional[str]    = None


# ---------------------------------------------------------------------------
# PRIVATE HELPERS (unchanged)
# ---------------------------------------------------------------------------

def _resolve_topic(proposal: Dict[str, Any]) -> str:
    proposal_type = proposal.get("proposal_type", "unclassified")
    known_types = {"surface_action", "hold_action", "escalate_action", "fallback_action", "bypass_action", "no_op"}
    if proposal_type not in known_types:
        log.warning(f"BUS | unknown proposal_type={proposal_type} | routing to unclassified")
        proposal_type = "unclassified"
    return f"v1rg0.proposals.{proposal_type}"


def _make_bus_call(adapter, topic: str, proposal: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = adapter(topic, proposal)
        if not isinstance(result, dict):
            return {"ok": False, "error": "adapter returned non-dict"}
        return result
    except Exception as exc:
        log.error(f"BUS ADAPTER EXCEPTION | topic={topic} | error={exc}")
        return {"ok": False, "error": str(exc)}


def _build_success_result(proposal_id: str, topic: str, attempt: int, t_start: float) -> BusPublishResult:
    elapsed = (time.time() - t_start) * 1000
    return BusPublishResult(proposal_id=proposal_id, topic=topic, status=BusPublishStatus.SUCCESS,
                            attempt_count=attempt, published_at=time.time(), elapsed_ms=elapsed,
                            notes=[f"Published on attempt {attempt}."])


def _build_failed_result(proposal_id: str, topic: str, attempt: int, t_start: float, error: str) -> BusPublishResult:
    elapsed = (time.time() - t_start) * 1000
    return BusPublishResult(proposal_id=proposal_id, topic=topic, status=BusPublishStatus.FAILED,
                            attempt_count=attempt, elapsed_ms=elapsed, error=error,
                            notes=[f"Failed after {attempt} attempt(s). Error: {error}"])


def _build_stub_result(proposal_id: str, topic: str) -> BusPublishResult:
    log.info(f"BUS STUB | proposal={proposal_id} | topic={topic} | no real adapter")
    return BusPublishResult(proposal_id=proposal_id, topic=topic, status=BusPublishStatus.STUB,
                            attempt_count=1, published_at=time.time(), elapsed_ms=0.0,
                            notes=["Stub adapter — no real bus connection."])


# ---------------------------------------------------------------------------
# MAIN BUS INTEGRATION
# ---------------------------------------------------------------------------

class V1rG0BusIntegration:
    """
    Publishes proposals — now with optional Terminal support for shared twingate_* subsystems.
    """

    def __init__(
        self,
        adapter: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
        terminal: Optional[TwingateTerminal] = None,
        max_attempts: int = 3,
    ) -> None:
        self._adapter = adapter
        self.terminal = terminal          # Injected Terminal for shared support calls
        self._max_attempts = max_attempts

    def publish(
        self,
        proposal: Dict[str, Any],
        notes: Optional[List[str]] = None,
    ) -> BusPublishResult:
        """Existing publish logic (unchanged core behavior)."""
        proposal_id = proposal.get("proposal_id", str(uuid.uuid4()))
        topic = _resolve_topic(proposal)
        t_start = time.time()

        if self._adapter is None:
            return _build_stub_result(proposal_id, topic)

        attempt = 0
        last_error = ""

        while attempt < self._max_attempts:
            attempt += 1
            result = _make_bus_call(self._adapter, topic, proposal)

            if result.get("ok"):
                log.info(f"BUS PUBLISH OK | proposal={proposal_id} | topic={topic} | attempt={attempt}")
                return _build_success_result(proposal_id, topic, attempt, t_start)

            last_error = result.get("error", "adapter returned not-ok")
            log.warning(f"BUS PUBLISH FAIL | proposal={proposal_id} | topic={topic} | attempt={attempt}/{self._max_attempts}")

        return _build_failed_result(proposal_id, topic, attempt, t_start, last_error)

    # --------------------- Terminal Integration ---------------------

    def publish_via_terminal(self, proposal: Dict[str, Any], target_suit: str) -> Dict[str, Any]:
        """
        Send proposal (or any payload) to a shared twingate_* suit via Terminal.
        Returns immediate ack. V1rG0 bus should poll or use compensation for result.
        """
        if not self.terminal:
            log.warning("No Terminal injected — falling back to local stub")
            return {"status": "no_terminal", "correlation_id": str(uuid.uuid4())}

        envelope = TwingateEnvelope(
            version="V1rG0",
            target_suit=target_suit,
            payload=proposal,
            metadata={"source": "v1rg0_bus", "intent": "proposal_publish"},
            priority=proposal.get("urgency_level", 0) or 5
        )

        response = self.terminal.submit(envelope)
        log.info(f"Terminal submit → {response['status']} | correlation={envelope.correlation_id} | target={target_suit}")
        return response

    def inject_terminal(self, terminal: TwingateTerminal) -> None:
        """Post-construction injection of Terminal (per your non-negotiables)."""
        self.terminal = terminal
        log.info("Terminal injected into V1rG0BusIntegration.")

    def inject_adapter(self, adapter: Callable[[str, Dict[str, Any]], Dict[str, Any]]) -> None:
        self._adapter = adapter
        log.info("BUS | adapter injected.")

    def health_check(self) -> Dict[str, Any]:
        return {
            "adapter_present": self._adapter is not None,
            "terminal_present": self.terminal is not None,
            "max_attempts": self._max_attempts,
            "status": "ready"
        }