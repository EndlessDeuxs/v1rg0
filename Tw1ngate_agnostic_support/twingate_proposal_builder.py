# proposal_builder.py
from __future__ import annotations
from contract_registry import ContractRegistry, attach_contract_middleware
from pulse import PulseBus, PulseSignal
import logging
import uuid

logger = logging.getLogger(__name__)

class ProposalBuilder:
    SUIT_ID = "proposal_builder"

    def __init__(self, pulse_bus: PulseBus) -> None:
        self.pulse_bus = pulse_bus
        self._pending: list[dict] = []
        ContractRegistry().register_suit(self.SUIT_ID, {
            "input": {"required_fields": []},
            "output": {"type": "proposal", "required_fields": ["proposal_id", "trigger_signal_id", "status"]},
        })
        attach_contract_middleware(pulse_bus, self.SUIT_ID)
        pulse_bus.subscribe("transform", self._on_transform)
        pulse_bus.subscribe("error", self._on_error)
        pulse_bus.subscribe("propose", self._on_propose_request)

    def _on_transform(self, signal: PulseSignal) -> None:
        draft = {
            "proposal_id": f"PROP-{uuid.uuid4().hex[:6]}",
            "trigger_signal_id": signal.signal_id,
            "source": signal.source_suit,
            "payload": signal.payload,
            "status": "drafting",
            "proposal_type": "transformation",
        }
        self._pending.append(draft)
        self.pulse_bus.emit(self.SUIT_ID, "drafting", {
            "draft_id": draft["proposal_id"],
            "pending_count": len(self._pending),
        })

    def _on_error(self, signal: PulseSignal) -> None:
        draft = {
            "proposal_id": f"PROP-{uuid.uuid4().hex[:6]}",
            "trigger_signal_id": signal.signal_id,
            "error_context": signal.payload,
            "status": "drafting",
            "proposal_type": "recovery",
        }
        self._pending.append(draft)

    def _on_propose_request(self, signal: PulseSignal) -> None:
        target_id = signal.payload.get("draft_id")
        for draft in self._pending:
            if draft["proposal_id"] == target_id:
                draft["status"] = "finalized"
                self.pulse_bus.emit(self.SUIT_ID, "proposal_ready", {
                    "proposal_id": draft["proposal_id"],
                    "trigger_signal_id": draft["trigger_signal_id"],
                    "status": "finalized",
                    "proposal_type": draft["proposal_type"],
                })
                break