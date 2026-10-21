# v1rg0_integration_harness.py — ADAPTER INJECTION FIX
# BUILD_R: Resolves CRITICAL finding — adapter not injected into components
# All components receive adapter via post-construction injection

import json
import logging
from typing import Callable, Dict, List, Optional

from tg6d_bus import TG6DBus
from tg6d_pulse import TG6DPulse

from v1rg0_salience_engine import SalienceEngine
from v1rg0_mit import MIT
from v1rg0_orchestrator import Orchestrator
from v1rg0_memory_store import MemoryStore
from v1rg0_proposal_builder import ProposalBuilder
from v1rg0_downstream import DownstreamActivator
from v1rg0_bus_integration import V1rG0BusAdapter
from v1rg0_pulse_integration import PulseDrivenPressureDecay
from agentman_registry import AgentmanRegistry
from compress_collecticks import compress_instruction, validate_token_budget

log = logging.getLogger("V1rG0.Harness")


def build_stack(mock_api_callback: Optional[Callable] = None) -> Dict:
    """
    Constructs and wires the full V1rG0 component stack.

    Construction order:
        1. Infrastructure (bus, adapter) — no V1rG0 dependencies
        2. Core components — constructed without adapter
        3. Adapter injection — adapter set on each component via setter
        4. Bus subscriptions — wired after all components exist
        5. Pulse integration — wired last, depends on orchestrator

    This order eliminates circular dependency risk.
    """

    log.info("BUILD_STACK | Phase 1: Infrastructure")

    registry = AgentmanRegistry()
    bus      = TG6DBus()
    adapter  = V1rG0BusAdapter(bus=bus)

    log.info("BUILD_STACK | Phase 2: Core components")

    salience   = SalienceEngine()
    memory     = MemoryStore()
    mit        = MIT()
    proposal   = ProposalBuilder(memory_store=memory)
    downstream = DownstreamActivator(
        mock_api_callback=mock_api_callback,
        proposal_builder=proposal
    )
    orchestrator = Orchestrator(
        salience_engine=salience,
        mit=mit,
        memory_store=memory
    )

    log.info("BUILD_STACK | Phase 3: Adapter injection")

    # Each component receives the adapter via setter.
    # Components must implement set_bus_adapter(adapter) — see Task 2.
    orchestrator.set_bus_adapter(adapter)
    proposal.set_bus_adapter(adapter)
    downstream.set_bus_adapter(adapter)

    log.info("BUILD_STACK | Phase 4: Bus subscriptions")

    # Packet processed → ProposalBuilder
    def _on_packet_processed(payload: dict) -> None:
        if payload.get("action") == "STORE_AND_PROPOSE":
            log.debug("BUS | packet_processed → proposal.on_packet_received")
            proposal.on_packet_received(payload)

    adapter.listen(
        V1rG0BusAdapter.EVENT_PACKET_PROCESSED,
        _on_packet_processed
    )

    # Proposal built → Downstream
    def _on_proposal_built(payload: dict) -> None:
        log.debug("BUS | proposal_built → downstream.on_proposal_received")
        downstream.on_proposal_received(payload)

    adapter.listen(
        V1rG0BusAdapter.EVENT_PROPOSAL_BUILT,
        _on_proposal_built
    )

    # Alert triggered → WARNING log (extensible to webhook)
    def _on_alert_triggered(payload: dict) -> None:
        log.warning(
            f"BUS | ALERT | "
            f"pressure={payload.get('pressure', 0.0):.4f} "
            f"tier={payload.get('tier', '—')}"
        )

    adapter.listen(
        V1rG0BusAdapter.EVENT_ALERT_TRIGGERED,
        _on_alert_triggered
    )

    log.info("BUILD_STACK | Phase 5: Pulse integration")

    pulse = TG6DPulse(bus=bus, interval_seconds=30)
    pressure_decay = PulseDrivenPressureDecay(
        bus_adapter=adapter,
        orchestrator=orchestrator,
        decay_rate=0.05
    )

    log.info("BUILD_STACK | Phase 6: Registry")

    registry.register("bus",              bus)
    registry.register("adapter",          adapter)
    registry.register("pulse",            pulse)
    registry.register("pressure_decay",   pressure_decay)
    registry.register("salience",         salience)
    registry.register("memory_store",     memory)
    registry.register("mit",              mit)
    registry.register("proposal_builder", proposal)
    registry.register("downstream",       downstream)
    registry.register("orchestrator",     orchestrator)

    log.info("BUILD_STACK | Complete — all phases nominal.")

    return {
        "registry":         registry,
        "bus":              bus,
        "adapter":          adapter,
        "pulse":            pulse,
        "pressure_decay":   pressure_decay,
        "salience":         salience,
        "memory_store":     memory,
        "mit":              mit,
        "proposal_builder": proposal,
        "downstream":       downstream,
        "orchestrator":     orchestrator
    }
