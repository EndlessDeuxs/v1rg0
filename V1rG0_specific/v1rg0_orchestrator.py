# v1rg0_orchestrator.py — PATCHED WITH COMPENSATION + TERMINAL
# BUILD_R: Integrate PushPullCompensator + Terminal support

import logging
from v1rg0_compensation import PushPullCompensator, CompensationStrategy

log = logging.getLogger("V1rG0.Orchestrator")


class Orchestrator:
    """
    V1rG0 Orchestrator — central processing node.
    Now with push/pull compensation and Terminal for shared supports.
    """

    def __init__(self, mit, proposal_builder, activator, bus_adapter, dlq_handler=None, terminal=None):
        self.mit = mit
        self.proposal_builder = proposal_builder
        self.activator = activator
        self.bus_adapter = bus_adapter
        self.dlq_handler = dlq_handler
        self.terminal = terminal                     # New: shared Terminal
        self.compensator = PushPullCompensator(max_retries=3)

    def _build_packet(self, parsed_event: dict, uat_score: float, mit_action: str) -> dict:
        """Simple packet builder — expand as needed."""
        return {
            "event_id": parsed_event.get("event_id", "unknown"),
            "uat_score": uat_score,
            "mit_action": mit_action,
            "payload": parsed_event.get("payload", {}),
            "timestamp": time.time()
        }

    def ingest_event(self, parsed_event: dict) -> dict:
        """
        Process a parsed event through the full V1rG0 pipeline.
        """
        # STAGE 1 — MIT EVALUATION (with compensation)
        mit_report = self.compensator.push_with_compensation(
            push_fn=lambda: self.mit.evaluate(parsed_event),
            strategy=CompensationStrategy.RETRY,
            context="mit.evaluate",
            fallback={"uat_score": 0.0, "action": "none"}
        )
        uat_score = mit_report.get("uat_score", 0.0)
        mit_action = mit_report.get("action", "none")

        # STAGE 2 — BUILD PACKET
        packet = self._build_packet(parsed_event, uat_score, mit_action)

        # STAGE 3 — PROPOSAL CONSTRUCTION (with compensation)
        proposal = None
        if mit_action in ("escalate", "emit"):
            proposal = self.compensator.push_with_compensation(
                push_fn=lambda: self.proposal_builder.build(packet),
                strategy=CompensationStrategy.FALLBACK,
                context="proposal_builder.build",
                fallback={"error": "proposal_failed", "packet_id": packet.get("event_id")}
            )

        # STAGE 4 — BUS EMIT (Terminal-aware)
        if self.terminal and proposal:
            # Prefer Terminal for shared support routing
            self.bus_adapter.publish_via_terminal(proposal, target_suit="proposal_bus")  # example
        else:
            self.compensator.push_with_compensation(
                push_fn=lambda: self.bus_adapter.emit(packet),
                strategy=CompensationStrategy.HOLD,
                context="bus_adapter.emit"
            )

        # STAGE 5 — DOWNSTREAM ACTIVATION (with compensation)
        activation = None
        if proposal is not None:
            activation = self.compensator.push_with_compensation(
                push_fn=lambda: self.activator.activate(proposal),
                strategy=CompensationStrategy.ESCALATE,
                context="activator.activate"
            )

        # STAGE 6 — PROCESS HELD OPERATIONS + DLQ
        held_processed = self.compensator.process_hold_queue()
        if held_processed > 0:
            log.info(f"Orchestrator: processed {held_processed} held operations")

        # Optional DLQ on error paths (example)
        # if some_error_condition:
        #     self.dlq_handler.handle_error({...})

        return {
            "uat_score":  uat_score,
            "mit_action": mit_action,
            "packet":     packet,
            "proposal":   proposal,
            "activation": activation
        }