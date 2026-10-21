# inspec_tor.py
from __future__ import annotations
from contract_registry import ContractRegistry, attach_contract_middleware
from pulse import PulseBus, PulseSignal
import logging

logger = logging.getLogger(__name__)

class Inspec_tor:
    SUIT_ID = "inspec_tor"

    def __init__(self, pulse_bus: PulseBus) -> None:
        self.pulse_bus = pulse_bus
        ContractRegistry().register_suit(self.SUIT_ID, {
            "input": {"type": "design", "required_fields": ["design_id", "specification"]},
            "output": {"type": "validation", "required_fields": ["valid", "issues", "design_id"]},
        })
        attach_contract_middleware(pulse_bus, self.SUIT_ID)
        pulse_bus.subscribe("design_ready", self._validate_design)

    def _validate_design(self, signal: PulseSignal) -> None:
        design = signal.payload
        issues = []
        spec = design.get("specification", {})
        if not spec.get("structure"):
            issues.append("Missing specification structure")
        if not spec.get("version"):
            issues.append("Missing specification version")
        validation = {
            "type": "validation",
            "valid": len(issues) == 0,
            "issues": issues,
            "design_id": design.get("design_id"),
            "inspected_at": signal.timestamp,
        }
        self.pulse_bus.emit(self.SUIT_ID, "validation_result", validation)