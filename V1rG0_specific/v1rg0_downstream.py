# v1rg0_downstream.py
# Downstream Activator for V1rG0 — handles proposal activation with API calls

import time
from typing import Dict, Optional

class DownstreamActivator:
    """
    V1rG0 Downstream Activator.
    Uses APIHandler for urgency-based external calls.
    Terminal used only for shared twingate_* suits.
    """

    def __init__(
        self,
        mock_api_callback=None,
        proposal_builder=None,
        api_handler=None,           # New: real APIHandler for pushes
        terminal=None,              # Only for shared supports
        bus_adapter=None
    ):
        self._mock_api_callback = mock_api_callback
        self._proposal_builder = proposal_builder
        self._api_handler = api_handler
        self._terminal = terminal
        self._bus_adapter = bus_adapter
        self._activation_log = []

    def activate(self, proposal: dict) -> dict:
        """
        Main activation entrypoint.
        Routes through APIHandler when available, falls back to mock.
        """
        if self._api_handler:
            # Use real urgency-based push
            routing_token = proposal.get("routing_token", f"{proposal.get('proposal_type', 'unknown')}:{proposal.get('urgency', 'LOW')}")
            t_start = time.time()
            result = self._api_handler.push(proposal, routing_token, t_start)
            
            entry = {
                "proposal_id": proposal.get("proposal_id"),
                "status": result.status,
                "attempt_count": result.attempt_count,
                "elapsed_ms": result.elapsed_ms,
                "timestamp": time.time()
            }
            self._activation_log.append(entry)
            
            return {
                "status": result.status.value if hasattr(result.status, "value") else result.status,
                "timestamp": entry["timestamp"],
                "details": result.notes
            }
        
        # Fallback to mock (your original behavior)
        result = self._mock_api_callback(proposal) if self._mock_api_callback else {"acknowledged": True}
        entry = {
            "proposal_version": proposal.get("proposal_version"),
            "status": result.get("acknowledged"),
            "timestamp": time.time()
        }
        self._activation_log.append(entry)
        return {"status": "ACK", "timestamp": entry["timestamp"]}

    def on_proposal_received(self, proposal: dict) -> None:
        """Optional hook called from Orchestrator or Bus."""
        activation_result = self.activate(proposal)
        proposal["activation_result"] = activation_result

        if self._bus_adapter:
            self._bus_adapter.emit(
                event_type="V1rG0.DOWNSTREAM_ACK",
                payload={
                    "proposal_id": proposal.get("proposal_id"),
                    "status": activation_result.get("status"),
                    "timestamp": activation_result.get("timestamp")
                },
                source="V1rG0.Downstream"
            )

    def pull_activation_log(self, limit: int = 10) -> list:
        return list(self._activation_log[-limit:])

    def inject_api_handler(self, api_handler) -> None:
        """Post-construction injection."""
        self._api_handler = api_handler

    def inject_terminal(self, terminal) -> None:
        """Only needed for shared support calls."""
        self._terminal = terminal